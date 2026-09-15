import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from app.core.sqlite import database_path
from app.core.tasks import TaskSnapshot, TaskStatus


class SQLiteTaskRepository:
    def __init__(self, database_url: str) -> None:
        self._path = database_path(database_url)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._path) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS workbench_tasks (
                id TEXT PRIMARY KEY, operation TEXT NOT NULL, status TEXT NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                error_code TEXT, result_ref TEXT
            )""")

    def save(self, snapshot: TaskSnapshot) -> None:
        with sqlite3.connect(self._path) as db:
            db.execute("""INSERT OR REPLACE INTO workbench_tasks
                (id, operation, status, created_at, updated_at, error_code, result_ref)
                VALUES (?, ?, ?, ?, ?, ?, ?)""", (
                    snapshot.id, snapshot.operation, snapshot.status.value,
                    snapshot.created_at.isoformat(), snapshot.updated_at.isoformat(),
                    snapshot.error_code, snapshot.result_ref,
                ))

    def get(self, task_id: str) -> TaskSnapshot | None:
        with sqlite3.connect(self._path) as db:
            row = db.execute("SELECT * FROM workbench_tasks WHERE id = ?", (task_id,)).fetchone()
        if row is None:
            return None
        return TaskSnapshot(row[0], row[1], TaskStatus(row[2]), datetime.fromisoformat(row[3]), datetime.fromisoformat(row[4]), row[5], row[6])

    def mark_interrupted(self) -> int:
        """Mark tasks left running by a previous process as failed."""
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self._path) as db:
            cursor = db.execute(
                "UPDATE workbench_tasks SET status = ?, updated_at = ?, error_code = ? WHERE status = ?",
                (TaskStatus.FAILED.value, now, "process_interrupted", TaskStatus.RUNNING.value),
            )
            return cursor.rowcount
