import sqlite3
import pytest

from app.core.sqlite import backup_database, database_path


def test_database_path_rejects_non_sqlite_urls(tmp_path) -> None:
    assert database_path(f"sqlite:///{(tmp_path / 'a.db').as_posix()}").name == "a.db"
    try:
        database_path("postgresql://example")
    except ValueError as error:
        assert "sqlite" in str(error)
    else:
        raise AssertionError("non-sqlite URL should be rejected")


def test_backup_database_preserves_source_contents(tmp_path) -> None:
    source = tmp_path / "source.db"
    with sqlite3.connect(source) as connection:
        connection.execute("create table sample (value text)")
        connection.execute("insert into sample values ('ok')")
    backup = backup_database(f"sqlite:///{source.as_posix()}", tmp_path / "backup.db")
    with sqlite3.connect(backup) as connection:
        assert connection.execute("select value from sample").fetchone() == ("ok",)


def test_backup_rejects_missing_source_without_creating_database(tmp_path) -> None:
    source = tmp_path / "missing.db"
    target = tmp_path / "backup.db"
    with pytest.raises(FileNotFoundError):
        backup_database(f"sqlite:///{source.as_posix()}", target)
    assert not source.exists()
    assert not target.exists()


def test_backup_never_overwrites_source_or_existing_target(tmp_path) -> None:
    source = tmp_path / "source.db"
    with sqlite3.connect(source) as db:
        db.execute("CREATE TABLE sample (id INTEGER)")
    url = f"sqlite:///{source.as_posix()}"
    with pytest.raises(ValueError):
        backup_database(url, source)
    target = tmp_path / "backup.db"
    target.write_bytes(b"previous backup")
    with pytest.raises(FileExistsError):
        backup_database(url, target)
    assert target.read_bytes() == b"previous backup"


def test_failed_backup_removes_partial_file(tmp_path) -> None:
    source = tmp_path / "corrupt.db"
    source.write_bytes(b"not a SQLite database" * 100)
    target = tmp_path / "backup.db"
    with pytest.raises(sqlite3.DatabaseError):
        backup_database(f"sqlite:///{source.as_posix()}", target)
    assert not target.exists()
