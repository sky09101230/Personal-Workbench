import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from app.modules.project_activity.application.errors import (
    ProjectActivityConflictError,
    ProjectActivityNotFoundError,
    ProjectActivityValidationError,
)
from app.modules.project_activity.application.service import ProjectActivityService
from app.modules.project_activity.domain.models import ActivityEvent
from app.modules.project_activity.infrastructure.sqlite import SQLiteProjectActivityRepository


@pytest.fixture
def activity(tmp_path):
    database_path = tmp_path / "activity.db"
    repository = SQLiteProjectActivityRepository(
        f"sqlite:///{database_path.as_posix()}"
    )
    times = iter(
        datetime(2026, 8, 27, hour, tzinfo=timezone.utc) for hour in range(20)
    )
    service = ProjectActivityService(repository, clock=lambda: next(times))
    return service, repository, database_path


def test_schema_v1_is_idempotent_and_owns_expected_tables_and_indexes(activity) -> None:
    _, repository, database_path = activity
    assert repository.ensure_schema().version == 1
    assert repository.ensure_schema().version == 1

    with sqlite3.connect(database_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        indexes = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            )
        }
        migrations = connection.execute(
            "SELECT version FROM activity_schema_migrations"
        ).fetchall()

    assert tables == {
        "activity_schema_migrations",
        "activity_devices",
        "activity_project_sources",
        "activity_runs",
        "activity_events",
    }
    assert {
        "activity_project_sources_project_idx",
        "activity_project_sources_device_idx",
        "activity_events_project_time_idx",
        "activity_events_source_time_idx",
        "activity_events_kind_time_idx",
    }.issubset(indexes)
    assert migrations == [(1,)]


def test_device_heartbeat_updates_without_duplicate(activity) -> None:
    service, _, _ = activity
    first = service.heartbeat_device(
        device_id="lab-5090", name="Lab 5090", agent_version="1.0"
    )
    second = service.heartbeat_device(
        device_id="lab-5090", name="Lab 5090", agent_version="1.1"
    )

    assert second.id == first.id
    assert second.last_seen_at > first.last_seen_at
    assert second.agent_version == "1.1"
    assert service.list_devices() == (second,)


def test_source_observation_upserts_and_supports_projects_and_devices(activity) -> None:
    service, _, _ = activity
    service.heartbeat_device(device_id="lab", name="Lab")
    service.heartbeat_device(device_id="local", name="Local")

    first = service.observe_project_source(
        project_id="project-a",
        source_type="local_workspace",
        source_key="checkout:semantic",
        device_id="lab",
        local_path="/data/semantic",
    )
    updated = service.observe_project_source(
        project_id="project-a",
        source_type="experiment_workspace",
        source_key="checkout:semantic",
        device_id="lab",
        local_path="/data/semantic-v2",
    )
    same_key_other_device = service.observe_project_source(
        project_id="project-a",
        source_type="local_workspace",
        source_key="checkout:semantic",
        device_id="local",
        local_path="D:/semantic",
    )
    another_project = service.observe_project_source(
        project_id="project-b",
        source_type="git_repository",
        source_key="github:owner/other",
        device_id="lab",
    )

    assert updated.id == first.id
    assert updated.local_path == "/data/semantic-v2"
    assert same_key_other_device.id != first.id
    assert another_project.device_id == "lab"
    assert {source.id for source in service.get_project_sources("project-a")} == {
        first.id,
        same_key_other_device.id,
    }

    with pytest.raises(ProjectActivityConflictError):
        service.observe_project_source(
            project_id="project-c",
            source_type="local_workspace",
            source_key="checkout:semantic",
            device_id="lab",
        )
    with pytest.raises(ProjectActivityNotFoundError):
        service.observe_project_source(
            project_id="project-a",
            source_type="local_workspace",
            source_key="missing-device-source",
            device_id="missing",
        )


