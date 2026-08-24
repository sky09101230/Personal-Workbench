from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.modules.news.application.errors import NewsError
from app.modules.news.application.service import NewsService
from app.modules.news.domain.models import FeedItemType


router = APIRouter()


def get_news_service(request: Request) -> NewsService:
    return request.app.state.news_service


@router.get("/feed")
def list_feed(
    item_type: Annotated[FeedItemType | None, Query(alias="type")] = None,
    topic: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    service: NewsService = Depends(get_news_service),
) -> dict[str, object]:
    page = service.list_feed(
        item_type=item_type,
        topic_id=topic,
        limit=limit,
        offset=offset,
    )
    return {
        "items": [asdict(item) for item in page.items],
        "total": page.total,
        "limit": page.limit,
        "offset": page.offset,
    }


@router.get("/topics")
def list_topics(
    service: NewsService = Depends(get_news_service),
) -> dict[str, list[dict[str, object]]]:
    return {"items": [asdict(topic) for topic in service.list_topics()]}


@router.post("/refresh")
def refresh(service: NewsService = Depends(get_news_service)) -> dict[str, object]:
    try:
        return {"status": "succeeded", **asdict(service.refresh())}
    except NewsError as error:
        raise HTTPException(
            status_code=502,
            detail={"code": error.code, "message": str(error)},
        ) from error
