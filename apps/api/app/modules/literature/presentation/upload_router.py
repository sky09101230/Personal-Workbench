"""Upload workflow API: stage PDFs → extract → review → confirm → canonical ingest."""

from dataclasses import asdict
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool
from app.modules.literature.presentation.workflow_contracts import MetadataPatchRequest, UploadConfirmResponse
from app.modules.literature.domain.workflow import UploadBatch, UploadItem


router = APIRouter()


def get_upload_service(request: Request):
    return request.app.state.upload_workflow_service


class ItemMetadataRequest(MetadataPatchRequest):
    pass


@router.post("/uploads/batches", status_code=201, response_model=UploadBatch)
def create_batch(service=Depends(get_upload_service)):
    batch = service.create_batch()
    return asdict(batch)


@router.post("/uploads/batches/{batch_id}/files", status_code=201, response_model=UploadItem)
async def stage_file(
    batch_id: str,
    request: Request,
    filename: str = Query(default="paper.pdf", max_length=240),
    service=Depends(get_upload_service),
):
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > 50 * 1024 * 1024:
            raise HTTPException(413, detail={"code": "pdf_too_large"})
    try:
        item = await run_in_threadpool(service.stage_file, batch_id, filename, bytes(data))
        return asdict(item)
    except ValueError as error:
        raise HTTPException(422, detail={"code": "invalid_upload", "reason": str(error)}) from error


@router.get("/uploads/batches/{batch_id}", response_model=UploadBatch)
def get_batch(batch_id: str, service=Depends(get_upload_service)):
    batch = service.get_batch(batch_id)
    if not batch:
        raise HTTPException(404, detail={"code": "batch_not_found"})
    return asdict(batch)


@router.patch("/uploads/batches/{batch_id}/items/{item_id}", response_model=UploadItem)
def update_item(
    batch_id: str,
    item_id: str,
    payload: ItemMetadataRequest,
    service=Depends(get_upload_service),
):
    metadata = payload.model_dump(exclude_unset=True)
    if not metadata:
        raise HTTPException(422, detail={"code": "empty_update"})
    try:
        item = service.update_item_metadata(batch_id, item_id, metadata)
        return asdict(item)
    except ValueError as error:
        raise HTTPException(422, detail={"code": "invalid_update", "reason": str(error)}) from error


@router.post("/uploads/batches/{batch_id}/confirm", response_model=UploadConfirmResponse)
def confirm_batch(batch_id: str, service=Depends(get_upload_service)):
    try:
        return {"results": service.confirm_batch(batch_id)}
    except ValueError as error:
        raise HTTPException(422, detail={"code": "confirm_failed", "reason": str(error)}) from error


@router.post("/uploads/batches/{batch_id}/cancel", response_model=UploadBatch)
def cancel_batch(batch_id: str, service=Depends(get_upload_service)):
    try:
        batch = service.cancel_batch(batch_id)
        return asdict(batch)
    except ValueError as error:
        raise HTTPException(422, detail={"code": "cancel_failed", "reason": str(error)}) from error


@router.post("/uploads/batches/{batch_id}/items/{item_id}/cancel", response_model=UploadItem)
def cancel_item(batch_id: str, item_id: str, service=Depends(get_upload_service)):
    try:
        item = service.cancel_item(batch_id, item_id)
        return asdict(item)
    except ValueError as error:
        raise HTTPException(422, detail={"code": "cancel_failed", "reason": str(error)}) from error


@router.post("/uploads/cleanup")
def cleanup_staging(max_age_seconds: int = Query(default=3600,ge=3600), service=Depends(get_upload_service)):
    return service.cleanup(max_age_seconds)
