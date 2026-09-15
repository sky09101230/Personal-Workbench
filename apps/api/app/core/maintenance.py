"""Run with: python -m app.core.maintenance backup --destination PATH."""

import argparse

from app.core.sqlite import backup_database


def main() -> None:
    parser = argparse.ArgumentParser(description="Workbench database maintenance")
    commands = parser.add_subparsers(dest="command", required=True)
    backup = commands.add_parser("backup", help="Create a verified, non-overwriting backup")
    backup.add_argument("--destination", required=True)
    backup.add_argument("--database-url")
    args = parser.parse_args()
    database_url = args.database_url
    if database_url is None:
        from app.core.config import settings

        database_url = settings.database_url
    print(backup_database(database_url, args.destination))


if __name__ == "__main__":
    main()
