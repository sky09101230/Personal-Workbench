import ast
import sqlite3
from pathlib import Path

from app.modules.project_activity.infrastructure.sqlite import SQLiteProjectActivityRepository


MODULE_ROOT = Path(__file__).parents[1] / "app" / "modules" / "project_activity"
FORBIDDEN_MODULES = {
    "app.modules.todo",
    "app.modules.news",
    "app.modules.literature",
}


def test_project_activity_has_no_cross_module_imports() -> None:
    violations: list[str] = []
    for path in MODULE_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            imported: list[str] = []
            if isinstance(node, ast.Import):
                imported = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported = [node.module]
            for module in imported:
                if any(
                    module == forbidden or module.startswith(f"{forbidden}.")
                    for forbidden in FORBIDDEN_MODULES
                ):
                    violations.append(f"{path.relative_to(MODULE_ROOT)}:{node.lineno} {module}")

    assert violations == []


def test_project_activity_schema_references_only_owned_tables(tmp_path) -> None:
    database_path = tmp_path / "boundaries.db"
    SQLiteProjectActivityRepository(f"sqlite:///{database_path.as_posix()}")

    with sqlite3.connect(database_path) as connection:
        objects = connection.execute(
            """
            SELECT type, name, sql FROM sqlite_master
            WHERE type IN ('table', 'index') AND name NOT LIKE 'sqlite_%'
            """
        ).fetchall()
        foreign_key_targets = {
            row[2]
            for table in (
                "activity_project_sources",
                "activity_runs",
                "activity_events",
            )
            for row in connection.execute(f"PRAGMA foreign_key_list({table})").fetchall()
        }

    assert objects
    assert all(name.startswith("activity_") for _, name, _ in objects)
    assert foreign_key_targets <= {"activity_devices", "activity_project_sources"}
    schema_sql = "\n".join(sql or "" for _, _, sql in objects).lower()
    assert "todo_" not in schema_sql
    assert "news_" not in schema_sql
    assert "literature_" not in schema_sql
