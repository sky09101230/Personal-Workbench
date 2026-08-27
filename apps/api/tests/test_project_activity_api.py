from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.modules.project_activity.application.service import ProjectActivityService
from app.modules.project_activity.infrastructure.sqlite import SQLiteProjectActivityRepository


@pytest.fixture
def activity_client(tmp_path, override_service):
    override_service(
        "project_activity_service",
        ProjectActivityService(
            SQLiteProjectActivityRepository(
                f"sqlite:///{(tmp_path / 'activity-api.db').as_posix()}"
            ),
            clock=lambda: datetime(2026, 8, 27, 8, tzinfo=timezone.utc),
        ),
    )
    with TestClient(app) as client:
        yield client


def test_project_activity_ingest_and_query_api_contract(activity_client) -> None:
    heartbeat = activity_client.post(
        "/api/project-activity/devices/heartbeat",
        json={"device_id": "lab-5090", "name": "Lab 5090", "agent_version": "1.0"},
    )
    assert heartbeat.status_code == 200
    assert heartbeat.json()["last_seen_at"] == "2026-08-27T08:00:00+00:00"

    source = activity_client.post(
        "/api/project-activity/sources/observe",
        json={
            "project_id": "opaque-project",
            "source_type": "experiment_workspace",
            "source_key": "device:lab-5090:/data/project",
            "device_id": "lab-5090",
            "local_path": "/data/project",
        },
    )
    assert source.status_code == 200
    source_id = source.json()["id"]

    run = activity_client.post(
        "/api/project-activity/runs/observe",
        json={
            "project_source_id": source_id,
            "run_id": "exp_034",
            "experiment_name": "Baseline",
            "status": "finished",
            "started_at": "2026-08-27T04:00:00Z",
            "ended_at": "2026-08-27T07:00:00Z",
            "latest_metrics": {"iou": 0.83},
            "summary": {"result": "improved"},
            "config_summary": {"loss": "dice"},
            "has_best_checkpoint": True,
        },
    )
    assert run.status_code == 200
    assert run.json()["latest_metrics"] == {"iou": 0.83}

    for kind, minute in (("development", 1), ("experiment", 2), ("system", 3)):
        event = activity_client.post(
            "/api/project-activity/events",
            json={
                "project_id": "opaque-project",
                "source_id": None if kind == "system" else source_id,
                "activity_kind": kind,
                "event_type": f"{kind}_event",
                "occurred_at": f"2026-08-27T08:0{minute}:00Z",
                "subject_type": None if kind == "system" else "run",
                "subject_id": None if kind == "system" else "exp_034",
                "payload": {"kind": kind},
            },
        )
        assert event.status_code == 201

    sources = activity_client.get(
        "/api/project-activity/projects/opaque-project/sources"
    )
    runs = activity_client.get("/api/project-activity/projects/opaque-project/runs")
    events = activity_client.get(
        "/api/project-activity/projects/opaque-project/events?activity_kind=experiment&limit=1"
    )

    assert sources.status_code == 200
    assert sources.json()["items"][0]["source_key"] == "device:lab-5090:/data/project"
    assert runs.status_code == 200
    assert runs.json()["items"][0]["run_id"] == "exp_034"
    assert events.status_code == 200
    assert len(events.json()["items"]) == 1
    assert events.json()["items"][0]["activity_kind"] == "experiment"


def test_project_activity_api_maps_validation_not_found_and_conflict(activity_client) -> None:
    invalid = activity_client.post(
        "/api/project-activity/devices/heartbeat", json={"device_id": "", "name": "Lab"}
    )
    assert invalid.status_code == 422

    missing_device = activity_client.post(
        "/api/project-activity/sources/observe",
        json={
            "project_id": "project-a",
            "source_type": "local_workspace",
            "source_key": "source",
            "device_id": "missing",
        },
    )
    assert missing_device.status_code == 404
    assert missing_device.json()["detail"]["code"] == "project_activity_not_found"

    activity_client.post(
        "/api/project-activity/sources/observe",
        json={
            "project_id": "project-a",
            "source_type": "git_repository",
            "source_key": "github:owner/repo",
        },
    )
    conflict = activity_client.post(
        "/api/project-activity/sources/observe",
        json={
            "project_id": "project-b",
            "source_type": "git_repository",
            "source_key": "github:owner/repo",
        },
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "project_activity_conflict"

    missing_source = activity_client.post(
        "/api/project-activity/runs/observe",
        json={"project_source_id": "missing", "run_id": "run", "status": "running"},
    )
    assert missing_source.status_code == 404
    invalid_limit = activity_client.get(
        "/api/project-activity/projects/project-a/events?limit=0"
    )
    assert invalid_limit.status_code == 422
