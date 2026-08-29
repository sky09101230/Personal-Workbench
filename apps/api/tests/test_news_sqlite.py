import sqlite3
from dataclasses import replace

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
    assert repository.ensure_schema().version == 3
    assert repository.ensure_schema().version == 3

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
        "news_source_state",
        "news_user_state",
        "news_schema_migrations",
        "news_papers",
        "news_paper_research_runs",
        "news_paper_research_recommendations",
    }.issubset(tables)
    assert migration_count == 1
    assert sentinel == "keep"


def test_news_schema_upgrades_v2_without_losing_existing_feed(tmp_path) -> None:
    database_path = tmp_path / "upgrade.db"
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE news_schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute("INSERT INTO news_schema_migrations (version) VALUES (2)")
        connection.execute(
            """
            CREATE TABLE news_feed_items (
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
            """
        )
        connection.execute(
            """
            INSERT INTO news_feed_items (
                id, type, source, title, url, authors_json, metadata_json
            ) VALUES ('openalex:existing', 'paper', 'openalex', 'Existing',
                      'https://example.com/existing', '[]', '{}')
            """
        )
        connection.commit()

    repository = SQLiteNewsRepository(f"sqlite:///{database_path.as_posix()}")
    assert repository.ensure_schema().version == 3

    with sqlite3.connect(database_path) as connection:
        versions = connection.execute(
            "SELECT version FROM news_schema_migrations ORDER BY version"
        ).fetchall()
        existing = connection.execute(
            "SELECT title FROM news_feed_items WHERE id = 'openalex:existing'"
        ).fetchone()[0]
        research_tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name LIKE 'news_paper%'"
            )
        }

    assert versions == [(2,), (3,)]
    assert existing == "Existing"
    assert research_tables == {
        "news_papers",
        "news_paper_research_runs",
        "news_paper_research_recommendations",
    }


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
    assert repository.topics_match((topic,)) is True
    assert repository.topics_match((Topic(id="other", name="Other"),)) is False


def test_refresh_reconciles_old_news_data_without_touching_shared_tables(tmp_path) -> None:
    database_path = tmp_path / "reconcile.db"
    with sqlite3.connect(database_path) as connection:
        connection.execute("CREATE TABLE literature_sentinel (id TEXT PRIMARY KEY)")
        connection.execute("INSERT INTO literature_sentinel VALUES ('keep')")
        connection.commit()

    repository = SQLiteNewsRepository(f"sqlite:///{database_path.as_posix()}")
    old_topic = Topic(id="old-topic", name="Old Topic", keywords=("old",))
    old_item = _item("demo:old", FeedItemType.PAPER, "Old paper")
    repository.save_refresh(
        items=(old_item,),
        topics=(old_topic,),
        item_topics={old_item.id: (old_topic.id,)},
    )
    target_topics = (
        Topic(
            id="diffractive-neural-networks",
            name="Diffractive Neural Networks",
            keywords=("D2NN",),
            enabled_sources=("openalex",),
        ),
        Topic(
            id="optical-computing",
            name="Optical Computing",
            keywords=("optical computing",),
            enabled_sources=("openalex",),
        ),
        Topic(
            id="metasurface",
            name="Metasurface",
            keywords=("metasurface",),
            enabled_sources=("openalex",),
        ),
    )

    repository.save_refresh(items=(), topics=target_topics, item_topics={})

    with sqlite3.connect(database_path) as connection:
        topics = connection.execute("SELECT id, name FROM news_topics ORDER BY id").fetchall()
        feed_count = connection.execute("SELECT COUNT(*) FROM news_feed_items").fetchone()[0]
        sentinel = connection.execute("SELECT id FROM literature_sentinel").fetchone()[0]

    assert topics == [
        ("diffractive-neural-networks", "Diffractive Neural Networks"),
        ("metasurface", "Metasurface"),
        ("optical-computing", "Optical Computing"),
    ]
    assert feed_count == 0
    assert sentinel == "keep"


