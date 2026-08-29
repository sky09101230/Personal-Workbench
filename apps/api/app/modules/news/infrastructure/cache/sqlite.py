import json
import sqlite3
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.modules.news.application.errors import PaperResearchIdentityConflictError
from app.modules.news.application.research import canonical_title_year
from app.modules.news.domain.models import FeedItem, FeedItemType, FeedPage, Topic
from app.modules.news.domain.research_models import (
    PaperResearchFeedPage,
    PaperResearchIngest,
    PaperResearchIngestResult,
    PaperResearchPaperInput,
)


@dataclass(frozen=True)
class SchemaVersion:
    version: int


_SCHEMA_VERSION = 3
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
    """
    CREATE TABLE IF NOT EXISTS news_source_state (
        source TEXT PRIMARY KEY,
        last_successful_refresh_slot TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS news_feed_items_type_idx ON news_feed_items(type)",
    "CREATE INDEX IF NOT EXISTS news_feed_items_published_idx ON news_feed_items(published_at)",
    "CREATE INDEX IF NOT EXISTS news_item_topics_topic_idx ON news_item_topics(topic_id)",
    """
    CREATE TABLE IF NOT EXISTS news_papers (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        authors_json TEXT NOT NULL DEFAULT '[]',
        doi TEXT,
        arxiv_id TEXT,
        openalex_id TEXT,
        canonical_title_year TEXT NOT NULL UNIQUE,
        published_at TEXT,
        venue TEXT,
        url TEXT,
        pdf_url TEXT,
        abstract TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS news_paper_research_runs (
        id TEXT PRIMARY KEY,
        task_key TEXT NOT NULL,
        run_key TEXT NOT NULL,
        schema_version TEXT NOT NULL,
        status TEXT NOT NULL,
        generated_at TEXT NOT NULL,
        ingested_at TEXT NOT NULL,
        agent_type TEXT NOT NULL,
        agent_model TEXT NOT NULL,
        prompt_version TEXT NOT NULL,
        query_plan_json TEXT NOT NULL,
        papers_found INTEGER NOT NULL,
        papers_accepted INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE (task_key, run_key)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS news_paper_research_recommendations (
        id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL REFERENCES news_paper_research_runs(id) ON DELETE CASCADE,
        paper_id TEXT NOT NULL REFERENCES news_papers(id) ON DELETE CASCADE,
        ai_summary TEXT NOT NULL,
        recommendation_reason TEXT NOT NULL,
        relevance_score REAL CHECK (relevance_score IS NULL OR relevance_score BETWEEN 0 AND 1),
        novelty_score REAL CHECK (novelty_score IS NULL OR novelty_score BETWEEN 0 AND 1),
        topics_json TEXT NOT NULL DEFAULT '[]',
        matched_topics_json TEXT NOT NULL DEFAULT '[]',
        relationship_to_library TEXT,
        source_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL,
        UNIQUE (run_id, paper_id)
    )
    """,
    "CREATE UNIQUE INDEX IF NOT EXISTS news_papers_doi_unique ON news_papers(doi) WHERE doi IS NOT NULL",
    "CREATE UNIQUE INDEX IF NOT EXISTS news_papers_arxiv_unique ON news_papers(arxiv_id) WHERE arxiv_id IS NOT NULL",
    "CREATE UNIQUE INDEX IF NOT EXISTS news_papers_openalex_unique ON news_papers(openalex_id) WHERE openalex_id IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS news_research_runs_generated_idx ON news_paper_research_runs(generated_at DESC)",
    "CREATE INDEX IF NOT EXISTS news_recommendations_paper_idx ON news_paper_research_recommendations(paper_id, created_at DESC)",
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

    def get_source_refresh_slot(self, source: str) -> str | None:
        self.ensure_schema()
        with sqlite3.connect(self._database_path) as connection:
            row = connection.execute(
                "SELECT last_successful_refresh_slot FROM news_source_state WHERE source = ?",
                (source,),
            ).fetchone()
        return str(row[0]) if row is not None else None

    def ingest_paper_research(
        self,
        payload: PaperResearchIngest,
    ) -> PaperResearchIngestResult:
        self.ensure_schema()
        ingested_at = _utc_now()
        created_paper_ids: set[str] = set()
        updated_paper_ids: set[str] = set()
        created_recommendation_ids: set[str] = set()
        updated_recommendation_ids: set[str] = set()
        accepted_paper_ids: set[str] = set()

        with sqlite3.connect(self._database_path) as connection:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("BEGIN IMMEDIATE")
            try:
                run_row = connection.execute(
                    """
                    SELECT id
                    FROM news_paper_research_runs
                    WHERE task_key = ? AND run_key = ?
                    """,
                    (payload.task_key, payload.run_key),
                ).fetchone()
                created_run = run_row is None
                run_id = str(run_row[0]) if run_row else f"research-run:{uuid4()}"
                if created_run:
                    connection.execute(
                        """
                        INSERT INTO news_paper_research_runs (
                            id, task_key, run_key, schema_version, status, generated_at,
                            ingested_at, agent_type, agent_model, prompt_version,
                            query_plan_json, papers_found, papers_accepted, created_at
                        ) VALUES (?, ?, ?, ?, 'succeeded', ?, ?, ?, ?, ?, ?, ?, 0, ?)
                        """,
                        (
                            run_id,
                            payload.task_key,
                            payload.run_key,
                            payload.schema_version,
                            payload.generated_at,
                            ingested_at,
                            payload.agent.type,
                            payload.agent.model,
                            payload.agent.prompt_version,
                            _json(payload.query_plan),
                            len(payload.papers),
                            ingested_at,
                        ),
                    )
                else:
                    connection.execute(
                        """
                        UPDATE news_paper_research_runs
                        SET schema_version = ?, status = 'succeeded', generated_at = ?,
                            ingested_at = ?, agent_type = ?, agent_model = ?,
                            prompt_version = ?, query_plan_json = ?, papers_found = ?
                        WHERE id = ?
                        """,
                        (
                            payload.schema_version,
                            payload.generated_at,
                            ingested_at,
                            payload.agent.type,
                            payload.agent.model,
                            payload.agent.prompt_version,
                            _json(payload.query_plan),
                            len(payload.papers),
                            run_id,
                        ),
                    )

                for paper in payload.papers:
                    paper_id, created_paper = _upsert_research_paper(
                        connection,
                        paper,
                        ingested_at,
                    )
                    accepted_paper_ids.add(paper_id)
                    if created_paper:
                        created_paper_ids.add(paper_id)
                    else:
                        updated_paper_ids.add(paper_id)

                    recommendation_row = connection.execute(
                        """
                        SELECT id
                        FROM news_paper_research_recommendations
                        WHERE run_id = ? AND paper_id = ?
                        """,
                        (run_id, paper_id),
                    ).fetchone()
                    if recommendation_row is None:
                        recommendation_id = f"research-recommendation:{uuid4()}"
                        connection.execute(
                            """
                            INSERT INTO news_paper_research_recommendations (
                                id, run_id, paper_id, ai_summary, recommendation_reason,
                                relevance_score, novelty_score, topics_json,
                                matched_topics_json, relationship_to_library,
                                source_json, created_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                recommendation_id,
                                run_id,
                                paper_id,
                                paper.ai_summary,
                                paper.recommendation_reason,
                                paper.relevance_score,
                                paper.novelty_score,
                                _json(paper.topics),
                                _json(paper.matched_topics),
                                paper.relationship_to_library,
                                _json(paper.source),
                                ingested_at,
                            ),
                        )
                        created_recommendation_ids.add(recommendation_id)
                    else:
                        recommendation_id = str(recommendation_row[0])
                        connection.execute(
                            """
                            UPDATE news_paper_research_recommendations
                            SET ai_summary = ?, recommendation_reason = ?,
                                relevance_score = ?, novelty_score = ?, topics_json = ?,
                                matched_topics_json = ?, relationship_to_library = ?,
                                source_json = ?
                            WHERE id = ?
                            """,
                            (
                                paper.ai_summary,
                                paper.recommendation_reason,
                                paper.relevance_score,
                                paper.novelty_score,
                                _json(paper.topics),
                                _json(paper.matched_topics),
                                paper.relationship_to_library,
                                _json(paper.source),
                                recommendation_id,
                            ),
                        )
                        updated_recommendation_ids.add(recommendation_id)

                connection.execute(
                    """
                    UPDATE news_paper_research_runs
                    SET papers_accepted = ?
                    WHERE id = ?
                    """,
                    (len(accepted_paper_ids), run_id),
                )
                connection.commit()
            except sqlite3.IntegrityError as error:
                connection.rollback()
                raise PaperResearchIdentityConflictError(
                    "Paper identifiers conflict with existing Research data"
                ) from error
            except Exception:
                connection.rollback()
                raise

        return PaperResearchIngestResult(
            run_id=run_id,
            created_run=created_run,
            created_papers=len(created_paper_ids),
            updated_papers=len(updated_paper_ids - created_paper_ids),
            created_recommendations=len(created_recommendation_ids),
            updated_recommendations=len(updated_recommendation_ids - created_recommendation_ids),
            papers_found=len(payload.papers),
            papers_accepted=len(accepted_paper_ids),
        )

    def list_paper_research(
        self,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> PaperResearchFeedPage:
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        if offset < 0:
            raise ValueError("offset must be non-negative")
        self.ensure_schema()
        latest = """
            SELECT recommendation.*, ROW_NUMBER() OVER (
                PARTITION BY recommendation.paper_id
                ORDER BY run.generated_at DESC, run.ingested_at DESC,
                         recommendation.created_at DESC, recommendation.id DESC
            ) AS recency
            FROM news_paper_research_recommendations AS recommendation
            JOIN news_paper_research_runs AS run ON run.id = recommendation.run_id
        """
        with sqlite3.connect(self._database_path) as connection:
            total = connection.execute(
                f"SELECT COUNT(*) FROM ({latest}) AS latest WHERE latest.recency = 1"
            ).fetchone()[0]
            rows = connection.execute(
                f"""
                SELECT
                    paper.id, paper.title, paper.authors_json, paper.doi,
                    paper.arxiv_id, paper.openalex_id, paper.published_at,
                    paper.venue, paper.url, paper.pdf_url, paper.abstract,
                    latest.ai_summary, latest.recommendation_reason,
                    latest.relevance_score, latest.novelty_score,
                    latest.topics_json, latest.matched_topics_json,
                    latest.relationship_to_library, latest.source_json,
                    run.id, run.task_key, run.run_key, run.schema_version,
                    run.generated_at, run.ingested_at, run.agent_type,
                    run.agent_model, run.prompt_version, run.query_plan_json
                FROM ({latest}) AS latest
                JOIN news_papers AS paper ON paper.id = latest.paper_id
                JOIN news_paper_research_runs AS run ON run.id = latest.run_id
                WHERE latest.recency = 1
                ORDER BY run.generated_at DESC, paper.published_at DESC, paper.id
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            ).fetchall()
        return PaperResearchFeedPage(
            items=tuple(_research_feed_item(row) for row in rows),
            total=int(total),
            limit=limit,
            offset=offset,
        )

    def topics_match(self, topics: Iterable[Topic]) -> bool:
        self.ensure_schema()
        expected = sorted(
            (
                topic.id,
                topic.name,
                _json(topic.keywords),
                _json(topic.negative_keywords),
                _json(topic.enabled_sources),
            )
            for topic in topics
        )
        with sqlite3.connect(self._database_path) as connection:
            persisted = connection.execute(
                """
                SELECT id, name, keywords_json, negative_keywords_json, enabled_sources_json
                FROM news_topics
                ORDER BY id
                """
            ).fetchall()
        return persisted == expected

    def save_refresh(
        self,
        *,
        items: Iterable[FeedItem],
        topics: Iterable[Topic],
        item_topics: Mapping[str, Iterable[str]],
        source_slots: Mapping[str, str] | None = None,
        item_types: Iterable[FeedItemType] | None = None,
    ) -> int:
        self.ensure_schema()
        feed_items = tuple(items)
        topic_items = tuple(topics)
        refreshed_types = None if item_types is None else tuple(dict.fromkeys(item_types))

        with sqlite3.connect(self._database_path) as connection:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.executemany(
                    """
                    INSERT INTO news_topics
                        (id, name, keywords_json, negative_keywords_json, enabled_sources_json)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        name = excluded.name,
                        keywords_json = excluded.keywords_json,
                        negative_keywords_json = excluded.negative_keywords_json,
                        enabled_sources_json = excluded.enabled_sources_json
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
                topic_ids = tuple(topic.id for topic in topic_items)
                if topic_ids:
                    placeholders = ", ".join("?" for _ in topic_ids)
                    connection.execute(
                        f"DELETE FROM news_topics WHERE id NOT IN ({placeholders})",
                        topic_ids,
                    )
                else:
                    connection.execute("DELETE FROM news_topics")
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
                item_ids = tuple(item.id for item in feed_items)
                if refreshed_types is None:
                    if item_ids:
                        placeholders = ", ".join("?" for _ in item_ids)
                        connection.execute(
                            f"DELETE FROM news_feed_items WHERE id NOT IN ({placeholders})",
                            item_ids,
                        )
                    else:
                        connection.execute("DELETE FROM news_feed_items")
                elif refreshed_types:
                    type_values = tuple(item_type.value for item_type in refreshed_types)
                    type_placeholders = ", ".join("?" for _ in type_values)
                    if item_ids:
                        item_placeholders = ", ".join("?" for _ in item_ids)
                        connection.execute(
                            f"DELETE FROM news_feed_items "
                            f"WHERE type IN ({type_placeholders}) "
                            f"AND id NOT IN ({item_placeholders})",
                            (*type_values, *item_ids),
                        )
                    else:
                        connection.execute(
                            f"DELETE FROM news_feed_items WHERE type IN ({type_placeholders})",
                            type_values,
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
                connection.executemany(
                    """
                    INSERT INTO news_source_state (source, last_successful_refresh_slot)
                    VALUES (?, ?)
                    ON CONFLICT(source) DO UPDATE SET
                        last_successful_refresh_slot = excluded.last_successful_refresh_slot
                    """,
                    tuple((source, slot) for source, slot in (source_slots or {}).items()),
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
        period: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> FeedPage:
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        if offset < 0:
            raise ValueError("offset must be non-negative")
        self.ensure_schema()

        where, parameters = _feed_filter(
            item_type=item_type,
            topic_id=topic_id,
            period=period,
        )
        rank_order = (
            """
                    CASE
                        WHEN json_type(item.metadata_json, '$.rank') IN ('integer', 'real') THEN 0
                        ELSE 1
                    END,
                    CASE
                        WHEN json_type(item.metadata_json, '$.rank') IN ('integer', 'real')
                        THEN json_extract(item.metadata_json, '$.rank')
                    END,
            """
            if item_type is not None
            else ""
        )
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
                ORDER BY
                    {rank_order}
                    COALESCE(item.published_at, item.fetched_at) DESC,
                    item.id
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
    period: str | None,
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
    if period is not None:
        clauses.append("json_extract(item.metadata_json, '$.period') = ?")
        parameters.append(period)
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


def _upsert_research_paper(
    connection: sqlite3.Connection,
    paper: PaperResearchPaperInput,
    updated_at: str,
) -> tuple[str, bool]:
    fallback_key = canonical_title_year(paper.title, paper.published_at)
    matches: set[str] = set()
    for column, value in (
        ("doi", paper.doi),
        ("arxiv_id", paper.arxiv_id),
        ("openalex_id", paper.openalex_id),
        ("canonical_title_year", fallback_key),
    ):
        if value is None:
            continue
        row = connection.execute(
            f"SELECT id FROM news_papers WHERE {column} = ?",
            (value,),
        ).fetchone()
        if row is not None:
            matches.add(str(row[0]))
    if len(matches) > 1:
        raise PaperResearchIdentityConflictError(
            "Paper identifiers resolve to multiple existing papers"
        )

    if not matches:
        paper_id = f"research-paper:{uuid4()}"
        connection.execute(
            """
            INSERT INTO news_papers (
                id, title, authors_json, doi, arxiv_id, openalex_id,
                canonical_title_year, published_at, venue, url, pdf_url,
                abstract, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                paper_id,
                paper.title,
                _json(paper.authors),
                paper.doi,
                paper.arxiv_id,
                paper.openalex_id,
                fallback_key,
                paper.published_at,
                paper.venue,
                paper.url,
                paper.pdf_url,
                paper.abstract,
                updated_at,
                updated_at,
            ),
        )
        return paper_id, True

    paper_id = next(iter(matches))
    existing = connection.execute(
        "SELECT doi, arxiv_id, openalex_id FROM news_papers WHERE id = ?",
        (paper_id,),
    ).fetchone()
    assert existing is not None
    for label, old_value, new_value in (
        ("DOI", existing[0], paper.doi),
        ("arXiv id", existing[1], paper.arxiv_id),
        ("OpenAlex id", existing[2], paper.openalex_id),
    ):
        if old_value is not None and new_value is not None and old_value != new_value:
            raise PaperResearchIdentityConflictError(
                f"Incoming {label} conflicts with the existing paper"
            )
    connection.execute(
        """
        UPDATE news_papers
        SET title = ?,
            authors_json = CASE WHEN ? = '[]' THEN authors_json ELSE ? END,
            doi = COALESCE(?, doi),
            arxiv_id = COALESCE(?, arxiv_id),
            openalex_id = COALESCE(?, openalex_id),
            canonical_title_year = ?,
            published_at = COALESCE(?, published_at),
            venue = COALESCE(?, venue),
            url = COALESCE(?, url),
            pdf_url = COALESCE(?, pdf_url),
            abstract = COALESCE(?, abstract),
            updated_at = ?
        WHERE id = ?
        """,
        (
            paper.title,
            _json(paper.authors),
            _json(paper.authors),
            paper.doi,
            paper.arxiv_id,
            paper.openalex_id,
            fallback_key,
            paper.published_at,
            paper.venue,
            paper.url,
            paper.pdf_url,
            paper.abstract,
            updated_at,
            paper_id,
        ),
    )
    return paper_id, False


def _research_feed_item(row: tuple[object, ...]) -> FeedItem:
    doi = str(row[3]) if row[3] is not None else None
    arxiv_id = str(row[4]) if row[4] is not None else None
    openalex_id = str(row[5]) if row[5] is not None else None
    url = (
        str(row[8])
        if row[8] is not None
        else str(row[9])
        if row[9] is not None
        else f"https://doi.org/{doi}"
        if doi
        else f"https://arxiv.org/abs/{arxiv_id}"
        if arxiv_id
        else f"https://openalex.org/{openalex_id}"
    )
    topics = tuple(json.loads(str(row[15])))
    matched_topics = tuple(json.loads(str(row[16])))
    return FeedItem(
        id=f"research:{row[0]}",
        type=FeedItemType.PAPER,
        source="research",
        title=str(row[1]),
        summary=str(row[11]),
        url=url,
        authors=tuple(json.loads(str(row[2]))),
        published_at=str(row[6]) if row[6] is not None else None,
        fetched_at=str(row[24]),
        topics=topics,
        metadata={
            "summary_kind": "ai",
            "research_kind": "ai_research",
            "recommendation_reason": str(row[12]),
            "relevance_score": float(row[13]) if row[13] is not None else None,
            "novelty_score": float(row[14]) if row[14] is not None else None,
            "matched_topics": list(matched_topics),
            "relationship_to_library": str(row[17]) if row[17] is not None else None,
            "source": dict(json.loads(str(row[18]))),
            "venue": str(row[7]) if row[7] is not None else None,
            "doi": doi,
            "arxiv_id": arxiv_id,
            "openalex_id": openalex_id,
            "pdf_url": str(row[9]) if row[9] is not None else None,
            "abstract": str(row[10]) if row[10] is not None else None,
            "research_run": {
                "id": str(row[19]),
                "task_key": str(row[20]),
                "run_key": str(row[21]),
                "schema_version": str(row[22]),
                "generated_at": str(row[23]),
                "ingested_at": str(row[24]),
                "agent_type": str(row[25]),
                "agent_model": str(row[26]),
                "prompt_version": str(row[27]),
                "query_plan": list(json.loads(str(row[28]))),
            },
        },
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _sqlite_path(database_url: str) -> str:
    prefix = "sqlite:///"
    if not database_url.startswith(prefix):
        raise ValueError("News cache requires a sqlite:/// database URL")
    return database_url.removeprefix(prefix)
