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

from app.modules.news.application.errors import NewsError, PaperResearchIdentityConflictError
from app.modules.news.application.research import (
    normalize_arxiv_id,
    normalize_doi,
    normalize_openalex_id,
)
from app.modules.news.application.service import NewsService
from app.modules.news.domain.models import FeedItemType
from app.modules.news.domain.research_models import (
    PaperResearchAgent,
    PaperResearchIngest,
    PaperResearchPaperInput,
)


router = APIRouter()


class _StrictRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        populate_by_name=True,
    )


class ResearchAgentRequest(_StrictRequest):
    type: Literal["codex", "literature-radar"]
    model: str = Field(min_length=1, max_length=200)
    prompt_version: str = Field(min_length=1, max_length=200)


class ResearchSourceRequest(_StrictRequest):
    provider: Literal[
        "web",
        "openalex",
        "crossref",
        "arxiv",
        "publisher",
        "manual",
        "literature_radar",
    ]
    source_id: str | None = Field(default=None, min_length=1, max_length=2_000)


class ResearchProfileRequest(_StrictRequest):
    key: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=500)
    path: str = Field(min_length=1, max_length=2_000)


class ResearchSearchWindowRequest(_StrictRequest):
    from_date: date = Field(alias="from")
    to_date: date = Field(alias="to")
    lookback_days: int = Field(ge=1, le=3650)

    @model_validator(mode="after")
    def validate_order(self) -> "ResearchSearchWindowRequest":
        if self.from_date > self.to_date:
            raise ValueError("search window from must not be after to")
        return self


class ResearchSourceStatusRequest(_StrictRequest):
    name: str = Field(min_length=1, max_length=200)
    status: Literal["success", "degraded", "failed", "not_attempted"]
    attempts: int = Field(ge=0)
    routes: list[dict[str, object]] = Field(default_factory=list, max_length=100)
    result_count: int = Field(default=0, ge=0)
    warning: str | None = Field(default=None, max_length=20_000)


class ResearchZoteroContextRequest(_StrictRequest):
    success: bool
    status: Literal["success", "degraded", "failed", "not_attempted"]
    backend: str = Field(min_length=1, max_length=100)
    utf8: bool | None = None
    queries_used: list[str] = Field(default_factory=list, max_length=100)
    successful_queries: int = Field(ge=0)
    failed_queries: int = Field(ge=0)
    query_limit: int = Field(ge=0)
    anchor_count: int = Field(ge=0)
    related_collection_count: int = Field(ge=0)
    summary: str = Field(min_length=1, max_length=50_000)
    warnings: list[str] = Field(default_factory=list, max_length=100)


class ResearchDateEvidenceRequest(_StrictRequest):
    first_public_at: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    online_at: str | None = Field(default=None, pattern=r"^\d{4}(?:-\d{2}(?:-\d{2})?)?$")
    issue_at: str | None = Field(default=None, pattern=r"^\d{4}(?:-\d{2}(?:-\d{2})?)?$")
    preprint_at: str | None = Field(default=None, pattern=r"^\d{4}(?:-\d{2}(?:-\d{2})?)?$")
    accepted_at: str | None = Field(default=None, pattern=r"^\d{4}(?:-\d{2}(?:-\d{2})?)?$")
    version_published_at: str | None = Field(default=None, pattern=r"^\d{4}(?:-\d{2}(?:-\d{2})?)?$")
    selected_reason: str = Field(min_length=1, max_length=20_000)


class ResearchEvidenceRequest(_StrictRequest):
    primary_url: HttpUrl
    additional_urls: list[HttpUrl] = Field(default_factory=list, max_length=100)
    evidence_depth: Literal["title", "abstract", "full_text"] | None = None


class ResearchZoteroRelationshipRequest(_StrictRequest):
    already_in_library: bool | None = None
    related_papers: list[dict[str, object]] = Field(default_factory=list, max_length=100)
    relationship_summary: str | None = Field(default=None, max_length=20_000)


