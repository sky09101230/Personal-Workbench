"""Shared lifecycle types for long-running local work."""

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from typing import Callable


class TaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class TaskSnapshot:
    id: str
    operation: str
    status: TaskStatus
    created_at: datetime
    updated_at: datetime
    error_code: str | None = None
    result_ref: str | None = None

    @classmethod
    def new(cls, task_id: str, operation: str) -> "TaskSnapshot":
        now = datetime.now(timezone.utc)
        return cls(task_id, operation, TaskStatus.PENDING, now, now)


class LocalTaskRegistry:
    """Small process-local executor; storage can be replaced without changing callers."""

    def __init__(self, workers: int = 2) -> None:
        self._executor = ThreadPoolExecutor(max_workers=workers)
        self._tasks: dict[str, TaskSnapshot] = {}
        self._lock = Lock()

    def submit(self, task_id: str, operation: str, work: Callable[[], str | None]) -> TaskSnapshot:
        snapshot = TaskSnapshot.new(task_id, operation)
        with self._lock:
            self._tasks[task_id] = snapshot
        self._executor.submit(self._run, snapshot, work)
        return snapshot

    def get(self, task_id: str) -> TaskSnapshot | None:
        with self._lock:
            return self._tasks.get(task_id)

    def _run(self, snapshot: TaskSnapshot, work: Callable[[], str | None]) -> None:
        self._replace(snapshot, status=TaskStatus.RUNNING)
        try:
            self._replace(snapshot, status=TaskStatus.SUCCEEDED, result_ref=work())
        except Exception as error:  # noqa: BLE001 - task boundary captures failures
            self._replace(snapshot, status=TaskStatus.FAILED, error_code=type(error).__name__)

    def _replace(self, snapshot: TaskSnapshot, **changes: object) -> None:
        from dataclasses import replace

        with self._lock:
            self._tasks[snapshot.id] = replace(
                self._tasks[snapshot.id], updated_at=datetime.now(timezone.utc), **changes
            )
