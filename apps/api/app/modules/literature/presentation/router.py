from dataclasses import asdict
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask

from app.modules.literature.application.errors import (
    InvalidCollectionIdentifierError,
    LiteratureError,
    LiteratureResourceNotFoundError,
    PdfUnavailableError,
    ProviderAuthenticationError,
    ProviderNotConfiguredError,
)
from app.modules.literature.application.service import LiteratureService

router = APIRouter()


def get_literature_service(request: Request) -> LiteratureService:
    return request.app.state.literature_service


@router.get("/status")
def status(service: LiteratureService = Depends(get_literature_service)) -> dict[str, object]:
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
    query: str | None = None,
    author: str | None = None,
    year: int | None = None,
    journal: str | None = None,
    tag: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    service: LiteratureService = Depends(get_literature_service),
) -> dict[str, object]:
    try:
        page = service.list_papers(
            collection_id=collection_id,
            limit=limit,
            offset=offset,
            query=query,
            author=author,
            year=year,
            journal=journal,
            tag=tag,
        )
        return {
            "items": [asdict(paper) for paper in page.items],
            "total": page.total,
            "library_version": page.library_version,
        }
    except LiteratureError as error:
        raise _http_error(error) from error


@router.get("/filters")
def list_filters(service: LiteratureService = Depends(get_literature_service)) -> dict[str, object]:
    return asdict(service.list_filter_options())


@router.get("/papers/{paper_id}")
def get_paper(
    paper_id: str,
    service: LiteratureService = Depends(get_literature_service),
) -> dict[str, object]:
    try:
        detail = service.get_paper(paper_id)
        attachments = service.list_attachments(paper_id)
        return {
            "paper": asdict(detail.paper),
            "collections": [asdict(collection) for collection in detail.collections],
            "pdf_available": any(
                item.downloadable and item.content_type == "application/pdf"
                for item in attachments
            ),
        }
    except LiteratureError as error:
        raise _http_error(error) from error


@router.get("/papers/{paper_id}/notes")
def list_notes(
    paper_id: str,
    service: LiteratureService = Depends(get_literature_service),
) -> dict[str, object]:
    try:
        return {"items": [asdict(note) for note in service.list_notes(paper_id)]}
    except LiteratureError as error:
        raise _http_error(error) from error


@router.get("/papers/{paper_id}/attachments")
def list_attachments(
    paper_id: str,
    service: LiteratureService = Depends(get_literature_service),
) -> dict[str, object]:
    try:
        return {
            "items": [
                {**asdict(attachment), "availability": _attachment_availability(attachment)}
                for attachment in service.list_attachments(paper_id)
            ]
        }
    except LiteratureError as error:
        raise _http_error(error) from error


@router.get("/papers/{paper_id}/pdf")
def stream_pdf(
    paper_id: str,
    range_header: Annotated[str | None, Header(alias="Range")] = None,
    service: LiteratureService = Depends(get_literature_service),
) -> StreamingResponse:
    return _pdf_response(paper_id, range_header, False, service)


@router.get("/papers/{paper_id}/pdf/download")
def download_pdf(
    paper_id: str,
    range_header: Annotated[str | None, Header(alias="Range")] = None,
    service: LiteratureService = Depends(get_literature_service),
) -> StreamingResponse:
    return _pdf_response(paper_id, range_header, True, service)


def _pdf_response(
    paper_id: str,
    range_header: str | None,
    download: bool,
    service: LiteratureService,
) -> StreamingResponse:
    try:
        provider_file = service.open_pdf(paper_id, range_header=range_header)
    except LiteratureError as error:
        raise _http_error(error) from error
    disposition = "attachment" if download else "inline"
    headers = {
        "Content-Disposition": f"{disposition}; filename*=UTF-8''{quote(provider_file.filename)}",
        "Cache-Control": "private, no-store",
    }
    for name, value in (
        ("Content-Length", provider_file.content_length),
        ("Content-Range", provider_file.content_range),
        ("Accept-Ranges", provider_file.accept_ranges),
    ):
        if value:
            headers[name] = value
    return StreamingResponse(
        provider_file.chunks,
        status_code=provider_file.status_code,
        media_type="application/pdf",
        headers=headers,
        background=BackgroundTask(provider_file.close) if provider_file.close else None,
    )


def _attachment_availability(attachment: object) -> str:
    content_type = getattr(attachment, "content_type", None)
    if content_type != "application/pdf":
        return "not_pdf"
    if getattr(attachment, "downloadable", False):
        return "available"
    if getattr(attachment, "link_mode", None) == "linked_file":
        return "linked_file"
    return "provider_unavailable"


def _http_error(error: LiteratureError) -> HTTPException:
    if isinstance(error, InvalidCollectionIdentifierError):
        return HTTPException(status_code=400, detail={"code": "invalid_collection_id"})
    if isinstance(error, ProviderNotConfiguredError):
        return HTTPException(status_code=503, detail={"code": "provider_not_configured"})
    if isinstance(error, ProviderAuthenticationError):
        return HTTPException(status_code=502, detail={"code": "provider_authentication_failed"})
    if isinstance(error, LiteratureResourceNotFoundError):
        return HTTPException(status_code=404, detail={"code": "paper_not_found"})
    if isinstance(error, PdfUnavailableError):
        return HTTPException(status_code=404, detail={"code": "pdf_unavailable"})
    return HTTPException(status_code=502, detail={"code": "provider_unavailable"})