class ResearchPaperRequest(_StrictRequest):
    title: str = Field(min_length=1, max_length=2_000)
    authors: list[str] = Field(default_factory=list, max_length=200)
    doi: str | None = Field(default=None, max_length=2_000)
    arxiv_id: str | None = Field(default=None, max_length=200)
    openalex_id: str | None = Field(default=None, max_length=200)
    published_at: date | None = None
    venue: str | None = Field(default=None, max_length=1_000)
    publication_type: str | None = Field(default=None, max_length=200)
    url: HttpUrl | None = None
    pdf_url: HttpUrl | None = None
    abstract: str | None = Field(default=None, max_length=100_000)
    topics: list[str] = Field(default_factory=list, max_length=100)
    matched_topics: list[str] = Field(default_factory=list, max_length=100)
    ai_summary: str = Field(default="", max_length=20_000)
    recommendation_reason: str = Field(min_length=1, max_length=20_000)
    relevance_score: float | None = Field(default=None, ge=0, le=1)
    novelty_score: float | None = Field(default=None, ge=0, le=1)
    scientific_value_score: float | None = Field(default=None, ge=0, le=1)
    recency_score: float | None = Field(default=None, ge=0, le=1)
    overall_score: float | None = Field(default=None, ge=0, le=1)
    relationship_to_library: str | None = Field(default=None, max_length=20_000)
    source: ResearchSourceRequest
    selection_kind: Literal["recommended", "verified_not_selected"] = "recommended"
    selection_rank: int | None = Field(default=None, ge=1, le=1_000)
    date_evidence: ResearchDateEvidenceRequest | None = None
    zotero_relationship: ResearchZoteroRelationshipRequest | None = None
    evidence: ResearchEvidenceRequest | None = None

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
    def validate_paper(self) -> "ResearchPaperRequest":
        if not any((self.url, self.pdf_url, self.doi, self.arxiv_id, self.openalex_id)):
            raise ValueError("paper requires a URL or supported identifier")
        if self.selection_kind == "recommended" and not self.ai_summary.strip():
            raise ValueError("recommended paper requires ai_summary")
        return self


