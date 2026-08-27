from dataclasses import asdict
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Body, Depends, Query, Request, Response, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.modules.todo.application.errors import (
    TodoConflictError,
    TodoError,
    TodoNotFoundError,
    TodoPlannerError,
    TodoPlannerUnavailableError,
    TodoValidationError,
)
from app.modules.todo.application.service import TodoService
from app.modules.todo.domain.models import ProjectStatus, TaskPriority, TaskStatus


router = APIRouter()


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    completed_items: list[str] = Field(default_factory=list, max_length=100)
    status: ProjectStatus = ProjectStatus.ACTIVE
    order: int = 0


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    completed_items: list[str] | None = Field(default=None, max_length=100)
    status: ProjectStatus | None = None
    order: int | None = None


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    project_id: str | None = None
    description: str | None = Field(default=None, max_length=10_000)
    status: TaskStatus = TaskStatus.TODO
    priority: TaskPriority | None = None
    due_date: date | None = None
    planned_date: date | None = None
    is_next_action: bool = False


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    project_id: str | None = None
    description: str | None = Field(default=None, max_length=10_000)
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    due_date: date | None = None
    planned_date: date | None = None
    is_next_action: bool | None = None


def get_todo_service(request: Request) -> TodoService:
    return request.app.state.todo_service


async def todo_error_handler(_: Request, error: TodoError) -> JSONResponse:
    if isinstance(error, TodoNotFoundError):
        http_status = 404
    elif isinstance(error, TodoValidationError):
        http_status = 422
    elif isinstance(error, TodoConflictError):
        http_status = 409
    elif isinstance(error, TodoPlannerUnavailableError):
        http_status = 503
    elif isinstance(error, TodoPlannerError):
        http_status = 502
    else:
        http_status = 500
    return JSONResponse(
        status_code=http_status,
        content={"detail": {"code": error.code, "message": str(error)}},
    )


@router.get("/projects")
def list_projects(
    project_status: Annotated[ProjectStatus | None, Query(alias="status")] = None,
    service: TodoService = Depends(get_todo_service),
) -> dict[str, object]:
    return {"items": _json(service.list_projects(status=project_status))}


@router.post("/projects", status_code=status.HTTP_201_CREATED)
def create_project(
    request: ProjectCreate,
    service: TodoService = Depends(get_todo_service),
) -> object:
    return _json(service.create_project(**request.model_dump()))


@router.get("/projects/{project_id}/detail")
def get_project_detail(
    project_id: str,
    service: TodoService = Depends(get_todo_service),
) -> object:
    return _json(service.project_detail(project_id))


@router.get("/projects/{project_id}")
def get_project(
    project_id: str,
    service: TodoService = Depends(get_todo_service),
) -> object:
    return _json(service.get_project(project_id))


@router.patch("/projects/{project_id}")
def update_project(
    project_id: str,
    request: ProjectUpdate,
    service: TodoService = Depends(get_todo_service),
) -> object:
    return _json(service.update_project(project_id, request.model_dump(exclude_unset=True)))


@router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: str,
    service: TodoService = Depends(get_todo_service),
) -> Response:
    service.delete_project(project_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/tasks")
def list_tasks(service: TodoService = Depends(get_todo_service)) -> dict[str, object]:
    return {"items": _json(service.list_tasks())}


@router.post("/tasks", status_code=status.HTTP_201_CREATED)
def create_task(
    request: TaskCreate,
    service: TodoService = Depends(get_todo_service),
) -> object:
    return _json(service.create_task(**request.model_dump()))


@router.get("/tasks/{task_id}")
def get_task(
    task_id: str,
    service: TodoService = Depends(get_todo_service),
) -> object:
    return _json(service.get_task(task_id))


@router.patch("/tasks/{task_id}")
def update_task(
    task_id: str,
    request: TaskUpdate,
    service: TodoService = Depends(get_todo_service),
) -> object:
    return _json(service.update_task(task_id, request.model_dump(exclude_unset=True)))


@router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(
    task_id: str,
    service: TodoService = Depends(get_todo_service),
) -> Response:
    service.delete_task(task_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/inbox")
def inbox(service: TodoService = Depends(get_todo_service)) -> dict[str, object]:
    return {"items": _json(service.inbox())}


@router.get("/today")
def today(service: TodoService = Depends(get_todo_service)) -> object:
    return _json(service.today())


@router.get("/upcoming")
def upcoming(service: TodoService = Depends(get_todo_service)) -> dict[str, object]:
    return {"items": _json(service.upcoming())}


@router.get("/completed")
def completed(service: TodoService = Depends(get_todo_service)) -> dict[str, object]:
    return {"items": _json(service.completed())}


@router.post("/plan-proposals", status_code=status.HTTP_201_CREATED)
def generate_plan(
    _: Annotated[dict[str, object] | None, Body()] = None,
    service: TodoService = Depends(get_todo_service),
) -> object:
    return _json(service.generate_plan())


@router.get("/plan-proposals/{proposal_id}")
def get_plan_proposal(
    proposal_id: str,
    service: TodoService = Depends(get_todo_service),
) -> object:
    return _json(service.get_proposal(proposal_id))


@router.post("/plan-proposals/{proposal_id}/accept")
def accept_plan_proposal(
    proposal_id: str,
    service: TodoService = Depends(get_todo_service),
) -> object:
    return _json(service.accept_proposal(proposal_id))


@router.post("/plan-proposals/{proposal_id}/reject")
def reject_plan_proposal(
    proposal_id: str,
    service: TodoService = Depends(get_todo_service),
) -> object:
    return _json(service.reject_proposal(proposal_id))


def _json(value: object) -> object:
    if hasattr(value, "__dataclass_fields__"):
        value = asdict(value)
    elif isinstance(value, tuple):
        value = [asdict(item) if hasattr(item, "__dataclass_fields__") else item for item in value]
    return jsonable_encoder(value)
