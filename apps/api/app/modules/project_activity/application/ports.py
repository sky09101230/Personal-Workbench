from typing import Protocol

from app.modules.project_activity.domain.models import (
    ActivityEvent,
    ActivityRun,
    Device,
    ProjectSource,
)


class ProjectActivityRepository(Protocol):
    def upsert_device(self, device: Device) -> Device:
        ...

    def get_device(self, device_id: str) -> Device | None:
        ...

    def list_devices(self) -> tuple[Device, ...]:
        ...

    def upsert_project_source(self, source: ProjectSource) -> ProjectSource:
        ...

    def get_project_source(self, source_id: str) -> ProjectSource | None:
        ...

    def get_project_source_by_identity(
        self, *, device_id: str | None, source_key: str
    ) -> ProjectSource | None:
        ...

    def list_project_sources(self, project_id: str) -> tuple[ProjectSource, ...]:
        ...

    def upsert_run(self, run: ActivityRun) -> ActivityRun:
        ...

    def get_run(self, project_source_id: str, run_id: str) -> ActivityRun | None:
        ...

    def list_runs(self, project_id: str) -> tuple[ActivityRun, ...]:
        ...

    def append_event(self, event: ActivityEvent) -> ActivityEvent:
        ...

    def list_events(
        self,
        *,
        project_id: str | None = None,
        source_id: str | None = None,
        activity_kind: str | None = None,
        limit: int = 50,
    ) -> tuple[ActivityEvent, ...]:
        ...
