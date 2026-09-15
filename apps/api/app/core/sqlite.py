"""Shared SQLite lifecycle helpers used by module-owned repositories."""

import sqlite3
from contextlib import closing
from pathlib import Path


def database_path(database_url: str) -> Path:
    """Resolve the supported sqlite URL form to a filesystem path."""
    prefix = "sqlite:///"
    if not database_url.startswith(prefix):
        raise ValueError("Only sqlite:/// database URLs are supported")
    value = database_url[len(prefix) :]
    if not value or value == ":memory:":
        raise ValueError("A filesystem-backed SQLite database is required")
    return Path(value).resolve()


def backup_database(database_url: str, destination: str | Path) -> Path:
    """Create a consistent SQLite backup without altering the source database."""
    source_path = database_path(database_url)
    destination_path = Path(destination).resolve()
    if source_path == destination_path:
        raise ValueError("Backup destination must differ from source")
    if not source_path.is_file():
        raise FileNotFoundError(source_path)
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation prevents silently overwriting a previous backup.
    with destination_path.open("xb"):
        pass
    try:
        with closing(sqlite3.connect(source_path.as_uri() + "?mode=ro", uri=True)) as source:
            with closing(sqlite3.connect(destination_path)) as target:
                source.backup(target)
                if target.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                    raise ValueError("Backup integrity check failed")
    except BaseException:
        destination_path.unlink(missing_ok=True)
        raise
    return destination_path
