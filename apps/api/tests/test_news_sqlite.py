import sqlite3

import pytest

from app.modules.news.domain.models import FeedItem, FeedItemType, Topic
from app.modules.news.infrastructure.cache.sqlite import SQLiteNewsRepository


def test_news_schema_is_idempotent_and_domain_isolated(tmp_path) -> None:
    database_path = tmp_path / "workbench.db"
    with sqlite3.connect(database_path) as connection:
        connection.execute("CREATE TABLE literature_sentinel (id TEXT PRIMARY KEY)")
        connection.execute("INSERT INTO literature_sentinel VALUES ('keep')")
        connection.commit()

    repository = SQLiteNewsRepository(f"sqlite:///{database_path.as_posix()}")
    assert repository.ensure_schema().version == 1
    assert repository.ensure_schema().version == 1

    with sqlite3.connect(database_path) as connection:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        migration_count = connection.execute(
            "SELECT COUNT(*) FROM news_schema_migrations"
        ).fetchone()[0]
        sentinel = connection.execute("SELECT id FROM literature_sentinel").fetchone()[0]

    assert {
        "news_feed_items",
        "news_topics",
        "news_item_topics",
        "news_user_state",
        "news_schema_migrations",
    }.issubset(tables)
    assert migration_count == 1
    assert sentinel == "keep"


def test_refresh_preserves_user_state_and_supports_feed_filters(tmp_path) -> None:
    database_path = tmp_path / "news.db"
    repository = SQLiteNewsRepository(f"sqlite:///{database_path.as_posix()}")
    topic = Topic(id="optical", name="Optical", keywords=("optical",))
    paper = _item("demo:paper", FeedItemType.PAPER, "Optical paper")
    repository.save_refresh(
        items=(paper, _item("demo:repo", FeedItemType.GITHUB_REPO, "Research repository")),
        topics=(topic,),
        item_topics={paper.id: (topic.id,), "demo:repo": ()},
    )

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "INSERT INTO news_user_state (item_id, read, saved, hidden) VALUES (?, 1, 1, 0)",
            (paper.id,),
        )
        connection.commit()

    updated_paper = _item("demo:paper", FeedItemType.PAPER, "Updated optical paper")
    repository.save_refresh(
        items=(updated_paper,),
        topics=(topic,),
        item_topics={updated_paper.id: (topic.id,)},
    )

    page = repository.list_feed(
        item_type=FeedItemType.PAPER,
        topic_id="optical",
        limit=10,
        offset=0,
    )
    empty_page = repository.list_feed(topic_id="missing", limit=10, offset=0)

    assert page.total == 1
    assert page.items[0].title == "Updated optical paper"
    assert page.items[0].topics == ("optical",)
    assert page.items[0].read is True
    assert page.items[0].saved is True
    assert page.items[0].hidden is False
    assert empty_page.items == ()
    assert empty_page.total == 0


def test_refresh_write_is_transactional(tmp_path) -> None:
    database_path = tmp_path / "transaction.db"
    repository = SQLiteNewsRepository(f"sqlite:///{database_path.as_posix()}")
    original = _item("demo:paper", FeedItemType.PAPER, "Original")
    repository.save_refresh(items=(original,), topics=(), item_topics={original.id: ()})

    with pytest.raises(sqlite3.IntegrityError):
        repository.save_refresh(
            items=(_item("demo:paper", FeedItemType.PAPER, "Partial update"),),
            topics=(),
            item_topics={"demo:paper": ("unknown-topic",)},
        )

    assert repository.list_feed().items[0].title == "Original"


def test_news_repository_rejects_non_sqlite_url() -> None:
    with pytest.raises(ValueError, match="sqlite"):
        SQLiteNewsRepository("postgresql://localhost/workbench")


def _item(item_id: str, item_type: FeedItemType, title: str) -> FeedItem:
    return FeedItem(
        id=item_id,
        type=item_type,
        source="demo",
        title=title,
        summary="Metadata only.",
        url="https://example.com/item",
        authors=("Example Author",),
        published_at="2026-08-20T00:00:00+00:00",
        fetched_at="2026-08-21T00:00:00+00:00",
        metadata={"kind": "test"},
    )