def test_run_observation_upserts_round_trips_json_and_scopes_identity(activity) -> None:
    service, repository, _ = activity
    source_a = service.observe_project_source(
        project_id="project-a", source_type="experiment_workspace", source_key="a"
    )
    source_b = service.observe_project_source(
        project_id="project-a", source_type="experiment_workspace", source_key="b"
    )
    lifecycle_time = datetime(2026, 8, 26, 12, tzinfo=timezone.utc)

    service.observe_run(
        project_source_id=source_a.id,
        run_id="exp_001",
        experiment_name="Baseline",
        status="running",
        created_at=lifecycle_time,
        started_at=lifecycle_time + timedelta(minutes=1),
        latest_metrics={"loss": 0.2, "nested": {"epoch": 3}},
        summary={"note": "稳定"},
        config_summary={"lr": 0.001},
        relative_path="runs/exp_001",
    )
    updated = service.observe_run(
        project_source_id=source_a.id,
        run_id="exp_001",
        status="finished",
        ended_at=lifecycle_time + timedelta(hours=2),
        latest_metrics={"iou": 0.83},
        summary={"best": True},
        config_summary={"model": "unet"},
        has_best_checkpoint=True,
    )
    other = service.observe_run(
        project_source_id=source_b.id, run_id="exp_001", status="running"
    )

    stored = repository.get_run(source_a.id, "exp_001")
    assert stored == updated
    assert stored.latest_metrics == {"iou": 0.83}
    assert stored.summary == {"best": True}
    assert stored.config_summary == {"model": "unet"}
    assert stored.has_best_checkpoint is True
    assert {run.project_source_id for run in service.get_project_runs("project-a")} == {
        source_a.id,
        source_b.id,
    }
    assert other.run_id == updated.run_id

    with pytest.raises(ProjectActivityNotFoundError):
        service.observe_run(project_source_id="missing", run_id="run", status="running")


def test_events_are_append_only_open_typed_ordered_filtered_and_limited(activity) -> None:
    service, repository, _ = activity
    source = service.observe_project_source(
        project_id="project-a", source_type="experiment_workspace", source_key="source-a"
    )
    base = datetime(2026, 8, 27, tzinfo=timezone.utc)
    kinds = ("development", "experiment", "knowledge", "literature", "system")
    recorded = []
    for offset, kind in enumerate(kinds):
        recorded.append(
            service.record_event(
                project_id="project-a",
                source_id=source.id if kind != "system" else None,
                activity_kind=kind,
                event_type=f"{kind}_happened",
                occurred_at=base + timedelta(minutes=offset),
                subject_type=None if kind == "system" else "run",
                subject_id=None if kind == "system" else f"exp_{offset}",
                payload={"kind": kind, "score": 0.83},
            )
        )

    recent = service.get_recent_activity("project-a", limit=3)
    assert [event.activity_kind for event in recent] == ["system", "literature", "knowledge"]
    experiment = service.get_recent_activity(
        "project-a", activity_kind="experiment", limit=10
    )
    assert experiment == (recorded[1],)
    assert experiment[0].payload == {"kind": "experiment", "score": 0.83}
    assert repository.list_events(source_id=source.id, limit=20) == tuple(
        reversed(recorded[:-1])
    )
    assert recorded[-1].subject_type is None
    assert recorded[-1].subject_id is None

    duplicate = ActivityEvent(**{**recorded[0].__dict__})
    with pytest.raises(ProjectActivityConflictError):
        repository.append_event(duplicate)


def test_run_observation_does_not_create_event_and_validation_is_stable(activity) -> None:
    service, _, _ = activity
    source = service.observe_project_source(
        project_id="project-a", source_type="experiment_workspace", source_key="source-a"
    )
    service.observe_run(project_source_id=source.id, run_id="run", status="running")
    service.observe_run(project_source_id=source.id, run_id="run", status="finished")
    assert service.get_recent_activity("project-a") == ()

    with pytest.raises(ProjectActivityValidationError):
        service.heartbeat_device(device_id=" ", name="Device")
    with pytest.raises(ProjectActivityValidationError):
        service.get_recent_activity("project-a", limit=0)


def test_repository_rejects_non_sqlite_database_urls() -> None:
    with pytest.raises(ValueError, match="sqlite"):
        SQLiteProjectActivityRepository("postgresql://localhost/workbench")
