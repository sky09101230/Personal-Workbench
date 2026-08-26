import sqlite3
from contextlib import contextmanager
from collections.abc import Iterator
from datetime import date, datetime
from pathlib import Path

from app.modules.todo.application.errors import (
    TodoConflictError,
    TodoNotFoundError,
)
from app.modules.todo.domain.models import (
    PlanProposal,
    PlanProposalItem,
    Project,
    ProjectOverview,
    ProjectStatus,
    ProposalStatus,
    Task,
    TaskPriority,
    TaskStatus,
)


_SCHEMA_VERSION = 1
_SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS todo_projects (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        status TEXT NOT NULL CHECK (status IN ('active', 'paused', 'archived')),
        sort_order INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS todo_tasks (
        id TEXT PRIMARY KEY,
        project_id TEXT REFERENCES todo_projects(id) ON DELETE SET NULL,
        title TEXT NOT NULL,
        description TEXT,
        status TEXT NOT NULL CHECK (status IN ('todo', 'doing', 'done', 'cancelled')),
        priority TEXT CHECK (priority IS NULL OR priority IN ('low', 'medium', 'high')),
        due_date TEXT,
        planned_date TEXT,
        is_next_action INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        completed_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS todo_plan_proposals (
        id TEXT PRIMARY KEY,
        status TEXT NOT NULL CHECK (status IN ('pending', 'accepted', 'rejected')),
        summary TEXT,
        created_at TEXT NOT NULL,
        decided_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS todo_plan_proposal_items (
        id TEXT PRIMARY KEY,
        proposal_id TEXT NOT NULL REFERENCES todo_plan_proposals(id) ON DELETE CASCADE,
        task_id TEXT NOT NULL,
        suggested_planned_date TEXT NOT NULL,
        suggested_priority TEXT CHECK (
            suggested_priority IS NULL OR suggested_priority IN ('low', 'medium', 'high')
        ),
        reason TEXT,
        UNIQUE (proposal_id, task_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS todo_projects_status_order_idx ON todo_projects(status, sort_order)",
    "CREATE INDEX IF NOT EXISTS todo_tasks_project_status_idx ON todo_tasks(project_id, status)",
    "CREATE INDEX IF NOT EXISTS todo_tasks_planned_idx ON todo_tasks(planned_date, status)",
    "CREATE INDEX IF NOT EXISTS todo_tasks_due_idx ON todo_tasks(due_date, status)",
    "CREATE UNIQUE INDEX IF NOT EXISTS todo_tasks_one_next_action_idx "
    "ON todo_tasks(project_id) WHERE project_id IS NOT NULL "
    "AND is_next_action = 1 AND status IN ('todo', 'doing')",
    "CREATE INDEX IF NOT EXISTS todo_proposal_items_proposal_idx ON todo_plan_proposal_items(proposal_id)",
)


class SQLiteTodoRepository:
    """Own the Todo-only schema and transactional write rules."""

    def __init__(self, database_url: str) -> None:
        self._database_path = _sqlite_path(database_url)

    def ensure_schema(self) -> int:
        if self._database_path != ":memory:":
            Path(self._database_path).parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS todo_schema_migrations (
                        version INTEGER PRIMARY KEY,
                        applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                applied = connection.execute(
                    "SELECT 1 FROM todo_schema_migrations WHERE version = ?",
                    (_SCHEMA_VERSION,),
                ).fetchone()
                if applied is None:
                    for statement in _SCHEMA_STATEMENTS:
                        connection.execute(statement)
                    connection.execute(
                        "INSERT INTO todo_schema_migrations (version) VALUES (?)",
                        (_SCHEMA_VERSION,),
                    )
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        return _SCHEMA_VERSION

    def create_project(self, project: Project) -> Project:
        self.ensure_schema()
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO todo_projects (id, name, status, sort_order, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    project.id,
                    project.name,
                    project.status.value,
                    project.order,
                    _datetime_text(project.created_at),
                    _datetime_text(project.updated_at),
                ),
            )
        return project

    def get_project(self, project_id: str) -> Project | None:
        self.ensure_schema()
        with self._connection() as connection:
            row = connection.execute(
                "SELECT id, name, status, sort_order, created_at, updated_at "
                "FROM todo_projects WHERE id = ?",
                (project_id,),
            ).fetchone()
        return _project_from_row(row) if row is not None else None

    def list_projects(self, *, status: ProjectStatus | None = None) -> tuple[Project, ...]:
        self.ensure_schema()
        with self._connection() as connection:
            if status is None:
                rows = connection.execute(
                    "SELECT id, name, status, sort_order, created_at, updated_at "
                    "FROM todo_projects ORDER BY sort_order, created_at, id"
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT id, name, status, sort_order, created_at, updated_at "
                    "FROM todo_projects WHERE status = ? ORDER BY sort_order, created_at, id",
                    (status.value,),
                ).fetchall()
        return tuple(_project_from_row(row) for row in rows)

    def update_project(self, project: Project) -> Project:
        self.ensure_schema()
        with self._connection() as connection:
            cursor = connection.execute(
                """
                UPDATE todo_projects
                SET name = ?, status = ?, sort_order = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    project.name,
                    project.status.value,
                    project.order,
                    _datetime_text(project.updated_at),
                    project.id,
                ),
            )
        if cursor.rowcount == 0:
            raise TodoNotFoundError("Project was not found")
        return project

    def delete_project(self, project_id: str) -> bool:
        self.ensure_schema()
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    "UPDATE todo_tasks SET is_next_action = 0 WHERE project_id = ?",
                    (project_id,),
                )
                cursor = connection.execute(
                    "DELETE FROM todo_projects WHERE id = ?",
                    (project_id,),
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        return cursor.rowcount > 0

    def create_task(self, task: Task) -> Task:
        self.ensure_schema()
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                if task.is_next_action and task.project_id is not None:
                    connection.execute(
                        "UPDATE todo_tasks SET is_next_action = 0 WHERE project_id = ?",
                        (task.project_id,),
                    )
                _insert_task(connection, task)
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        return task

    def get_task(self, task_id: str) -> Task | None:
        self.ensure_schema()
        with self._connection() as connection:
            row = connection.execute(
                f"{_TASK_SELECT} WHERE task.id = ?",
                (task_id,),
            ).fetchone()
        return _task_from_row(row) if row is not None else None

    def list_tasks(self) -> tuple[Task, ...]:
        self.ensure_schema()
        with self._connection() as connection:
            rows = connection.execute(
                f"{_TASK_SELECT} ORDER BY task.created_at DESC, task.id"
            ).fetchall()
        return tuple(_task_from_row(row) for row in rows)

    def list_tasks_for_project(self, project_id: str) -> tuple[Task, ...]:
        self.ensure_schema()
        with self._connection() as connection:
            rows = connection.execute(
                f"{_TASK_SELECT} WHERE task.project_id = ? "
                "ORDER BY CASE task.status WHEN 'doing' THEN 0 WHEN 'todo' THEN 1 "
                "WHEN 'done' THEN 2 ELSE 3 END, "
                "COALESCE(task.completed_at, task.updated_at) DESC, task.id",
                (project_id,),
            ).fetchall()
        return tuple(_task_from_row(row) for row in rows)

    def update_task(self, task: Task) -> Task:
        self.ensure_schema()
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                if task.is_next_action and task.project_id is not None:
                    connection.execute(
                        "UPDATE todo_tasks SET is_next_action = 0 "
                        "WHERE project_id = ? AND id <> ?",
                        (task.project_id, task.id),
                    )
                cursor = connection.execute(
                    """
                    UPDATE todo_tasks
                    SET project_id = ?, title = ?, description = ?, status = ?, priority = ?,
                        due_date = ?, planned_date = ?, is_next_action = ?, updated_at = ?,
                        completed_at = ?
                    WHERE id = ?
                    """,
                    _task_update_values(task),
                )
                if cursor.rowcount == 0:
                    raise TodoNotFoundError("Task was not found")
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        return task

    def delete_task(self, task_id: str) -> bool:
        self.ensure_schema()
        with self._connection() as connection:
            cursor = connection.execute("DELETE FROM todo_tasks WHERE id = ?", (task_id,))
        return cursor.rowcount > 0

    def list_inbox(self) -> tuple[Task, ...]:
        return self._list_tasks_where(
            "task.project_id IS NULL AND task.status IN ('todo', 'doing')",
            order="task.created_at DESC, task.id",
        )

    def list_unfinished(self) -> tuple[Task, ...]:
        return self._list_tasks_where(
            "task.status IN ('todo', 'doing')",
            order="task.is_next_action DESC, task.created_at, task.id",
        )

    def list_today_tasks(self, today: date) -> tuple[tuple[Task, ...], tuple[Task, ...]]:
        today_text = today.isoformat()
        carryover = self._list_tasks_where(
            "task.status IN ('todo', 'doing') AND task.planned_date < ?",
            (today_text,),
            order="task.planned_date, task.is_next_action DESC, task.created_at, task.id",
        )
        planned_today = self._list_tasks_where(
            "task.status IN ('todo', 'doing') AND task.planned_date = ?",
            (today_text,),
            order="task.is_next_action DESC, task.priority DESC, task.created_at, task.id",
        )
        return carryover, planned_today

    def list_upcoming(self, today: date) -> tuple[Task, ...]:
        today_text = today.isoformat()
        return self._list_tasks_where(
            "task.status IN ('todo', 'doing') "
            "AND (task.planned_date > ? OR task.due_date > ?)",
            (today_text, today_text),
            order=(
                "CASE "
                "WHEN task.planned_date > '" + today_text + "' AND task.due_date > '" + today_text + "' "
                "THEN MIN(task.planned_date, task.due_date) "
                "WHEN task.planned_date > '" + today_text + "' THEN task.planned_date "
                "ELSE task.due_date END, task.created_at, task.id"
            ),
        )

    def list_completed(self) -> tuple[Task, ...]:
        return self._list_tasks_where(
            "task.status = 'done'",
            order="COALESCE(task.completed_at, task.updated_at) DESC, task.id",
        )

    def list_project_overviews(self) -> tuple[ProjectOverview, ...]:
        projects = self.list_projects(status=ProjectStatus.ACTIVE)
        self.ensure_schema()
        overviews: list[ProjectOverview] = []
        with self._connection() as connection:
            for project in projects:
                count = connection.execute(
                    "SELECT COUNT(*) FROM todo_tasks "
                    "WHERE project_id = ? AND status IN ('todo', 'doing')",
                    (project.id,),
                ).fetchone()[0]
                row = connection.execute(
                    f"{_TASK_SELECT} WHERE task.project_id = ? "
                    "AND task.status IN ('todo', 'doing') AND task.is_next_action = 1 "
                    "ORDER BY task.updated_at DESC, task.id LIMIT 1",
                    (project.id,),
                ).fetchone()
                overviews.append(
                    ProjectOverview(
                        project=project,
                        unfinished_task_count=int(count),
                        next_action=_task_from_row(row) if row is not None else None,
                    )
                )
        return tuple(overviews)

    def create_proposal(self, proposal: PlanProposal) -> PlanProposal:
        self.ensure_schema()
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    """
                    INSERT INTO todo_plan_proposals (id, status, summary, created_at, decided_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        proposal.id,
                        proposal.status.value,
                        proposal.summary,
                        _datetime_text(proposal.created_at),
                        _optional_datetime_text(proposal.decided_at),
                    ),
                )
                connection.executemany(
                    """
                    INSERT INTO todo_plan_proposal_items
                        (id, proposal_id, task_id, suggested_planned_date,
                         suggested_priority, reason)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        (
                            item.id,
                            item.proposal_id,
                            item.task_id,
                            item.suggested_planned_date.isoformat(),
                            item.suggested_priority.value if item.suggested_priority else None,
                            item.reason,
                        )
                        for item in proposal.items
                    ),
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        return proposal

    def get_proposal(self, proposal_id: str) -> PlanProposal | None:
        self.ensure_schema()
        with self._connection() as connection:
            proposal_row = connection.execute(
                "SELECT id, status, summary, created_at, decided_at "
                "FROM todo_plan_proposals WHERE id = ?",
                (proposal_id,),
            ).fetchone()
            if proposal_row is None:
                return None
            item_rows = connection.execute(
                """
                SELECT id, proposal_id, task_id, suggested_planned_date,
                       suggested_priority, reason
                FROM todo_plan_proposal_items
                WHERE proposal_id = ?
                ORDER BY rowid
                """,
                (proposal_id,),
            ).fetchall()
        return _proposal_from_rows(proposal_row, item_rows)

    def accept_proposal(self, proposal_id: str, *, decided_at: datetime) -> PlanProposal:
        self.ensure_schema()
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                status_row = connection.execute(
                    "SELECT status FROM todo_plan_proposals WHERE id = ?",
                    (proposal_id,),
                ).fetchone()
                if status_row is None:
                    raise TodoNotFoundError("Plan proposal was not found")
                if status_row[0] != ProposalStatus.PENDING.value:
                    raise TodoConflictError("Plan proposal has already been decided")
                items = connection.execute(
                    "SELECT task_id, suggested_planned_date, suggested_priority "
                    "FROM todo_plan_proposal_items WHERE proposal_id = ? ORDER BY rowid",
                    (proposal_id,),
                ).fetchall()
                for task_id, planned_date, priority in items:
                    task_row = connection.execute(
                        "SELECT status FROM todo_tasks WHERE id = ?",
                        (task_id,),
                    ).fetchone()
                    if task_row is None or task_row[0] not in ("todo", "doing"):
                        raise TodoConflictError(
                            "A proposed Task no longer exists or is no longer unfinished"
                        )
                    connection.execute(
                        """
                        UPDATE todo_tasks
                        SET planned_date = ?,
                            priority = CASE WHEN ? IS NULL THEN priority ELSE ? END,
                            updated_at = ?
                        WHERE id = ?
                        """,
                        (
                            planned_date,
                            priority,
                            priority,
                            _datetime_text(decided_at),
                            task_id,
                        ),
                    )
                connection.execute(
                    "UPDATE todo_plan_proposals SET status = 'accepted', decided_at = ? WHERE id = ?",
                    (_datetime_text(decided_at), proposal_id),
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        proposal = self.get_proposal(proposal_id)
        if proposal is None:
            raise TodoNotFoundError("Plan proposal was not found")
        return proposal

    def reject_proposal(self, proposal_id: str, *, decided_at: datetime) -> PlanProposal:
        self.ensure_schema()
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                cursor = connection.execute(
                    """
                    UPDATE todo_plan_proposals
                    SET status = 'rejected', decided_at = ?
                    WHERE id = ? AND status = 'pending'
                    """,
                    (_datetime_text(decided_at), proposal_id),
                )
                if cursor.rowcount == 0:
                    exists = connection.execute(
                        "SELECT 1 FROM todo_plan_proposals WHERE id = ?",
                        (proposal_id,),
                    ).fetchone()
                    if exists is None:
                        raise TodoNotFoundError("Plan proposal was not found")
                    raise TodoConflictError("Plan proposal has already been decided")
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        proposal = self.get_proposal(proposal_id)
        if proposal is None:
            raise TodoNotFoundError("Plan proposal was not found")
        return proposal

    def _list_tasks_where(
        self,
        where: str,
        parameters: tuple[object, ...] = (),
        *,
        order: str,
    ) -> tuple[Task, ...]:
        self.ensure_schema()
        with self._connection() as connection:
            rows = connection.execute(
                f"{_TASK_SELECT} WHERE {where} ORDER BY {order}",
                parameters,
            ).fetchall()
        return tuple(_task_from_row(row) for row in rows)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path)
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()


_TASK_SELECT = """
SELECT task.id, task.project_id, task.title, task.description, task.status,
       task.priority, task.due_date, task.planned_date, task.is_next_action,
       task.created_at, task.updated_at, task.completed_at
FROM todo_tasks AS task
"""


def _insert_task(connection: sqlite3.Connection, task: Task) -> None:
    connection.execute(
        """
        INSERT INTO todo_tasks
            (id, project_id, title, description, status, priority, due_date, planned_date,
             is_next_action, created_at, updated_at, completed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            task.id,
            task.project_id,
            task.title,
            task.description,
            task.status.value,
            task.priority.value if task.priority else None,
            task.due_date.isoformat() if task.due_date else None,
            task.planned_date.isoformat() if task.planned_date else None,
            int(task.is_next_action),
            _datetime_text(task.created_at),
            _datetime_text(task.updated_at),
            _optional_datetime_text(task.completed_at),
        ),
    )


def _task_update_values(task: Task) -> tuple[object, ...]:
    return (
        task.project_id,
        task.title,
        task.description,
        task.status.value,
        task.priority.value if task.priority else None,
        task.due_date.isoformat() if task.due_date else None,
        task.planned_date.isoformat() if task.planned_date else None,
        int(task.is_next_action),
        _datetime_text(task.updated_at),
        _optional_datetime_text(task.completed_at),
        task.id,
    )


def _project_from_row(row: sqlite3.Row | tuple[object, ...]) -> Project:
    return Project(
        id=str(row[0]),
        name=str(row[1]),
        status=ProjectStatus(str(row[2])),
        order=int(row[3]),
        created_at=datetime.fromisoformat(str(row[4])),
        updated_at=datetime.fromisoformat(str(row[5])),
    )


def _task_from_row(row: sqlite3.Row | tuple[object, ...]) -> Task:
    return Task(
        id=str(row[0]),
        project_id=str(row[1]) if row[1] is not None else None,
        title=str(row[2]),
        description=str(row[3]) if row[3] is not None else None,
        status=TaskStatus(str(row[4])),
        priority=TaskPriority(str(row[5])) if row[5] is not None else None,
        due_date=date.fromisoformat(str(row[6])) if row[6] is not None else None,
        planned_date=date.fromisoformat(str(row[7])) if row[7] is not None else None,
        is_next_action=bool(row[8]),
        created_at=datetime.fromisoformat(str(row[9])),
        updated_at=datetime.fromisoformat(str(row[10])),
        completed_at=datetime.fromisoformat(str(row[11])) if row[11] is not None else None,
    )


def _proposal_from_rows(
    proposal_row: sqlite3.Row | tuple[object, ...],
    item_rows: list[sqlite3.Row] | list[tuple[object, ...]],
) -> PlanProposal:
    return PlanProposal(
        id=str(proposal_row[0]),
        status=ProposalStatus(str(proposal_row[1])),
        summary=str(proposal_row[2]) if proposal_row[2] is not None else None,
        created_at=datetime.fromisoformat(str(proposal_row[3])),
        decided_at=(
            datetime.fromisoformat(str(proposal_row[4]))
            if proposal_row[4] is not None
            else None
        ),
        items=tuple(
            PlanProposalItem(
                id=str(row[0]),
                proposal_id=str(row[1]),
                task_id=str(row[2]),
                suggested_planned_date=date.fromisoformat(str(row[3])),
                suggested_priority=(
                    TaskPriority(str(row[4])) if row[4] is not None else None
                ),
                reason=str(row[5]) if row[5] is not None else None,
            )
            for row in item_rows
        ),
    )


def _datetime_text(value: datetime) -> str:
    return value.isoformat()


def _optional_datetime_text(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _sqlite_path(database_url: str) -> str:
    prefix = "sqlite:///"
    if not database_url.startswith(prefix):
        raise ValueError("Todo repository requires a sqlite:/// database URL")
    return database_url.removeprefix(prefix)
