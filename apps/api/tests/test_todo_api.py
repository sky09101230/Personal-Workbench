from datetime import date, datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.modules.todo.application.service import TodoService
from app.modules.todo.domain.models import PlannerResult, PlannerSuggestion
from app.modules.todo.infrastructure.sqlite import SQLiteTodoRepository


class ApiPlanner:
    task_id: str | None = None

    def plan_day(self, context) -> PlannerResult:
        task_id = self.task_id or context.unfinished_tasks[0].id
        return PlannerResult(
            summary="今天推进一个核心任务",
            items=(PlannerSuggestion(task_id, context.current_date, reason="当前下一步"),),
        )


@pytest.fixture
def todo_client(tmp_path):
    original = app.state.todo_service
    planner = ApiPlanner()
    app.state.todo_service = TodoService(
        SQLiteTodoRepository(f"sqlite:///{(tmp_path / 'api-todo.db').as_posix()}"),
        planner=planner,
        clock=lambda: datetime(2026, 8, 26, 1, 0, tzinfo=timezone.utc),
    )
    try:
        with TestClient(app) as client:
            yield client, planner
    finally:
        app.state.todo_service = original


def test_todo_api_project_task_today_and_detail_workflow(todo_client) -> None:
    client, _ = todo_client
    project = client.post("/api/todo/projects", json={"name": "Workbench", "order": 1})
    assert project.status_code == 201
    project_id = project.json()["id"]
    task = client.post(
        "/api/todo/tasks",
        json={
            "title": "Build Todo",
            "project_id": project_id,
            "planned_date": "2026-08-25",
            "due_date": "2026-08-27",
            "is_next_action": True,
        },
    )
    assert task.status_code == 201

    today = client.get("/api/todo/today")
    detail = client.get(f"/api/todo/projects/{project_id}/detail")

    assert today.status_code == 200
    assert today.json()["carryover"][0]["planned_date"] == "2026-08-25"
    assert today.json()["active_projects"][0]["unfinished_task_count"] == 1
    assert detail.json()["next_action"]["id"] == task.json()["id"]


def test_todo_api_inbox_assignment_completion_and_delete(todo_client) -> None:
    client, _ = todo_client
    project_id = client.post("/api/todo/projects", json={"name": "D2NN"}).json()["id"]
    task_id = client.post("/api/todo/tasks", json={"title": "Capture"}).json()["id"]
    assert client.get("/api/todo/inbox").json()["items"][0]["id"] == task_id

    assigned = client.patch(f"/api/todo/tasks/{task_id}", json={"project_id": project_id})
    assert assigned.status_code == 200
    assert client.get("/api/todo/inbox").json()["items"] == []
    assert client.patch(f"/api/todo/tasks/{task_id}", json={"status": "done"}).status_code == 200
    assert client.get("/api/todo/completed").json()["items"][0]["id"] == task_id
    assert client.delete(f"/api/todo/tasks/{task_id}").status_code == 204


def test_todo_api_plan_proposal_requires_accept_before_task_changes(todo_client) -> None:
    client, _ = todo_client
    task_id = client.post("/api/todo/tasks", json={"title": "Plan me"}).json()["id"]

    generated = client.post("/api/todo/plan-proposals")

    assert generated.status_code == 201
    proposal = generated.json()
    assert client.get(f"/api/todo/tasks/{task_id}").json()["planned_date"] is None
    accepted = client.post(f"/api/todo/plan-proposals/{proposal['id']}/accept")
    assert accepted.status_code == 200
    assert accepted.json()["status"] == "accepted"
    assert client.get(f"/api/todo/tasks/{task_id}").json()["planned_date"] == date(2026, 8, 26).isoformat()
    conflict = client.post(f"/api/todo/plan-proposals/{proposal['id']}/reject")
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "todo_conflict"


def test_todo_api_returns_stable_validation_not_found_and_planner_errors(
    todo_client,
) -> None:
    client, planner = todo_client
    inbox_id = client.post("/api/todo/tasks", json={"title": "Inbox"}).json()["id"]
    invalid = client.patch(f"/api/todo/tasks/{inbox_id}", json={"is_next_action": True})
    assert invalid.status_code == 422
    assert invalid.json()["detail"]["code"] == "todo_validation_error"
    missing = client.get("/api/todo/tasks/missing")
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "todo_not_found"

    planner.task_id = "unknown"
    failed = client.post("/api/todo/plan-proposals")
    assert failed.status_code == 422
    assert client.get(f"/api/todo/tasks/{inbox_id}").json()["title"] == "Inbox"
