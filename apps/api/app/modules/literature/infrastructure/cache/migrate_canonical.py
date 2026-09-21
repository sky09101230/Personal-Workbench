"""Run with PYTHONPATH=apps/api, python -m ...migrate_canonical --dry-run."""

import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile

from app.core.config import settings
from app.modules.literature.infrastructure.cache.canonical import SQLiteCanonicalRepository, backup_database


def main():
    parser = argparse.ArgumentParser(description="Back up and migrate Literature to canonical ownership")
    parser.add_argument("--database", default=settings.database_url.removeprefix("sqlite:///"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    source = Path(args.database).resolve()
    if not source.is_file():
        parser.error("Existing SQLite database required")
    if args.dry_run:
        with tempfile.TemporaryDirectory(prefix="literature-v2-") as tmp:
            target = str(Path(tmp) / "dry-run.db")
            backup_database(str(source), target)
            repository = SQLiteCanonicalRepository(f"sqlite:///{target}")
            report = repository.migration_report()
            with closing(sqlite3.connect(target)) as c:
                report["integrity"] = c.execute("PRAGMA integrity_check").fetchone()[0]
            print(json.dumps({"dry_run": True, "source": str(source), **report}, indent=2))
    else:
        repository = SQLiteCanonicalRepository(f"sqlite:///{source}")
        print(json.dumps({"dry_run": False, "source": str(source), **repository.migration_report()}, indent=2))


if __name__ == "__main__":
    main()