class PaperResearchIngestRequest(_StrictRequest):
    schema_version: Literal["1", "2"]
    task_key: str = Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
    run_key: str = Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
    generated_at: AwareDatetime
    agent: ResearchAgentRequest
    query_plan: list[str] = Field(min_length=1, max_length=100)
    papers: list[ResearchPaperRequest] = Field(min_length=1, max_length=100)
    run_kind: Literal["paper_research", "literature_radar"] = "paper_research"
    ingest_identity: str | None = Field(
        default=None,
        pattern=r"^sha256:[0-9a-f]{64}$",
        max_length=80,
    )
    profile: ResearchProfileRequest | None = None
    search_window: ResearchSearchWindowRequest | None = None
    candidate_count: int | None = Field(default=None, ge=0)
    verified_candidate_count: int | None = Field(default=None, ge=0)
    recommended_count: int | None = Field(default=None, ge=0)
    warnings: list[str] = Field(default_factory=list, max_length=100)
    source_status: list[ResearchSourceStatusRequest] = Field(default_factory=list, max_length=100)
    zotero_context: ResearchZoteroContextRequest | None = None
    diagnostics: dict[str, object] = Field(default_factory=dict)

    @field_validator("query_plan", "warnings")
    @classmethod
    def reject_blank_values(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("list values must not be blank")
        return values

    @model_validator(mode="after")
    def validate_contract_version(self) -> "PaperResearchIngestRequest":
        if self.schema_version == "1":
            if any(paper.selection_kind != "recommended" for paper in self.papers):
                raise ValueError("schema v1 supports recommended papers only")
            return self

        if self.run_kind != "literature_radar":
            raise ValueError("schema v2 requires run_kind literature_radar")
        required = (
            self.ingest_identity,
            self.profile,
            self.search_window,
            self.candidate_count,
            self.verified_candidate_count,
            self.recommended_count,
            self.zotero_context,
        )
        if any(value is None for value in required):
            raise ValueError("schema v2 requires Radar run metadata")
        if not self.source_status:
            raise ValueError("schema v2 requires source_status")
        if self.verified_candidate_count != len(self.papers):
            raise ValueError("verified_candidate_count must equal ingested papers")
        recommended = [paper for paper in self.papers if paper.selection_kind == "recommended"]
        alternatives = [
            paper for paper in self.papers if paper.selection_kind == "verified_not_selected"
        ]
        if self.recommended_count != len(recommended):
            raise ValueError("recommended_count must equal recommended papers")
        if self.candidate_count is not None and self.verified_candidate_count is not None:
            if self.candidate_count < self.verified_candidate_count:
                raise ValueError("candidate_count must be at least verified_candidate_count")
        if [paper.selection_rank for paper in recommended] != list(range(1, len(recommended) + 1)):
            raise ValueError("recommended selection ranks must be consecutive")
        if [paper.selection_rank for paper in alternatives] != list(range(1, len(alternatives) + 1)):
            raise ValueError("alternative selection ranks must be consecutive")
        for paper in self.papers:
            if paper.date_evidence is None or paper.evidence is None:
                raise ValueError("schema v2 papers require date_evidence and evidence")
            if (
                paper.published_at is None
                or paper.published_at.isoformat() != paper.date_evidence.first_public_at
            ):
                raise ValueError("published_at must equal date_evidence.first_public_at")
            if paper.selection_kind == "recommended":
                relationship = paper.zotero_relationship
                if relationship is None or relationship.already_in_library is not False:
                    raise ValueError("recommended paper requires a non-duplicate Zotero decision")
        return self


class PaperResearchReviewRequest(_StrictRequest):
    status: Literal["new", "seen", "interested", "dismissed"]


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
    response: dict[str, object] = {"status": "succeeded", **asdict(result)}
    if payload.schema_version == "2":
        response.update(
            ingest_identity=payload.ingest_identity,
            candidate_count=payload.candidate_count,
            verified_candidate_count=payload.verified_candidate_count,
            recommended_count=payload.recommended_count,
        )
    return response


@router.get("/papers/research/radar/latest")
def latest_literature_radar(
    service: NewsService = Depends(get_news_service),
) -> dict[str, object]:
    run = service.latest_literature_radar()
    return {"run": asdict(run) if run is not None else None}


@router.patch("/papers/research/recommendations/{recommendation_id}/review")
def update_paper_research_review(
    recommendation_id: str,
    payload: PaperResearchReviewRequest,
    service: NewsService = Depends(get_news_service),
) -> dict[str, object]:
    result = service.update_paper_research_review(recommendation_id, payload.status)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "paper_research_recommendation_not_found",
                "message": "Research recommendation was not found",
            },
        )
    return asdict(result)


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
        papers=tuple(_research_paper(paper) for paper in payload.papers),
        run_kind=payload.run_kind,
        ingest_identity=payload.ingest_identity,
        profile=(
            payload.profile.model_dump(mode="json", by_alias=True)
            if payload.profile is not None
            else {}
        ),
        search_window=(
            payload.search_window.model_dump(mode="json", by_alias=True)
            if payload.search_window is not None
            else {}
        ),
        candidate_count=payload.candidate_count,
        verified_candidate_count=payload.verified_candidate_count,
        recommended_count=payload.recommended_count,
        warnings=tuple(payload.warnings),
        source_status=tuple(
            item.model_dump(mode="json") for item in payload.source_status
        ),
        zotero_context=(
            payload.zotero_context.model_dump(mode="json")
            if payload.zotero_context is not None
            else {}
        ),
        diagnostics=dict(payload.diagnostics),
    )


def _research_paper(paper: ResearchPaperRequest) -> PaperResearchPaperInput:
    relationship = (
        paper.zotero_relationship.model_dump(mode="json")
        if paper.zotero_relationship is not None
        else {}
    )
    return PaperResearchPaperInput(
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
        relationship_to_library=(
            paper.relationship_to_library
            or relationship.get("relationship_summary")
        ),
        source=paper.source.model_dump(exclude_none=True),
        publication_type=paper.publication_type,
        selection_kind=paper.selection_kind,
        selection_rank=paper.selection_rank,
        scientific_value_score=paper.scientific_value_score,
        recency_score=paper.recency_score,
        overall_score=paper.overall_score,
        date_evidence=(
            paper.date_evidence.model_dump(mode="json")
            if paper.date_evidence is not None
            else {}
        ),
        zotero_relationship=relationship,
        evidence=(
            paper.evidence.model_dump(mode="json")
            if paper.evidence is not None
            else {}
        ),
    )
