import sqlite3

import pytest

from app.modules.literature.infrastructure.cache.sqlite import SQLiteLiteratureRepository


def test_schema_migration_creates_metadata_cache_idempotently(tmp_path) -> None:
    database_path = tmp_path / "literature.db"
    repository = SQLiteLiteratureRepository(f"sqlite:///{database_path.as_posix()}")

    assert repository.ensure_schema().version == 2
    assert repository.ensure_schema().version == 2

    with sqlite3.connect(database_path) as connection:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        migration_count = connection.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0]

    assert {
        "literature_library_state",
        "literature_papers",
        "literature_collections",
        "literature_collection_papers",
        "literature_tags",
        "literature_notes",
        "literature_attachments",
        "literature_external_references",
    }.issubset(tables)
    assert migration_count == 2


def test_schema_migration_rejects_non_sqlite_database_urls() -> None:
    with pytest.raises(ValueError, match="sqlite"):
        SQLiteLiteratureRepository("postgresql://localhost/workbench")


def test_v2_migration_preserves_cache_and_requires_one_full_asset_sync(tmp_path) -> None:
    database_path = tmp_path / "v1.db"
    with sqlite3.connect(database_path) as connection:
        connection.execute("CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY)")
        connection.execute("INSERT INTO schema_migrations (version) VALUES (1)")
        connection.execute(
            """
            CREATE TABLE literature_library_state (
                provider TEXT NOT NULL,
                library_id TEXT NOT NULL,
                library_version TEXT,
                last_synced_at TEXT,
                sync_state TEXT NOT NULL,
                sync_error TEXT,
                PRIMARY KEY (provider, library_id)
            )
            """
        )
        connection.execute(
            "INSERT INTO literature_library_state VALUES ('zotero', '123', '5013', 'now', 'succeeded', NULL)"
        )
        connection.execute(
            "CREATE TABLE literature_notes (id TEXT PRIMARY KEY, paper_id TEXT, content TEXT, created_at TEXT, updated_at TEXT)"
        )
        connection.execute(
            "CREATE TABLE literature_attachments (id TEXT PRIMARY KEY, paper_id TEXT, filename TEXT, content_type TEXT, downloadable INTEGER, created_at TEXT, updated_at TEXT)"
        )
        connection.commit()

    repository = SQLiteLiteratureRepository(f"sqlite:///{database_path.as_posix()}")
    assert repository.ensure_schema().version == 2

    with sqlite3.connect(database_path) as connection:
        state = connection.execute(
            "SELECT library_version, last_synced_at, sync_state FROM literature_library_state"
        ).fetchone()
        note_columns = {row[1] for row in connection.execute("PRAGMA table_info(literature_notes)")}
        attachment_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(literature_attachments)")
        }

    assert state == (None, "now", "not_started")
    assert {"kind", "page_label", "color"}.issubset(note_columns)
    assert "link_mode" in attachment_columns
