from dataclasses import asdict
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from starlette.concurrency import run_in_threadpool

from app.modules.literature.application.local_transfer import LocalTransferError, MAX_BYTES

router = APIRouter()


def service(request: Request):
    return request.app.state.local_transfer_service


class Observation(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    library_id: str = Field(pattern=r'^[0-9]{1,20}$')
    item_key: str = Field(pattern=r'^[A-Z0-9]{8}$')
    parent_key: str = Field(pattern=r'^[A-Z0-9]{8}$')
    version: str = Field(min_length=1, max_length=200)
    sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    md5: str = Field(pattern=r'^[a-f0-9]{32}$')
    size_bytes: int = Field(gt=0, le=MAX_BYTES)


class Envelope(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    schema_version: Literal[1]
    before: Observation
    after: Observation


@router.post('/papers/{paper_id}/assets/{asset_id}/local-intent')
def create(paper_id: str, asset_id: str, svc=Depends(service)):
    try:
        return svc.create(paper_id, asset_id)
    except LocalTransferError as error:
        raise HTTPException(409, detail={'code': str(error)}) from error


@router.post('/papers/{paper_id}/assets/{asset_id}/local-transfer')
async def receive(paper_id: str, asset_id: str, request: Request,
                  x_transfer_intent: str = Header(max_length=128),
                  x_zotero_observation: str = Header(max_length=4096), svc=Depends(service)):
    try:
        observation = Envelope.model_validate_json(x_zotero_observation)
        await run_in_threadpool(svc.validate, paper_id, asset_id, x_transfer_intent)
        if request.headers.get('content-type') != 'application/pdf':
            raise HTTPException(415, detail={'code': 'not_pdf'})
        data = bytearray()
        async for chunk in request.stream():
            if len(data) + len(chunk) > MAX_BYTES:
                raise HTTPException(413, detail={'code': 'size_limit'})
            data.extend(chunk)
        result = await run_in_threadpool(svc.receive, paper_id, asset_id, x_transfer_intent, observation.model_dump(), bytes(data))
        return asdict(result)
    except ValidationError as error:
        raise HTTPException(422, detail={'code': 'invalid_observation'}) from error
    except LocalTransferError as error:
        raise HTTPException(409, detail={'code': str(error)}) from error
    except ValueError as error:
        raise HTTPException(422, detail={'code': 'invalid_pdf'}) from error