def test_typed_refresh_reconciles_only_that_feed_type(tmp_path) -> None:
    repository = SQLiteNewsRepository(f"sqlite:///{(tmp_path / 'typed.db').as_posix()}")
    topic = Topic(id="optical", name="Optical", keywords=("optical",))
    paper = _item("demo:paper", FeedItemType.PAPER, "Original paper")
    repository_item = _item("demo:repo", FeedItemType.GITHUB_REPO, "Repository")
    repository.save_refresh(
        items=(paper, repository_item),
        topics=(topic,),
        item_topics={paper.id: (topic.id,), repository_item.id: (topic.id,)},
    )
    updated_paper = _item("demo:paper", FeedItemType.PAPER, "Updated paper")

    repository.save_refresh(
        items=(updated_paper,),
        topics=(topic,),
        item_topics={updated_paper.id: (topic.id,)},
        item_types=(FeedItemType.PAPER,),
    )

    items = {item.id: item for item in repository.list_feed().items}
    assert items["demo:paper"].title == "Updated paper"
    assert items["demo:repo"].title == "Repository"
    assert items["demo:repo"].topics == ("optical",)

    repository.save_refresh(
        items=(),
        topics=(topic,),
        item_topics={},
        item_types=(FeedItemType.PAPER,),
    )

    remaining = repository.list_feed()
    assert [item.id for item in remaining.items] == ["demo:repo"]


def test_ranked_github_refresh_and_paper_refresh_preserve_each_other(tmp_path) -> None:
    repository = SQLiteNewsRepository(f"sqlite:///{(tmp_path / 'ranked.db').as_posix()}")
    topic = Topic(id="optical", name="Optical", keywords=("optical",))
    paper = replace(
        _item("openalex:paper", FeedItemType.PAPER, "Optical paper"),
        published_at="2026-08-26T00:00:00+00:00",
    )
    stale_repo = _ranked_repo(
        "github_trending:daily:stale/repo",
        "stale/repo",
        rank=1,
        period="daily",
    )
    repository.save_refresh(
        items=(paper, stale_repo),
        topics=(topic,),
        item_topics={paper.id: (topic.id,), stale_repo.id: ()},
    )

    second = _ranked_repo(
        "github_trending:daily:second/repo",
        "second/repo",
        rank=2,
        period="daily",
    )
    first = _ranked_repo(
        "github_trending:daily:first/repo",
        "first/repo",
        rank=1,
        period="daily",
    )
    weekly = _ranked_repo(
        "github_trending:weekly:first/repo",
        "first/repo",
        rank=1,
        period="weekly",
    )
    repository.save_refresh(
        items=(second, first, weekly),
        topics=(topic,),
        item_topics={second.id: (), first.id: (), weekly.id: ()},
        item_types=(FeedItemType.GITHUB_REPO,),
    )

    assert repository.list_feed(item_type=FeedItemType.PAPER).items[0].id == paper.id
    ranked = repository.list_feed(item_type=FeedItemType.GITHUB_REPO, period="daily")
    assert [item.id for item in ranked.items] == [first.id, second.id]
    assert [item.metadata["rank"] for item in ranked.items] == [1, 2]
    assert repository.list_feed(
        item_type=FeedItemType.GITHUB_REPO,
        period="weekly",
    ).items == (weekly,)
    assert repository.list_feed(
        item_type=FeedItemType.GITHUB_REPO,
        period="monthly",
    ).total == 0
    assert repository.list_feed().items[0].id == paper.id

    updated_paper = _item("openalex:paper", FeedItemType.PAPER, "Updated optical paper")
    repository.save_refresh(
        items=(updated_paper,),
        topics=(topic,),
        item_topics={updated_paper.id: (topic.id,)},
        item_types=(FeedItemType.PAPER,),
    )

    assert repository.list_feed(item_type=FeedItemType.PAPER).items[0].title == "Updated optical paper"
    assert [
        item.id
        for item in repository.list_feed(
            item_type=FeedItemType.GITHUB_REPO,
            period="daily",
        ).items
    ] == [first.id, second.id]


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
            source_slots={"openalex": "2026-08-25-AM"},
        )

    assert repository.list_feed().items[0].title == "Original"
    assert repository.get_source_refresh_slot("openalex") is None


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


def _ranked_repo(item_id: str, title: str, *, rank: int, period: str) -> FeedItem:
    return FeedItem(
        id=item_id,
        type=FeedItemType.GITHUB_REPO,
        source="github_trending",
        title=title,
        summary=None,
        url=f"https://github.com/{title}",
        fetched_at="2026-08-25T00:00:00+00:00",
        metadata={"rank": rank, "period": period},
    )
