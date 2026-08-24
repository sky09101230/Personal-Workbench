import json
import sqlite3
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from app.modules.news.domain.models import FeedItem, FeedItemType, FeedPage, Topic


@dataclass(frozen=True)
class SchemaVersion:
    version: int


_SCHEMA_VERSION = 1
_SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS news_feed_items (
        id TEXT PRIMARY KEY,
        type TEXT NOT NULL,
        source TEXT NOT NULL,
        title TEXT NOT NULL,
        summary TEXT,
        url TEXT NOT NULL,
        authors_json TEXT NOT NULL,
        published_at TEXT,
        fetched_at TEXT,
        metadata_json TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS news_topics (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        keywords_json TEXT NOT NULL,
        negative_keywords_json TEXT NOT NULL,
        enabled_sources_json TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS news_item_topics (
        item_id TEXT NOT NULL REFERENCES news_feed_items(id) ON DELETE CASCADE,
        topic_id TEXT NOT NULL REFERENCES news_topics(id) ON DELETE CASCADE,
        PRIMARY KEY (item_id, topic_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS news_user_state (
        item_id TEXT PRIMARY KEY REFERENCES news_feed_items(id) ON DELETE CASCADE,
        read INTEGER NOT NULL DEFAULT 0,
        saved INTEGER NOT NULL DEFAULT 0,
        hidden INTEGER NOT NULL DEFAULT 0
    )
    """,
    "CREATE INDEX IF NOT EXISTS news_feed_items_type_idx ON news_feed_items(type)",
    "CREATE INDEX IF NOT EXISTS news_feed_items_published_idx ON news_feed_items(published_at)",
    "CREATE INDEX IF NOT EXISTS news_item_topics_topic_idx ON news_item_topics(topic_id)",
)


class SQLiteNewsRepository:
    """Owns the News-only schema within the shared Workbench SQLite file."""

    def __init__(self, database_url: str) -> None:
        self._database_path = _sqlite_path(database_url)

    def ensure_schema(self) -> SchemaVersion:
        if self._database_path != ":memory:":
            Path(self._database_path).parent.mkdir(parents=True, exist_ok=True)

        with sqlite3.connect(self._database_path) as connection:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS news_schema_migrations (
                        version INTEGER PRIMARY KEY,
                        applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                applied = connection.execute(
                    "SELECT 1 FROM news_schema_migrations WHERE version = ?",
                    (_SCHEMA_VERSION,),
                ).fetchone()
                if applied is None:
                    for statement in _SCHEMA_STATEMENTS:
                        connection.execute(statement)
                    connection.execute(
                        "INSERT INTO news_schema_migrations (version) VALUES (?)",
                        (_SCHEMA_VERSION,),
                    )
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        return SchemaVersion(version=_SCHEMA_VERSION)

    def save_refresh(
        self,
        *,
        items: Iterable[FeedItem],
        topics: Iterable[Topic],
        item_topics: Mapping[str, Iterable[str]],
    ) -> int:
        self.ensure_schema()
        feed_items = tuple(items)
        topic_items = tuple(topics)

        with sqlite3.connect(self._database_path) as connection:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute("DELETE FROM news_topics")
                connection.executemany(
                    """
                    INSERT INTO news_topics
                        (id, name, keywords_json, negative_keywords_json, enabled_sources_json)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        (
                            topic.id,
                            topic.name,
                            _json(topic.keywords),
                            _json(topic.negative_keywords),
                            _json(topic.enabled_sources),
                        )
                        for topic in topic_items
                    ),
                )
                connection.executemany(
                    """
                    INSERT INTO news_feed_items
                        (id, type, source, title, summary, url, authors_json, published_at, fetched_at, metadata_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        type = excluded.type,
                        source = excluded.source,
                        title = excluded.title,
                        summary = excluded.summary,
                        url = excluded.url,
                        authors_json = excluded.authors_json,
                        published_at = excluded.published_at,
                        fetched_at = excluded.fetched_at,
                        metadata_json = excluded.metadata_json
                    """,
                    (
                        (
                            item.id,
                            item.type.value,
                            item.source,
                            item.title,
                            item.summary,
                            item.url,
                            _json(item.authors),
                            item.published_at,
                            item.fetched_at,
                            _json(item.metadata),
                        )
                        for item in feed_items
                    ),
                )
                connection.executemany(
                    "DELETE FROM news_item_topics WHERE item_id = ?",
                    ((item.id,) for item in feed_items),
                )
                connection.executemany(
                    "INSERT INTO news_item_topics (item_id, topic_id) VALUES (?, ?)",
                    (
                        (item.id, topic_id)
                        for item in feed_items
                        for topic_id in item_topics.get(item.id, ())
                    ),
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        return len(feed_items)

    def list_feed(
        self,
        *,
        item_type: FeedItemType | None = None,
        topic_id: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> FeedPage:
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        if offset < 0:
            raise ValueError("offset must be non-negative")
        self.ensure_schema()

        where, parameters = _feed_filter(item_type=item_type, topic_id=topic_id)
        with sqlite3.connect(self._database_path) as connection:
            total = connection.execute(
                f"SELECT COUNT(*) FROM news_feed_items AS item {where}",
                parameters,
            ).fetchone()[0]
            rows = connection.execute(
                f"""
                SELECT
                    item.id, item.type, item.source, item.title, item.summary, item.url,
                    item.authors_json, item.published_at, item.fetched_at, item.metadata_json,
                    COALESCE(state.read, 0), COALESCE(state.saved, 0), COALESCE(state.hidden, 0)
                FROM news_feed_items AS item
                LEFT JOIN news_user_state AS state ON state.item_id = item.id
                {where}
                ORDER BY COALESCE(item.published_at, item.fetched_at) DESC, item.id
                LIMIT ? OFFSET ?
                """,
                (*parameters, limit, offset),
            ).fetchall()
            topic_map = _topics_by_item(connection, tuple(row[0] for row in rows))

        return FeedPage(
            items=tuple(_item_from_row(row, topic_map.get(row[0], ())) for row in rows),
            total=total,
            limit=limit,
            offset=offset,
        )


def _feed_filter(
    *,
    item_type: FeedItemType | None,
    topic_id: str | None,
) -> tuple[str, tuple[object, ...]]:
    clauses: list[str] = []
    parameters: list[object] = []
    if item_type is not None:
        clauses.append("item.type = ?")
        parameters.append(item_type.value)
    if topic_id is not None:
        clauses.append(
            "EXISTS (SELECT 1 FROM news_item_topics AS match "
            "WHERE match.item_id = item.id AND match.topic_id = ?)"
        )
        parameters.append(topic_id)
    return (f"WHERE {' AND '.join(clauses)}" if clauses else "", tuple(parameters))


def _topics_by_item(
    connection: sqlite3.Connection,
    item_ids: tuple[str, ...],
) -> dict[str, tuple[str, ...]]:
    if not item_ids:
        return {}
    placeholders = ", ".join("?" for _ in item_ids)
    rows = connection.execute(
        f"""
        SELECT item_id, topic_id
        FROM news_item_topics
        WHERE item_id IN ({placeholders})
        ORDER BY topic_id
        """,
        item_ids,
    ).fetchall()
    result: dict[str, list[str]] = {}
    for item_id, topic_id in rows:
        result.setdefault(item_id, []).append(topic_id)
    return {item_id: tuple(topic_ids) for item_id, topic_ids in result.items()}


def _item_from_row(row: tuple[object, ...], topics: tuple[str, ...]) -> FeedItem:
    return FeedItem(
        id=str(row[0]),
        type=FeedItemType(str(row[1])),
        source=str(row[2]),
        title=str(row[3]),
        summary=str(row[4]) if row[4] is not None else None,
        url=str(row[5]),
        authors=tuple(json.loads(str(row[6]))),
        published_at=str(row[7]) if row[7] is not None else None,
        fetched_at=str(row[8]) if row[8] is not None else None,
        topics=topics,
        metadata=dict(json.loads(str(row[9]))),
        read=bool(row[10]),
        saved=bool(row[11]),
        hidden=bool(row[12]),
    )


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _sqlite_path(database_url: str) -> str:
    prefix = "sqlite:///"
    if not database_url.startswith(prefix):
        raise ValueError("News cache requires a sqlite:/// database URL")
    return database_url.removeprefix(prefix)
