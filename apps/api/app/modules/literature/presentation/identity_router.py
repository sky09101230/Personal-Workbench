from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from app.modules.literature.domain.canonical import IdentityConflictError


router = APIRouter()


def identity_service(request: Request):
    return request.app.state.identity_review_service


class SnapshotDecision(BaseModel):
    model_config = ConfigDict(extra='forbid')
    snapshot: str = Field(pattern=r'^[a-f0-9]{64}$')
    reason: str = Field(min_length=10, max_length=4000)


class IdentityConfirmation(SnapshotDecision):
    evidence_ids: list[str] = Field(min_length=1, max_length=50)


class IdentifierValues(BaseModel):
    model_config = ConfigDict(extra='forbid')
    doi: str | None = Field(max_length=1000)
    arxiv_id: str | None = Field(max_length=1000)
    openalex_id: str | None = Field(max_length=1000)


class IdentityCorrection(IdentityConfirmation):
    correction: IdentifierValues


class ConflictDecision(SnapshotDecision):
    decision: Literal['keep_current', 'keep_separate', 'quarantine', 'reopen']


class VersionLink(BaseModel):
    model_config = ConfigDict(extra='forbid')
    published_id: str = Field(min_length=1, max_length=300)
    preprint_snapshot: str = Field(pattern=r'^[a-f0-9]{64}$')
    published_snapshot: str = Field(pattern=r'^[a-f0-9]{64}$')
    evidence_ids: list[str] = Field(min_length=2, max_length=50)
    reason: str = Field(min_length=10, max_length=4000)


def _perform(operation, *args, **kwargs):
    try:
        return operation(*args, **kwargs)
    except IdentityConflictError:
        raise
    except ValueError as error:
        raise HTTPException(422, detail={'code': 'invalid_identity_review', 'reason': str(error)}) from error


@router.get('/papers/{paper_id}/identity')
def identity_context(paper_id: str, service=Depends(identity_service)):
    return _perform(service.context, paper_id)


@router.get('/identity/conflicts')
def identity_conflicts(limit: int = Query(default=100, ge=1, le=100), offset: int = Query(default=0, ge=0), service=Depends(identity_service)):
    return service.conflicts(limit=limit, offset=offset)


@router.post('/papers/{paper_id}/identity/confirm')
def confirm_identity(paper_id: str, payload: IdentityConfirmation, service=Depends(identity_service)):
    return _perform(service.review, paper_id, **payload.model_dump())


@router.post('/papers/{paper_id}/identity/correct')
def correct_identity(paper_id: str, payload: IdentityCorrection, service=Depends(identity_service)):
    return _perform(service.review, paper_id, **payload.model_dump())


@router.post('/identity/conflicts/{conflict_id}/decisions')
def decide_conflict(conflict_id: str, payload: ConflictDecision, service=Depends(identity_service)):
    return _perform(service.decide_conflict, conflict_id, **payload.model_dump())


@router.post('/papers/{paper_id}/versions')
def link_versions(paper_id: str, payload: VersionLink, service=Depends(identity_service)):
    return _perform(service.link_versions, paper_id, **payload.model_dump())


@router.post('/versions/{version_id}/retract')
def retract_version(version_id: str, payload: SnapshotDecision, service=Depends(identity_service)):
    return _perform(service.retract_version, version_id, **payload.model_dump())
