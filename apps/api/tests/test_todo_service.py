from datetime import date, datetime, timezone

import pytest

from app.modules.todo.application.errors import TodoValidationError
from app.modules.todo.application.service import TodoService
from app.modules.todo.domain.models import ProjectStatus, TaskPriority, TaskStatus
from app.modules.todo.infrastructure.sqlite import SQLiteTodoRepository


FIXED_NOW = datetime(2026, 8, 26, 1, 0, tzinfo=timezone.utc)


@pytest.fixture
def service(tmp_path) -> TodoService:
    repository = SQLiteTodoRepository(f"sqlite:///{(tmp_path / 'todo.db').as_posix()}")
    return TodoService(repository, clock=lambda: FIXED_NOW)


def test_project_crud_status_order_and_delete_preserves_tasks(service: TodoService) -> None:
    first = service.create_project(name="D2NN", description="Optical experiments", completed_items=("Baseline",), order=2)
    second = service.create_project(name="Workbench", order=1)
    task = service.create_task(title="Keep me", project_id=first.id, is_next_action=True)

    assert [project.id for project in service.list_projects()] == [second.id, first.id]
    assert first.description == "Optical experiments"
    assert first.completed_items == ("Baseline",)
    paused = service.update_project(first.id, {"status": "paused", "order": 0})
    assert paused.status is ProjectStatus.PAUSED
    assert [project.id for project in service.list_projects(status=ProjectStatus.ACTIVE)] == [second.id]

    service.delete_project(first.id)

    preserved = service.get_task(task.id)
    assert preserved.project_id is None
    assert preserved.is_next_action is False
    assert [item.id for item in service.inbox()] == [task.id]


def test_task_crud_keeps_planned_and_due_dates_independent(service: TodoService) -> None:
    planned = service.create_task(title="Planned", planned_date=date(2026, 8, 27))
    due = service.create_task(title="Due", due_date=date(2026, 8, 28))

    assert planned.planned_date == date(2026, 8, 27)
    assert planned.due_date is None
    assert due.due_date == date(2026, 8, 28)
    assert due.planned_date is None

    done = service.update_task(planned.id, {"status": "done", "priority": "high"})
    assert done.status is TaskStatus.DONE
    assert done.priority is TaskPriority.HIGH
    assert done.completed_at == FIXED_NOW
    reopened = service.update_task(planned.id, {"status": "doing"})
    assert reopened.status is TaskStatus.DOING
    assert reopened.completed_at is None

    service.delete_task(due.id)
    assert {task.id for task in service.list_tasks()} == {planned.id}


def test_inbox_contains_only_unassigned_unfinished_tasks(service: TodoService) -> None:
    project = service.create_project(name="D2NN")
    inbox_task = service.create_task(title="Capture")
    done_task = service.create_task(title="Done")
    service.update_task(done_task.id, {"status": "done"})

    assert [task.id for task in service.inbox()] == [inbox_task.id]
    assigned = service.update_task(inbox_task.id, {"project_id": project.id})
    assert assigned.project_id == project.id
    assert service.inbox() == ()


def test_setting_next_action_atomically_replaces_previous_task(service: TodoService) -> None:
    project = service.create_project(name="Workbench")
    first = service.create_task(title="First", project_id=project.id, is_next_action=True)
    second = service.create_task(title="Second", project_id=project.id)

    service.update_task(second.id, {"is_next_action": True})

    assert service.get_task(first.id).is_next_action is False
    assert service.get_task(second.id).is_next_action is True
    with pytest.raises(TodoValidationError):
        service.create_task(title="Inbox next", is_next_action=True)
    service.update_task(second.id, {"status": "done"})
    assert service.today().active_projects[0].next_action is None


def test_today_queries_carryover_without_mutating_dates_and_counts_projects(
    service: TodoService,
) -> None:
    active = service.create_project(name="Active", order=1)
    empty = service.create_project(name="Empty", order=2)
    paused = service.create_project(name="Paused", status=ProjectStatus.PAUSED)
    carryover = service.create_task(
        title="Yesterday",
        project_id=active.id,
        planned_date=date(2026, 8, 25),
        is_next_action=True,
    )
    today_task = service.create_task(
        title="Today",
        project_id=active.id,
        planned_date=date(2026, 8, 26),
    )
    service.create_task(title="Paused task", project_id=paused.id)

    view = service.today()

    assert view.date == date(2026, 8, 26)
    assert [task.id for task in view.carryover] == [carryover.id]
    assert [task.id for task in view.planned_today] == [today_task.id]
    assert service.get_task(carryover.id).planned_date == date(2026, 8, 25)
    assert [overview.project.id for overview in view.active_projects] == [active.id, empty.id]
    assert [overview.unfinished_task_count for overview in view.active_projects] == [2, 0]
    assert view.active_projects[0].next_action.id == carryover.id


def test_upcoming_and_completed_queries_keep_explicit_status_semantics(
    service: TodoService,
) -> None:
    future_planned = service.create_task(
        title="Future planned",
        planned_date=date(2026, 8, 27),
    )
    future_due = service.create_task(title="Future due", due_date=date(2026, 8, 28))
    past_due = service.create_task(title="Past due", due_date=date(2026, 8, 25))
    done = service.create_task(title="Done")
    cancelled = service.create_task(title="Cancelled")
    service.update_task(done.id, {"status": "done"})
    service.update_task(cancelled.id, {"status": "cancelled"})

    upcoming_ids = [task.id for task in service.upcoming()]
    completed_ids = [task.id for task in service.completed()]

    assert upcoming_ids == [future_planned.id, future_due.id]
    assert past_due.id not in upcoming_ids
    assert completed_ids == [done.id]
