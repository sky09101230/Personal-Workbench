from dataclasses import asdict
from datetime import datetime
import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.modules.project_activity.application.errors import (
    ProjectActivityConflictError,
    ProjectActivityError,
    ProjectActivityNotFoundError,
    ProjectActivityValidationError,
)
from app.modules.project_activity.application.service import ProjectActivityService


router = APIRouter()


class DeviceHeartbeat(BaseModel):
    device_id: str = Field(min_length=1, max_length=500)
    name: str = Field(min_length=1, max_length=500)
    agent_version: str | None = Field(default=None, max_length=200)


class ProjectSourceObserve(BaseModel):
    project_id: str = Field(min_length=1, max_length=500)
    source_type: str = Field(min_length=1, max_length=200)
    source_key: str = Field(min_length=1, max_length=2000)
    device_id: str | None = Field(default=None, max_length=500)
    local_path: str | None = Field(default=None, max_length=5000)


class ActivityRunObserve(BaseModel):
    project_source_id: str = Field(min_length=1, max_length=500)
    run_id: str = Field(min_length=1, max_length=1000)
    experiment_name: str | None = Field(default=None, max_length=1000)
    status: str = Field(min_length=1, max_length=200)
    created_at: datetime | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    latest_metrics: dict[str, object] | None = None
    summary: dict[str, object] | None = None
    config_summary: dict[str, object] | None = None
    relative_path: str | None = Field(default=None, max_length=5000)
    has_best_checkpoint: bool = False


class ActivityEventCreate(BaseModel):
    project_id: str = Field(min_length=1, max_length=500)
    source_id: str | None = Field(default=None, max_length=500)
    activity_kind: str = Field(min_length=1, max_length=200)
    event_type: str = Field(min_length=1, max_length=500)
    occurred_at: datetime | None = None
    subject_type: str | None = Field(default=None, max_length=200)
    subject_id: str | None = Field(default=None, max_length=1000)
    payload: dict[str, object] | None = None


def get_project_activity_service(request: Request) -> ProjectActivityService:
    return request.app.state.project_activity_service


def require_agent_token(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    configured_token = getattr(request.app.state, "project_activity_agent_token", "")
    if not configured_token:
        raise HTTPException(status_code=503, detail="Agent authentication is not configured")

    scheme, separator, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not separator or not token:
        raise HTTPException(
            status_code=401,
            detail="Invalid agent credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not secrets.compare_digest(token, configured_token):
        raise HTTPException(
            status_code=401,
            detail="Invalid agent credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def project_activity_error_handler(
    _: Request, error: ProjectActivityError
) -> JSONResponse:
    if isinstance(error, ProjectActivityNotFoundError):
        http_status = 404
    elif isinstance(error, ProjectActivityValidationError):
        http_status = 422
    elif isinstance(error, ProjectActivityConflictError):
        http_status = 409
    else:
        http_status = 500
    return JSONResponse(
        status_code=http_status,
        content={"detail": {"code": error.code, "message": str(error)}},
    )


@router.post("/devices/heartbeat")
def heartbeat_device(
    request: DeviceHeartbeat,
    _: None = Depends(require_agent_token),
    service: ProjectActivityService = Depends(get_project_activity_service),
) -> object:
    return _json(service.heartbeat_device(**request.model_dump()))


@router.post("/sources/observe")
def observe_project_source(
    request: ProjectSourceObserve,
    _: None = Depends(require_agent_token),
    service: ProjectActivityService = Depends(get_project_activity_service),
) -> object:
    return _json(service.observe_project_source(**request.model_dump()))


@router.post("/runs/observe")
def observe_run(
    request: ActivityRunObserve,
    _: None = Depends(require_agent_token),
    service: ProjectActivityService = Depends(get_project_activity_service),
) -> object:
    return _json(service.observe_run(**request.model_dump()))


@router.post("/events", status_code=status.HTTP_201_CREATED)
def record_event(
    request: ActivityEventCreate,
    _: None = Depends(require_agent_token),
    service: ProjectActivityService = Depends(get_project_activity_service),
) -> object:
    return _json(service.record_event(**request.model_dump()))


@router.get("/projects/{project_id}/sources")
def get_project_sources(
    project_id: str,
    service: ProjectActivityService = Depends(get_project_activity_service),
) -> dict[str, object]:
    return {"items": _json(service.get_project_sources(project_id))}


@router.get("/projects/{project_id}/runs")
def get_project_runs(
    project_id: str,
    service: ProjectActivityService = Depends(get_project_activity_service),
) -> dict[str, object]:
    return {"items": _json(service.get_project_runs(project_id))}


@router.get("/projects/{project_id}/events")
def get_recent_activity(
    project_id: str,
    activity_kind: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    service: ProjectActivityService = Depends(get_project_activity_service),
) -> dict[str, object]:
    return {
        "items": _json(
            service.get_recent_activity(
                project_id, activity_kind=activity_kind, limit=limit
            )
        )
    }


def _json(value: object) -> object:
    if hasattr(value, "__dataclass_fields__"):
        value = asdict(value)
    elif isinstance(value, tuple):
        value = [asdict(item) if hasattr(item, "__dataclass_fields__") else item for item in value]
    return jsonable_encoder(value)
