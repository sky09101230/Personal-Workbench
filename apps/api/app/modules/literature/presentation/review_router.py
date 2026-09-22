"""Metadata review API: propose, compare, accept/reject/edit with provenance."""

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from app.modules.literature.presentation.workflow_contracts import MetadataPatchRequest, ProposalListResponse
from app.modules.literature.domain.workflow import MetadataProposal
from app.modules.literature.domain.canonical import IdentityConflictError


router = APIRouter()


def get_review_service(request: Request):
    return request.app.state.metadata_review_service


class ProposalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: str = Field(min_length=1,max_length=100)
    proposed_metadata: MetadataPatchRequest


class EditAcceptRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    edits: MetadataPatchRequest


class MetadataConfirmationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    snapshot: MetadataPatchRequest


@router.post("/papers/{paper_id}/metadata/confirm")
def confirm_metadata(paper_id: str, payload: MetadataConfirmationRequest, service=Depends(get_review_service)):
    try:
        return service.confirm_metadata(paper_id, payload.snapshot.model_dump(exclude_unset=True))
    except IdentityConflictError:
        raise
    except ValueError as error:
        raise HTTPException(422, detail={"code": "invalid_metadata_snapshot", "reason": str(error)}) from error


@router.get("/papers/{paper_id}/metadata/proposals", response_model=ProposalListResponse)
def list_proposals(paper_id: str, service=Depends(get_review_service)):
    return {"proposals": [asdict(p) for p in service.list_proposals(paper_id)]}


@router.post("/papers/{paper_id}/metadata/proposals", status_code=201, response_model=MetadataProposal)
def create_proposal(paper_id: str, payload: ProposalRequest, service=Depends(get_review_service)):
    try:
        proposal = service.create_proposal(paper_id, payload.source, payload.proposed_metadata.model_dump(exclude_unset=True))
        return asdict(proposal)
    except IdentityConflictError:
        raise
    except ValueError as error:
        raise HTTPException(422, detail={"code": "invalid_proposal", "reason": str(error)}) from error


@router.get("/metadata/proposals/{proposal_id}", response_model=MetadataProposal)
def get_proposal(proposal_id: str, service=Depends(get_review_service)):
    proposal = service.get_proposal(proposal_id)
    if not proposal:
        raise HTTPException(404, detail={"code": "proposal_not_found"})
    return asdict(proposal)


@router.post("/metadata/proposals/{proposal_id}/accept", response_model=MetadataProposal)
def accept_proposal(proposal_id: str, service=Depends(get_review_service)):
    try:
        proposal = service.accept_proposal(proposal_id)
        return asdict(proposal)
    except IdentityConflictError:
        raise
    except ValueError as error:
        raise HTTPException(422, detail={"code": "accept_failed", "reason": str(error)}) from error


@router.post("/metadata/proposals/{proposal_id}/reject", response_model=MetadataProposal)
def reject_proposal(proposal_id: str, service=Depends(get_review_service)):
    try:
        proposal = service.reject_proposal(proposal_id)
        return asdict(proposal)
    except ValueError as error:
        raise HTTPException(422, detail={"code": "reject_failed", "reason": str(error)}) from error


@router.post("/metadata/proposals/{proposal_id}/edit-accept", response_model=MetadataProposal)
def edit_accept(proposal_id: str, payload: EditAcceptRequest, service=Depends(get_review_service)):
    try:
        proposal = service.edit_and_accept(proposal_id, payload.edits.model_dump(exclude_unset=True))
        return asdict(proposal)
    except IdentityConflictError:
        raise
    except ValueError as error:
        raise HTTPException(422, detail={"code": "edit_accept_failed", "reason": str(error)}) from error
