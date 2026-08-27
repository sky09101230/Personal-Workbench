from collections.abc import Callable
from datetime import datetime, timezone
from uuid import uuid4

from app.modules.project_activity.application.errors import (
    ProjectActivityConflictError,
    ProjectActivityNotFoundError,
    ProjectActivityValidationError,
)
from app.modules.project_activity.application.ports import ProjectActivityRepository
from app.modules.project_activity.domain.models import (
    ActivityEvent,
    ActivityRun,
    Device,
    ProjectSource,
)


class ProjectActivityService:
    def __init__(
        self,
        repository: ProjectActivityRepository,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self.repository = repository
        self.clock = clock

    def heartbeat_device(
        self, *, device_id: str, name: str, agent_version: str | None = None
    ) -> Device:
        device = Device(
            id=_required_text(device_id, "Device id"),
            name=_required_text(name, "Device name"),
            last_seen_at=self._now(),
            agent_version=_optional_text(agent_version),
        )
        return self.repository.upsert_device(device)

    def get_device(self, device_id: str) -> Device:
        device = self.repository.get_device(_required_text(device_id, "Device id"))
        if device is None:
            raise ProjectActivityNotFoundError("Device was not found")
        return device

    def list_devices(self) -> tuple[Device, ...]:
        return self.repository.list_devices()

    def observe_project_source(
        self,
        *,
        project_id: str,
        source_type: str,
        source_key: str,
        device_id: str | None = None,
        local_path: str | None = None,
    ) -> ProjectSource:
        project_id = _required_text(project_id, "Project id")
        source_key = _required_text(source_key, "Source key")
        device_id = _optional_text(device_id)
        if device_id is not None and self.repository.get_device(device_id) is None:
            raise ProjectActivityNotFoundError("Device was not found")
        existing = self.repository.get_project_source_by_identity(
            device_id=device_id, source_key=source_key
        )
        if existing is not None and existing.project_id != project_id:
            raise ProjectActivityConflictError(
                "Project source identity belongs to another project"
            )
        source = ProjectSource(
            id=existing.id if existing is not None else str(uuid4()),
            project_id=project_id,
            source_type=_required_text(source_type, "Source type"),
            source_key=source_key,
            device_id=device_id,
            local_path=_optional_text(local_path),
            last_seen_at=self._now(),
        )
        return self.repository.upsert_project_source(source)

    def observe_run(
        self,
        *,
        project_source_id: str,
        run_id: str,
        status: str,
        experiment_name: str | None = None,
        created_at: datetime | None = None,
        started_at: datetime | None = None,
        ended_at: datetime | None = None,
        latest_metrics: dict[str, object] | None = None,
        summary: dict[str, object] | None = None,
        config_summary: dict[str, object] | None = None,
        relative_path: str | None = None,
        has_best_checkpoint: bool = False,
    ) -> ActivityRun:
        project_source_id = _required_text(project_source_id, "Project source id")
        if self.repository.get_project_source(project_source_id) is None:
            raise ProjectActivityNotFoundError("Project source was not found")
        run = ActivityRun(
            project_source_id=project_source_id,
            run_id=_required_text(run_id, "Run id"),
            experiment_name=_optional_text(experiment_name),
            status=_required_text(status, "Run status"),
            created_at=created_at,
            started_at=started_at,
            ended_at=ended_at,
            latest_metrics=latest_metrics,
            summary=summary,
            config_summary=config_summary,
            relative_path=_optional_text(relative_path),
            has_best_checkpoint=has_best_checkpoint,
            observed_at=self._now(),
        )
        return self.repository.upsert_run(run)

    def record_event(
        self,
        *,
        project_id: str,
        activity_kind: str,
        event_type: str,
        occurred_at: datetime | None = None,
        source_id: str | None = None,
        subject_type: str | None = None,
        subject_id: str | None = None,
        payload: dict[str, object] | None = None,
    ) -> ActivityEvent:
        project_id = _required_text(project_id, "Project id")
        source_id = _optional_text(source_id)
        if source_id is not None:
            source = self.repository.get_project_source(source_id)
            if source is None:
                raise ProjectActivityNotFoundError("Project source was not found")
            if source.project_id != project_id:
                raise ProjectActivityConflictError(
                    "Project source belongs to another project"
                )
        event = ActivityEvent(
            id=str(uuid4()),
            project_id=project_id,
            source_id=source_id,
            activity_kind=_required_text(activity_kind, "Activity kind"),
            event_type=_required_text(event_type, "Event type"),
            occurred_at=occurred_at or self._now(),
            subject_type=_optional_text(subject_type),
            subject_id=_optional_text(subject_id),
            payload=payload,
        )
        return self.repository.append_event(event)

    def get_project_sources(self, project_id: str) -> tuple[ProjectSource, ...]:
        return self.repository.list_project_sources(_required_text(project_id, "Project id"))

    def get_project_runs(self, project_id: str) -> tuple[ActivityRun, ...]:
        return self.repository.list_runs(_required_text(project_id, "Project id"))

    def get_recent_activity(
        self,
        project_id: str,
        *,
        activity_kind: str | None = None,
        limit: int = 50,
    ) -> tuple[ActivityEvent, ...]:
        if limit < 1 or limit > 200:
            raise ProjectActivityValidationError("Limit must be between 1 and 200")
        return self.repository.list_events(
            project_id=_required_text(project_id, "Project id"),
            activity_kind=_optional_text(activity_kind),
            limit=limit,
        )

    def _now(self) -> datetime:
        value = self.clock()
        if value.tzinfo is None:
            raise ProjectActivityValidationError("Clock must return a timezone-aware datetime")
        return value


def _required_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProjectActivityValidationError(f"{label} is required")
    return value.strip()


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ProjectActivityValidationError("Optional text value is invalid")
    return value.strip() or None
