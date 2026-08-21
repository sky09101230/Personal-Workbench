import sqlite3

import pytest

from app.modules.literature.infrastructure.cache.sqlite import SQLiteLiteratureRepository


def test_schema_migration_creates_metadata_cache_idempotently(tmp_path) -> None:
    database_path = tmp_path / "literature.db"
    repository = SQLiteLiteratureRepository(f"sqlite:///{database_path.as_posix()}")

    assert repository.ensure_schema().version == 1
    assert repository.ensure_schema().version == 1

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
    assert migration_count == 1


def test_schema_migration_rejects_non_sqlite_database_urls() -> None:
    with pytest.raises(ValueError, match="sqlite"):
        SQLiteLiteratureRepository("postgresql://localhost/workbench")
