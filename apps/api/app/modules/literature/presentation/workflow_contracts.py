from typing import Annotated, Literal

from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr

from app.modules.literature.application.errors import MigrationRequiredError, WorkflowConflictError, WorkflowNotFoundError
from app.modules.literature.domain.canonical import IdentityConflictError
from app.modules.literature.presentation.router import _http_error
from app.modules.literature.domain.workflow import MetadataProposal


class MetadataPatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, min_length=1, max_length=1000)
    authors: list[Annotated[StrictStr, Field(min_length=1, max_length=512)]] | None = Field(default=None, max_length=100)
    year: Annotated[StrictInt, Field(ge=1000, le=3000)] | None = None
    doi: str | None = Field(default=None, max_length=1000)
    arxiv_id: str | None = Field(default=None, max_length=1000)
    openalex_id: str | None = Field(default=None, max_length=1000)
    journal: str | None = Field(default=None, max_length=1000)
    abstract: str | None = Field(default=None, max_length=30000)


class UploadConfirmResult(BaseModel):
    item_id: str
    status: Literal["confirmed", "already_confirmed", "cancelled", "conflict", "needs_review", "failed"]
    paper_id: str | None = None
    asset_id: str | None = None
    created: bool | None = None
    error: str | None = None
    candidates: list[str] = Field(default_factory=list)


class UploadConfirmResponse(BaseModel):
    results: list[UploadConfirmResult]


class ProposalListResponse(BaseModel):
    proposals: list[MetadataProposal]


async def workflow_error_handler(request, error):
    if isinstance(error, MigrationRequiredError):
        return JSONResponse(status_code=409, content={"detail":{"code":"migration_required"}})
    if isinstance(error, WorkflowNotFoundError):
        return JSONResponse(status_code=404, content={"detail":{"code":"workflow_not_found"}})
    if isinstance(error, WorkflowConflictError):
        return JSONResponse(status_code=409, content={"detail":{"code":"workflow_conflict", "reason":str(error)}})
    if isinstance(error, IdentityConflictError):
        return JSONResponse(status_code=409, content={"detail":{"code":"identity_conflict", "reason":str(error), "candidates":list(error.candidates)}})
    response = _http_error(error)
    return JSONResponse(status_code=response.status_code, content={"detail":response.detail})
