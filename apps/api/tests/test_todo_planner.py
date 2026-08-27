import json
from datetime import date, datetime, timezone

import httpx
import pytest

from app.core.config import Settings
from app.modules.todo.application.errors import (
    TodoConflictError,
    TodoPlannerError,
    TodoPlannerUnavailableError,
    TodoValidationError,
)
from app.modules.todo.application.service import TodoService
from app.modules.todo.domain.models import (
    PlannerContext,
    PlannerResult,
    PlannerSuggestion,
    Project,
    ProjectStatus,
    Task,
    TaskStatus,
)
from app.modules.todo.infrastructure.planners.deepseek import DeepSeekTodoPlanner
from app.modules.todo.infrastructure.sqlite import SQLiteTodoRepository


FIXED_NOW = datetime(2026, 8, 26, 1, 0, tzinfo=timezone.utc)


class StubPlanner:
    def __init__(self, result: PlannerResult | Exception) -> None:
        self.result = result
        self.context: PlannerContext | None = None

    def plan_day(self, context: PlannerContext) -> PlannerResult:
        self.context = context
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def _service(tmp_path, planner: StubPlanner) -> TodoService:
    repository = SQLiteTodoRepository(f"sqlite:///{(tmp_path / 'todo.db').as_posix()}")
    return TodoService(repository, planner=planner, clock=lambda: FIXED_NOW)


def test_generate_proposal_receives_context_without_mutating_task(tmp_path) -> None:
    planner = StubPlanner(PlannerResult(summary="推进核心工作", items=()))
    service = _service(tmp_path, planner)
    project = service.create_project(name="Workbench")
    task = service.create_task(
        title="Build Todo",
        project_id=project.id,
        due_date=date(2026, 8, 27),
        planned_date=date(2026, 8, 25),
        is_next_action=True,
    )
    planner.result = PlannerResult(
        summary="推进核心工作",
        items=(
            PlannerSuggestion(
                task_id=task.id,
                suggested_planned_date=date(2026, 8, 26),
                reason="这是当前 Next Action",
            ),
        ),
    )

    proposal = service.generate_plan()

    assert proposal.status.value == "pending"
    assert service.get_task(task.id).planned_date == date(2026, 8, 25)
    assert planner.context is not None
    assert planner.context.active_projects == (project,)
    assert [item.id for item in planner.context.carryover_tasks] == [task.id]
    assert [item.id for item in planner.context.next_actions] == [task.id]


def test_accept_and_reject_are_explicit_one_time_decisions(tmp_path) -> None:
    planner = StubPlanner(PlannerResult(summary=None, items=()))
    service = _service(tmp_path, planner)
    task = service.create_task(title="Plan me")
    planner.result = PlannerResult(
        summary="安排今天",
        items=(
            PlannerSuggestion(
                task_id=task.id,
                suggested_planned_date=date(2026, 8, 26),
            ),
        ),
    )

    accepted = service.accept_proposal(service.generate_plan().id)
    assert accepted.status.value == "accepted"
    assert service.get_task(task.id).planned_date == date(2026, 8, 26)
    with pytest.raises(TodoConflictError):
        service.reject_proposal(accepted.id)

    second = service.generate_plan()
    rejected = service.reject_proposal(second.id)
    assert rejected.status.value == "rejected"
    with pytest.raises(TodoConflictError):
        service.accept_proposal(rejected.id)


def test_accept_rolls_back_all_changes_if_one_task_is_no_longer_valid(tmp_path) -> None:
    planner = StubPlanner(PlannerResult(summary=None, items=()))
    service = _service(tmp_path, planner)
    first = service.create_task(title="First")
    second = service.create_task(title="Second")
    planner.result = PlannerResult(
        summary=None,
        items=(
            PlannerSuggestion(first.id, date(2026, 8, 26)),
            PlannerSuggestion(second.id, date(2026, 8, 26)),
        ),
    )
    proposal = service.generate_plan()
    service.delete_task(second.id)

    with pytest.raises(TodoConflictError):
        service.accept_proposal(proposal.id)

    assert service.get_task(first.id).planned_date is None
    assert service.get_proposal(proposal.id).status.value == "pending"


def test_invalid_or_failing_planner_does_not_change_existing_tasks(tmp_path) -> None:
    planner = StubPlanner(
        PlannerResult(
            summary=None,
            items=(PlannerSuggestion("unknown", date(2026, 8, 26)),),
        )
    )
    service = _service(tmp_path, planner)
    task = service.create_task(title="Preserved")
    with pytest.raises(TodoValidationError):
        service.generate_plan()
    assert service.get_task(task.id) == task

    planner.result = TodoPlannerError("provider failed")
    with pytest.raises(TodoPlannerError):
        service.generate_plan()
    assert service.get_task(task.id) == task


def test_deepseek_planner_parses_structured_response_and_rejects_unconfigured() -> None:
    context = _planner_context()

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["model"] == "deepseek-test"
        assert context.unfinished_tasks[0].id in body["messages"][1]["content"]
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "summary": "今天推进 Workbench",
                                    "items": [
                                        {
                                            "task_id": context.unfinished_tasks[0].id,
                                            "suggested_planned_date": "2026-08-26",
                                            "suggested_priority": "high",
                                            "reason": "核心下一步",
                                        }
                                    ],
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ]
            },
        )

    settings = Settings(
        "sqlite:///unused.db",
        ["http://localhost:5173"],
        "",
        "",
        deepseek_api_key="secret",
        deepseek_base_url="https://deepseek.invalid",
        deepseek_model="deepseek-test",
    )
    planner = DeepSeekTodoPlanner(settings, httpx.Client(transport=httpx.MockTransport(handler)))
    result = planner.plan_day(context)
    assert result.items[0].suggested_priority.value == "high"

    unavailable = DeepSeekTodoPlanner(
        Settings("sqlite:///unused.db", [], "", ""),
        httpx.Client(transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(TodoPlannerUnavailableError):
        unavailable.plan_day(context)


def _planner_context() -> PlannerContext:
    project = Project(
        id="project-1",
        name="Workbench",
        description=None,
        completed_items=(),
        status=ProjectStatus.ACTIVE,
        order=0,
        created_at=FIXED_NOW,
        updated_at=FIXED_NOW,
    )
    task = Task(
        id="task-1",
        project_id=project.id,
        title="Build Todo",
        description=None,
        status=TaskStatus.TODO,
        priority=None,
        due_date=None,
        planned_date=None,
        is_next_action=True,
        created_at=FIXED_NOW,
        updated_at=FIXED_NOW,
        completed_at=None,
    )
    return PlannerContext(
        current_datetime=FIXED_NOW,
        current_date=date(2026, 8, 26),
        active_projects=(project,),
        unfinished_tasks=(task,),
        carryover_tasks=(),
        planned_today_tasks=(),
        next_actions=(task,),
    )
