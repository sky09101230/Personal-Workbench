from dataclasses import asdict
from datetime import date, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    field_validator,
    model_validator,
)

from app.modules.news.application.research import (
    normalize_arxiv_id,
    normalize_doi,
    normalize_openalex_id,
)
from app.modules.news.application.errors import NewsError, PaperResearchIdentityConflictError
from app.modules.news.application.service import NewsService
from app.modules.news.domain.models import FeedItemType
from app.modules.news.domain.research_models import (
    PaperResearchAgent,
    PaperResearchIngest,
    PaperResearchPaperInput,
)


router = APIRouter()


class _StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ResearchAgentRequest(_StrictRequest):
    type: Literal["codex"]
    model: str = Field(min_length=1, max_length=200)
    prompt_version: str = Field(min_length=1, max_length=200)


class ResearchSourceRequest(_StrictRequest):
    provider: Literal["web", "openalex", "crossref", "arxiv", "publisher", "manual"]
    source_id: str | None = Field(default=None, min_length=1, max_length=2_000)


class ResearchPaperRequest(_StrictRequest):
    title: str = Field(min_length=1, max_length=2_000)
    authors: list[str] = Field(default_factory=list, max_length=200)
    doi: str | None = Field(default=None, max_length=2_000)
    arxiv_id: str | None = Field(default=None, max_length=200)
    openalex_id: str | None = Field(default=None, max_length=200)
    published_at: date | None = None
    venue: str | None = Field(default=None, max_length=1_000)
    url: HttpUrl | None = None
    pdf_url: HttpUrl | None = None
    abstract: str | None = Field(default=None, max_length=100_000)
    topics: list[str] = Field(default_factory=list, max_length=100)
    matched_topics: list[str] = Field(default_factory=list, max_length=100)
    ai_summary: str = Field(min_length=1, max_length=20_000)
    recommendation_reason: str = Field(min_length=1, max_length=20_000)
    relevance_score: float | None = Field(default=None, ge=0, le=1)
    novelty_score: float | None = Field(default=None, ge=0, le=1)
    relationship_to_library: str | None = Field(default=None, max_length=5_000)
    source: ResearchSourceRequest

    @field_validator("authors", "topics", "matched_topics")
    @classmethod
    def reject_blank_list_values(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("list values must not be blank")
        return values

    @field_validator("doi")
    @classmethod
    def validate_doi(cls, value: str | None) -> str | None:
        return normalize_doi(value)

    @field_validator("arxiv_id")
    @classmethod
    def validate_arxiv_id(cls, value: str | None) -> str | None:
        return normalize_arxiv_id(value)

    @field_validator("openalex_id")
    @classmethod
    def validate_openalex_id(cls, value: str | None) -> str | None:
        return normalize_openalex_id(value)

    @model_validator(mode="after")
    def require_location(self) -> "ResearchPaperRequest":
        if not any((self.url, self.pdf_url, self.doi, self.arxiv_id, self.openalex_id)):
            raise ValueError("paper requires a URL or supported identifier")
        return self


class PaperResearchIngestRequest(_StrictRequest):
    schema_version: Literal["1"]
    task_key: str = Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
    run_key: str = Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
    generated_at: AwareDatetime
    agent: ResearchAgentRequest
    query_plan: list[str] = Field(min_length=1, max_length=100)
    papers: list[ResearchPaperRequest] = Field(min_length=1, max_length=100)

    @field_validator("query_plan")
    @classmethod
    def reject_blank_queries(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("query_plan values must not be blank")
        return values


def get_news_service(request: Request) -> NewsService:
    return request.app.state.news_service


@router.post("/papers/research/ingest")
def ingest_paper_research(
    payload: PaperResearchIngestRequest,
    service: NewsService = Depends(get_news_service),
) -> dict[str, object]:
    try:
        result = service.ingest_paper_research(_research_payload(payload))
    except PaperResearchIdentityConflictError as error:
        raise HTTPException(
            status_code=409,
            detail={"code": error.code, "message": str(error)},
        ) from error
    return {"status": "succeeded", **asdict(result)}


@router.get("/papers/research")
def list_paper_research(
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    service: NewsService = Depends(get_news_service),
) -> dict[str, object]:
    page = service.list_paper_research(limit=limit, offset=offset)
    return {
        "items": [asdict(item) for item in page.items],
        "total": page.total,
        "limit": page.limit,
        "offset": page.offset,
    }


@router.get("/feed")
def list_feed(
    item_type: Annotated[FeedItemType | None, Query(alias="type")] = None,
    topic: str | None = None,
    period: Literal["daily", "weekly", "monthly"] | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    service: NewsService = Depends(get_news_service),
) -> dict[str, object]:
    page = service.list_feed(
        item_type=item_type,
        topic_id=topic,
        period=period,
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
def refresh(
    item_type: Annotated[FeedItemType | None, Query(alias="type")] = None,
    service: NewsService = Depends(get_news_service),
) -> dict[str, object]:
    try:
        return {"status": "succeeded", **asdict(service.refresh(item_type=item_type))}
    except NewsError as error:
        raise HTTPException(
            status_code=502,
            detail={"code": error.code, "message": str(error)},
        ) from error


def _research_payload(payload: PaperResearchIngestRequest) -> PaperResearchIngest:
    return PaperResearchIngest(
        schema_version=payload.schema_version,
        task_key=payload.task_key,
        run_key=payload.run_key,
        generated_at=payload.generated_at.astimezone(timezone.utc).isoformat(),
        agent=PaperResearchAgent(
            type=payload.agent.type,
            model=payload.agent.model,
            prompt_version=payload.agent.prompt_version,
        ),
        query_plan=tuple(payload.query_plan),
        papers=tuple(
            PaperResearchPaperInput(
                title=paper.title,
                authors=tuple(paper.authors),
                doi=paper.doi,
                arxiv_id=paper.arxiv_id,
                openalex_id=paper.openalex_id,
                published_at=paper.published_at.isoformat() if paper.published_at else None,
                venue=paper.venue,
                url=str(paper.url) if paper.url else None,
                pdf_url=str(paper.pdf_url) if paper.pdf_url else None,
                abstract=paper.abstract,
                topics=tuple(paper.topics),
                matched_topics=tuple(paper.matched_topics),
                ai_summary=paper.ai_summary,
                recommendation_reason=paper.recommendation_reason,
                relevance_score=paper.relevance_score,
                novelty_score=paper.novelty_score,
                relationship_to_library=paper.relationship_to_library,
                source=paper.source.model_dump(exclude_none=True),
            )
            for paper in payload.papers
        ),
    )
