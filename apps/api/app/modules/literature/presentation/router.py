from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.modules.literature.application.errors import (
    InvalidCollectionIdentifierError,
    LiteratureError,
    ProviderAuthenticationError,
    ProviderNotConfiguredError,
)
from app.modules.literature.application.service import LiteratureService

router = APIRouter()


def get_literature_service(request: Request) -> LiteratureService:
    return request.app.state.literature_service


@router.get("/status")
def status(service: LiteratureService = Depends(get_literature_service)) -> dict[str, str | bool]:
    return service.status()


@router.post("/sync")
def sync(service: LiteratureService = Depends(get_literature_service)) -> dict[str, object]:
    try:
        result = service.sync()
        return {"status": "succeeded", **asdict(result)}
    except LiteratureError as error:
        raise _http_error(error) from error


@router.get("/collections")
def list_collections(
    service: LiteratureService = Depends(get_literature_service),
) -> dict[str, list[dict[str, object]]]:
    try:
        return {"items": [asdict(collection) for collection in service.list_collections()]}
    except LiteratureError as error:
        raise _http_error(error) from error


@router.get("/papers")
def list_papers(
    collection_id: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    service: LiteratureService = Depends(get_literature_service),
) -> dict[str, object]:
    try:
        page = service.list_papers(collection_id=collection_id, limit=limit, offset=offset)
        return {
            "items": [asdict(paper) for paper in page.items],
            "total": page.total,
            "library_version": page.library_version,
        }
    except LiteratureError as error:
        raise _http_error(error) from error


def _http_error(error: LiteratureError) -> HTTPException:
    if isinstance(error, InvalidCollectionIdentifierError):
        return HTTPException(status_code=400, detail={"code": "invalid_collection_id"})
    if isinstance(error, ProviderNotConfiguredError):
        return HTTPException(status_code=503, detail={"code": "provider_not_configured"})
    if isinstance(error, ProviderAuthenticationError):
        return HTTPException(status_code=502, detail={"code": "provider_authentication_failed"})
    return HTTPException(status_code=502, detail={"code": "provider_unavailable"})
