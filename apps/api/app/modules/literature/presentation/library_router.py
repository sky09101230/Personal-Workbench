from dataclasses import asdict
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool

from app.modules.literature.application.ingestion import LiteratureIngestionService
from app.modules.literature.application.errors import LiteratureResourceNotFoundError
from app.modules.literature.domain.canonical import IdentityConflictError


router = APIRouter()


def get_ingestion(request: Request) -> LiteratureIngestionService:
    return request.app.state.literature_ingestion_service


class StateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reading_status: Literal["inbox", "saved", "reading", "read", "archived"] | None = None
    tags: list[str] | None = Field(default=None, max_length=100)


class CollectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    parent_id: str | None = None


class MembershipRequest(BaseModel):
    present: bool = True


class SavedRequest(BaseModel):
    recommendation_ids: list[str] = Field(max_length=500)


def require_paper(service, paper_id):
    paper = service.repository.get_paper(paper_id)
    if paper is None:
        raise HTTPException(404, detail={"code": "paper_not_found"})
    return paper


@router.post("/imports/radar/{recommendation_id}")
def save_radar(recommendation_id: str, service=Depends(get_ingestion)):
    try:
        return asdict(service.save_radar(recommendation_id))
    except IdentityConflictError as error:
        raise HTTPException(409, detail={"code": "identity_conflict", "reason": str(error), "candidates": error.candidates}) from error
    except LiteratureResourceNotFoundError as error:
        raise HTTPException(404, detail={"code": "recommendation_not_found"}) from error
    except ValueError as error:
        raise HTTPException(422, detail={"code": "invalid_metadata", "reason": str(error)}) from error


@router.post("/imports/radar-saved")
def radar_saved(payload: SavedRequest, service=Depends(get_ingestion)):
    return {"saved": service.repository.saved_origins(payload.recommendation_ids)}


@router.post("/imports/pdf", status_code=201)
async def upload_pdf(
    request: Request,
    filename: str = Query(default="paper.pdf", max_length=240),
    paper_id: str | None = None,
    title: str | None = Query(default=None, max_length=1000),
    role: Literal["primary", "preprint", "supplementary"] = "primary",
    service=Depends(get_ingestion),
):
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > 50 * 1024 * 1024:
            raise HTTPException(413, detail={"code": "pdf_too_large"})
    try:
        result, asset = await run_in_threadpool(service.upload_pdf, bytes(data), filename, paper_id=paper_id, title=title, role=role)
        return {**asdict(result), "asset": asdict(asset)}
    except LiteratureResourceNotFoundError as error:
        raise HTTPException(404, detail={"code": "paper_not_found"}) from error
    except IdentityConflictError as error:
        raise HTTPException(409, detail={"code": "identity_conflict", "reason": str(error)}) from error
    except ValueError as error:
        raise HTTPException(422, detail={"code": "invalid_pdf", "reason": str(error)}) from error


@router.get("/papers/{paper_id}/provenance")
def provenance(paper_id: str, service=Depends(get_ingestion)):
    require_paper(service, paper_id)
    return service.repository.provenance(paper_id)


@router.patch("/papers/{paper_id}/state")
def state(paper_id: str, payload: StateRequest, service=Depends(get_ingestion)):
    require_paper(service, paper_id)
    tags = None if payload.tags is None else [t.strip() for t in payload.tags if t.strip()]
    if tags and any(len(t) > 256 for t in tags):
        raise HTTPException(422, detail={"code": "invalid_tag"})
    service.repository.set_state(paper_id, reading_status=payload.reading_status, tags=tags)
    return asdict(service.repository.get_paper(paper_id).paper)


@router.delete("/papers/{paper_id}")
def delete_paper(paper_id: str, service=Depends(get_ingestion)):
    require_paper(service, paper_id)
    service.repository.set_state(paper_id, deleted=True)
    return {"deleted": True, "recoverable": True}


@router.post("/collections", status_code=201)
def create_collection(payload: CollectionRequest, service=Depends(get_ingestion)):
    if not payload.name.strip() or payload.parent_id and payload.parent_id not in {c.id for c in service.repository.list_collections()}:
        raise HTTPException(422, detail={"code": "invalid_collection"})
    return asdict(service.repository.create_collection(payload.name, payload.parent_id))


@router.patch("/papers/{paper_id}/collections/{collection_id}")
def membership(paper_id: str, collection_id: str, payload: MembershipRequest, service=Depends(get_ingestion)):
    require_paper(service, paper_id)
    try:
        service.repository.set_membership(paper_id, collection_id, payload.present)
    except ValueError as error:
        raise HTTPException(404, detail={"code": "collection_not_found"}) from error
    return {"present": payload.present}
