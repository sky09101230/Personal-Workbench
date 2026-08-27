from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Device:
    id: str
    name: str
    last_seen_at: datetime
    agent_version: str | None


@dataclass(frozen=True)
class ProjectSource:
    id: str
    project_id: str
    source_type: str
    source_key: str
    device_id: str | None
    local_path: str | None
    last_seen_at: datetime


@dataclass(frozen=True)
class ActivityEvent:
    id: str
    project_id: str
    source_id: str | None
    activity_kind: str
    event_type: str
    occurred_at: datetime
    subject_type: str | None
    subject_id: str | None
    payload: dict[str, object] | None


@dataclass(frozen=True)
class ActivityRun:
    project_source_id: str
    run_id: str
    experiment_name: str | None
    status: str
    created_at: datetime | None
    started_at: datetime | None
    ended_at: datetime | None
    latest_metrics: dict[str, object] | None
    summary: dict[str, object] | None
    config_summary: dict[str, object] | None
    relative_path: str | None
    has_best_checkpoint: bool
    observed_at: datetime
