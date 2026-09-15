from datetime import timezone

from app.core.errors import ErrorEnvelope
from app.core.tasks import LocalTaskRegistry, TaskSnapshot, TaskStatus


def test_error_envelope_is_stable_json_shape() -> None:
    assert ErrorEnvelope("provider_timeout", "retry later", True).as_dict() == {
        "code": "provider_timeout",
        "message": "retry later",
        "retryable": True,
    }


def test_task_snapshot_starts_pending_with_utc_timestamps() -> None:
    snapshot = TaskSnapshot.new("task-1", "news.refresh")
    assert snapshot.status is TaskStatus.PENDING
    assert snapshot.created_at.tzinfo is timezone.utc
    assert snapshot.updated_at >= snapshot.created_at


def test_local_task_registry_captures_success_and_failure() -> None:
    registry = LocalTaskRegistry()
    registry.submit("ok", "demo", lambda: "result")
    registry.submit("bad", "demo", lambda: (_ for _ in ()).throw(ValueError("bad")))
    import time

    for _ in range(50):
        if all(registry.get(task_id).status in {TaskStatus.SUCCEEDED, TaskStatus.FAILED} for task_id in ("ok", "bad")):
            break
        time.sleep(0.01)
    assert registry.get("ok").result_ref == "result"
    assert registry.get("bad").error_code == "ValueError"
