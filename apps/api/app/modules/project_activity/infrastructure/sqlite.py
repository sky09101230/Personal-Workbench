import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from collections.abc import Iterator

from app.modules.project_activity.application.errors import ProjectActivityConflictError
from app.modules.project_activity.domain.models import (
    ActivityEvent,
    ActivityRun,
    Device,
    ProjectSource,
)


_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class SchemaVersion:
    version: int


class SQLiteProjectActivityRepository:
    def __init__(self, database_url: str) -> None:
        self._database_path = _sqlite_path(database_url)
        self.ensure_schema()

    def ensure_schema(self) -> SchemaVersion:
        with self._connection() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS activity_schema_migrations "
                "(version INTEGER PRIMARY KEY)"
            )
            applied = {
                int(row[0])
                for row in connection.execute(
                    "SELECT version FROM activity_schema_migrations"
                ).fetchall()
            }
            if 1 not in applied:
                self._apply_v1(connection)
                connection.execute(
                    "INSERT INTO activity_schema_migrations (version) VALUES (1)"
                )
        return SchemaVersion(_SCHEMA_VERSION)

    def _apply_v1(self, connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            CREATE TABLE activity_devices (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                agent_version TEXT
            );

            CREATE TABLE activity_project_sources (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                source_type TEXT NOT NULL,
                source_key TEXT NOT NULL,
                device_id TEXT,
                local_path TEXT,
                last_seen_at TEXT NOT NULL,
                FOREIGN KEY (device_id) REFERENCES activity_devices(id)
            );

            CREATE UNIQUE INDEX activity_project_sources_device_key_uq
                ON activity_project_sources(device_id, source_key)
                WHERE device_id IS NOT NULL;
            CREATE UNIQUE INDEX activity_project_sources_global_key_uq
                ON activity_project_sources(source_key)
                WHERE device_id IS NULL;
            CREATE INDEX activity_project_sources_project_idx
                ON activity_project_sources(project_id);
            CREATE INDEX activity_project_sources_device_idx
                ON activity_project_sources(device_id);

            CREATE TABLE activity_runs (
                project_source_id TEXT NOT NULL,
                run_id TEXT NOT NULL,
                experiment_name TEXT,
                status TEXT NOT NULL,
                created_at TEXT,
                started_at TEXT,
                ended_at TEXT,
                latest_metrics_json TEXT,
                summary_json TEXT,
                config_summary_json TEXT,
                relative_path TEXT,
                has_best_checkpoint INTEGER NOT NULL,
                observed_at TEXT NOT NULL,
                PRIMARY KEY (project_source_id, run_id),
                FOREIGN KEY (project_source_id) REFERENCES activity_project_sources(id)
            );

            CREATE TABLE activity_events (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                source_id TEXT,
                activity_kind TEXT NOT NULL,
                event_type TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                subject_type TEXT,
                subject_id TEXT,
                payload_json TEXT,
                FOREIGN KEY (source_id) REFERENCES activity_project_sources(id)
            );

            CREATE INDEX activity_events_project_time_idx
                ON activity_events(project_id, occurred_at DESC);
            CREATE INDEX activity_events_source_time_idx
                ON activity_events(source_id, occurred_at DESC);
            CREATE INDEX activity_events_kind_time_idx
                ON activity_events(activity_kind, occurred_at DESC);
            """
        )

    def upsert_device(self, device: Device) -> Device:
        self.ensure_schema()
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO activity_devices (id, name, last_seen_at, agent_version)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    last_seen_at = excluded.last_seen_at,
                    agent_version = excluded.agent_version
                """,
                (device.id, device.name, _datetime_text(device.last_seen_at), device.agent_version),
            )
        return device

    def get_device(self, device_id: str) -> Device | None:
        self.ensure_schema()
        with self._connection() as connection:
            row = connection.execute(
                "SELECT id, name, last_seen_at, agent_version "
                "FROM activity_devices WHERE id = ?",
                (device_id,),
            ).fetchone()
        return _device_from_row(row) if row is not None else None

    def list_devices(self) -> tuple[Device, ...]:
        self.ensure_schema()
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT id, name, last_seen_at, agent_version "
                "FROM activity_devices ORDER BY name, id"
            ).fetchall()
        return tuple(_device_from_row(row) for row in rows)

    def upsert_project_source(self, source: ProjectSource) -> ProjectSource:
        self.ensure_schema()
        try:
            with self._connection() as connection:
                connection.execute(
                    """
                    INSERT INTO activity_project_sources
                        (id, project_id, source_type, source_key, device_id, local_path, last_seen_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        project_id = excluded.project_id,
                        source_type = excluded.source_type,
                        source_key = excluded.source_key,
                        device_id = excluded.device_id,
                        local_path = excluded.local_path,
                        last_seen_at = excluded.last_seen_at
                    """,
                    (
                        source.id,
                        source.project_id,
                        source.source_type,
                        source.source_key,
                        source.device_id,
                        source.local_path,
                        _datetime_text(source.last_seen_at),
                    ),
                )
        except sqlite3.IntegrityError as error:
            raise ProjectActivityConflictError("Project source conflicts with existing data") from error
        return source

    def get_project_source(self, source_id: str) -> ProjectSource | None:
        self.ensure_schema()
        with self._connection() as connection:
            row = connection.execute(
                f"{_SOURCE_SELECT} WHERE id = ?", (source_id,)
            ).fetchone()
        return _source_from_row(row) if row is not None else None

    def get_project_source_by_identity(
        self, *, device_id: str | None, source_key: str
    ) -> ProjectSource | None:
        self.ensure_schema()
        where = "device_id = ? AND source_key = ?" if device_id is not None else "device_id IS NULL AND source_key = ?"
        parameters: tuple[object, ...] = (device_id, source_key) if device_id is not None else (source_key,)
        with self._connection() as connection:
            row = connection.execute(f"{_SOURCE_SELECT} WHERE {where}", parameters).fetchone()
        return _source_from_row(row) if row is not None else None

    def list_project_sources(self, project_id: str) -> tuple[ProjectSource, ...]:
        self.ensure_schema()
        with self._connection() as connection:
            rows = connection.execute(
                f"{_SOURCE_SELECT} WHERE project_id = ? ORDER BY last_seen_at DESC, id",
                (project_id,),
            ).fetchall()
        return tuple(_source_from_row(row) for row in rows)

    def upsert_run(self, run: ActivityRun) -> ActivityRun:
        self.ensure_schema()
        try:
            with self._connection() as connection:
                connection.execute(
                    """
                    INSERT INTO activity_runs
                        (project_source_id, run_id, experiment_name, status, created_at,
                         started_at, ended_at, latest_metrics_json, summary_json,
                         config_summary_json, relative_path, has_best_checkpoint, observed_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(project_source_id, run_id) DO UPDATE SET
                        experiment_name = excluded.experiment_name,
                        status = excluded.status,
                        created_at = excluded.created_at,
                        started_at = excluded.started_at,
                        ended_at = excluded.ended_at,
                        latest_metrics_json = excluded.latest_metrics_json,
                        summary_json = excluded.summary_json,
                        config_summary_json = excluded.config_summary_json,
                        relative_path = excluded.relative_path,
                        has_best_checkpoint = excluded.has_best_checkpoint,
                        observed_at = excluded.observed_at
                    """,
                    _run_values(run),
                )
        except sqlite3.IntegrityError as error:
            raise ProjectActivityConflictError("Run conflicts with existing data") from error
        return run

    def get_run(self, project_source_id: str, run_id: str) -> ActivityRun | None:
        self.ensure_schema()
        with self._connection() as connection:
            row = connection.execute(
                f"{_RUN_SELECT} WHERE project_source_id = ? AND run_id = ?",
                (project_source_id, run_id),
            ).fetchone()
        return _run_from_row(row) if row is not None else None

    def list_runs(self, project_id: str) -> tuple[ActivityRun, ...]:
        self.ensure_schema()
        with self._connection() as connection:
            rows = connection.execute(
                f"""{_RUN_SELECT}
                WHERE project_source_id IN (
                    SELECT id FROM activity_project_sources WHERE project_id = ?
                )
                ORDER BY observed_at DESC, project_source_id, run_id""",
                (project_id,),
            ).fetchall()
        return tuple(_run_from_row(row) for row in rows)

    def append_event(self, event: ActivityEvent) -> ActivityEvent:
        self.ensure_schema()
        try:
            with self._connection() as connection:
                connection.execute(
                    """
                    INSERT INTO activity_events
                        (id, project_id, source_id, activity_kind, event_type, occurred_at,
                         subject_type, subject_id, payload_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event.id,
                        event.project_id,
                        event.source_id,
                        event.activity_kind,
                        event.event_type,
                        _datetime_text(event.occurred_at),
                        event.subject_type,
                        event.subject_id,
                        _json_text(event.payload),
                    ),
                )
        except sqlite3.IntegrityError as error:
            raise ProjectActivityConflictError("Event conflicts with existing data") from error
        return event

    def list_events(
        self,
        *,
        project_id: str | None = None,
        source_id: str | None = None,
        activity_kind: str | None = None,
        limit: int = 50,
    ) -> tuple[ActivityEvent, ...]:
        self.ensure_schema()
        clauses: list[str] = []
        parameters: list[object] = []
        if project_id is not None:
            clauses.append("project_id = ?")
            parameters.append(project_id)
        if source_id is not None:
            clauses.append("source_id = ?")
            parameters.append(source_id)
        if activity_kind is not None:
            clauses.append("activity_kind = ?")
            parameters.append(activity_kind)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        parameters.append(limit)
        with self._connection() as connection:
            rows = connection.execute(
                f"{_EVENT_SELECT}{where} ORDER BY occurred_at DESC, id DESC LIMIT ?",
                tuple(parameters),
            ).fetchall()
        return tuple(_event_from_row(row) for row in rows)

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


_SOURCE_SELECT = """
SELECT id, project_id, source_type, source_key, device_id, local_path, last_seen_at
FROM activity_project_sources
"""

_RUN_SELECT = """
SELECT project_source_id, run_id, experiment_name, status, created_at, started_at,
       ended_at, latest_metrics_json, summary_json, config_summary_json,
       relative_path, has_best_checkpoint, observed_at
FROM activity_runs
"""

_EVENT_SELECT = """
SELECT id, project_id, source_id, activity_kind, event_type, occurred_at,
       subject_type, subject_id, payload_json
FROM activity_events
"""


def _device_from_row(row: sqlite3.Row | tuple[object, ...]) -> Device:
    return Device(str(row[0]), str(row[1]), datetime.fromisoformat(str(row[2])), str(row[3]) if row[3] is not None else None)


def _source_from_row(row: sqlite3.Row | tuple[object, ...]) -> ProjectSource:
    return ProjectSource(
        id=str(row[0]), project_id=str(row[1]), source_type=str(row[2]),
        source_key=str(row[3]), device_id=str(row[4]) if row[4] is not None else None,
        local_path=str(row[5]) if row[5] is not None else None,
        last_seen_at=datetime.fromisoformat(str(row[6])),
    )


def _run_values(run: ActivityRun) -> tuple[object, ...]:
    return (
        run.project_source_id, run.run_id, run.experiment_name, run.status,
        _optional_datetime_text(run.created_at), _optional_datetime_text(run.started_at),
        _optional_datetime_text(run.ended_at), _json_text(run.latest_metrics),
        _json_text(run.summary), _json_text(run.config_summary), run.relative_path,
        int(run.has_best_checkpoint), _datetime_text(run.observed_at),
    )


def _run_from_row(row: sqlite3.Row | tuple[object, ...]) -> ActivityRun:
    return ActivityRun(
        project_source_id=str(row[0]), run_id=str(row[1]),
        experiment_name=str(row[2]) if row[2] is not None else None, status=str(row[3]),
        created_at=_optional_datetime(row[4]), started_at=_optional_datetime(row[5]),
        ended_at=_optional_datetime(row[6]), latest_metrics=_optional_json(row[7]),
        summary=_optional_json(row[8]), config_summary=_optional_json(row[9]),
        relative_path=str(row[10]) if row[10] is not None else None,
        has_best_checkpoint=bool(row[11]), observed_at=datetime.fromisoformat(str(row[12])),
    )


def _event_from_row(row: sqlite3.Row | tuple[object, ...]) -> ActivityEvent:
    return ActivityEvent(
        id=str(row[0]), project_id=str(row[1]),
        source_id=str(row[2]) if row[2] is not None else None,
        activity_kind=str(row[3]), event_type=str(row[4]),
        occurred_at=datetime.fromisoformat(str(row[5])),
        subject_type=str(row[6]) if row[6] is not None else None,
        subject_id=str(row[7]) if row[7] is not None else None,
        payload=_optional_json(row[8]),
    )


def _datetime_text(value: datetime) -> str:
    return value.isoformat()


def _optional_datetime_text(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _optional_datetime(value: object) -> datetime | None:
    return datetime.fromisoformat(str(value)) if value is not None else None


def _json_text(value: dict[str, object] | None) -> str | None:
    return json.dumps(value, ensure_ascii=False) if value is not None else None


def _optional_json(value: object) -> dict[str, object] | None:
    return json.loads(str(value)) if value is not None else None


def _sqlite_path(database_url: str) -> str:
    prefix = "sqlite:///"
    if not database_url.startswith(prefix):
        raise ValueError("ProjectActivity repository requires a sqlite:/// database URL")
    return database_url.removeprefix(prefix)
