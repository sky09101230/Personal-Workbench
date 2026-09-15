from app.core.task_repository import SQLiteTaskRepository
from app.core.tasks import TaskSnapshot, TaskStatus


def test_task_repository_round_trips_snapshot(tmp_path) -> None:
    repo = SQLiteTaskRepository(f"sqlite:///{(tmp_path / 'tasks.db').as_posix()}")
    snapshot = TaskSnapshot.new("t1", "news.refresh")
    repo.save(snapshot)
    loaded = repo.get("t1")
    assert loaded is not None
    assert loaded.status is TaskStatus.PENDING
    assert loaded.operation == "news.refresh"


def test_task_repository_marks_orphaned_running_tasks_failed(tmp_path) -> None:
    repo = SQLiteTaskRepository(f"sqlite:///{(tmp_path / 'tasks.db').as_posix()}")
    snapshot = TaskSnapshot.new("t1", "news.refresh")
    repo.save(TaskSnapshot(snapshot.id, snapshot.operation, TaskStatus.RUNNING, snapshot.created_at, snapshot.updated_at))
    assert repo.mark_interrupted() == 1
    assert repo.get("t1").error_code == "process_interrupted"
