from dataclasses import dataclass, field

from app.modules.news.domain.models import FeedItem


@dataclass(frozen=True)
class Paper:
    id: str
    title: str
    authors: tuple[str, ...]
    doi: str | None
    arxiv_id: str | None
    openalex_id: str | None
    canonical_title: str | None
    published_at: str | None
    venue: str | None
    publication_type: str | None
    url: str | None
    pdf_url: str | None
    abstract: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class PaperResearchRun:
    id: str
    task_key: str
    run_key: str
    schema_version: str
    status: str
    generated_at: str
    ingested_at: str
    agent_type: str
    agent_model: str
    prompt_version: str
    query_plan: tuple[str, ...]
    papers_found: int
    papers_accepted: int
    created_at: str
    run_kind: str = "paper_research"
    ingest_identity: str | None = None
    profile: dict[str, object] = field(default_factory=dict)
    search_window: dict[str, object] = field(default_factory=dict)
    candidate_count: int | None = None
    verified_candidate_count: int | None = None
    recommended_count: int | None = None
    warnings: tuple[str, ...] = ()
    source_status: tuple[dict[str, object], ...] = ()
    zotero_context: dict[str, object] = field(default_factory=dict)
    diagnostics: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class PaperResearchRecommendation:
    id: str
    run_id: str
    paper_id: str
    ai_summary: str
    recommendation_reason: str
    relevance_score: float | None
    novelty_score: float | None
    topics: tuple[str, ...]
    matched_topics: tuple[str, ...]
    relationship_to_library: str | None
    source: dict[str, object] = field(default_factory=dict)
    created_at: str = ""
    selection_kind: str = "recommended"
    selection_rank: int | None = None
    scientific_value_score: float | None = None
    recency_score: float | None = None
    overall_score: float | None = None
    date_evidence: dict[str, object] = field(default_factory=dict)
    zotero_relationship: dict[str, object] = field(default_factory=dict)
    evidence: dict[str, object] = field(default_factory=dict)
    review_status: str = "new"


@dataclass(frozen=True)
class PaperResearchAgent:
    type: str
    model: str
    prompt_version: str


@dataclass(frozen=True)
class PaperResearchPaperInput:
    title: str
    authors: tuple[str, ...]
    doi: str | None
    arxiv_id: str | None
    openalex_id: str | None
    published_at: str | None
    venue: str | None
    url: str | None
    pdf_url: str | None
    abstract: str | None
    topics: tuple[str, ...]
    matched_topics: tuple[str, ...]
    ai_summary: str
    recommendation_reason: str
    relevance_score: float | None
    novelty_score: float | None
    relationship_to_library: str | None
    source: dict[str, object] = field(default_factory=dict)
    publication_type: str | None = None
    selection_kind: str = "recommended"
    selection_rank: int | None = None
    scientific_value_score: float | None = None
    recency_score: float | None = None
    overall_score: float | None = None
    date_evidence: dict[str, object] = field(default_factory=dict)
    zotero_relationship: dict[str, object] = field(default_factory=dict)
    evidence: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class PaperResearchIngest:
    schema_version: str
    task_key: str
    run_key: str
    generated_at: str
    agent: PaperResearchAgent
    query_plan: tuple[str, ...]
    papers: tuple[PaperResearchPaperInput, ...]
    run_kind: str = "paper_research"
    ingest_identity: str | None = None
    profile: dict[str, object] = field(default_factory=dict)
    search_window: dict[str, object] = field(default_factory=dict)
    candidate_count: int | None = None
    verified_candidate_count: int | None = None
    recommended_count: int | None = None
    warnings: tuple[str, ...] = ()
    source_status: tuple[dict[str, object], ...] = ()
    zotero_context: dict[str, object] = field(default_factory=dict)
    diagnostics: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class PaperResearchIngestResult:
    run_id: str
    created_run: bool
    created_papers: int
    updated_papers: int
    created_recommendations: int
    updated_recommendations: int
    papers_found: int
    papers_accepted: int


@dataclass(frozen=True)
class PaperResearchFeedPage:
    items: tuple[FeedItem, ...]
    total: int
    limit: int
    offset: int


@dataclass(frozen=True)
class PaperResearchRadarItem:
    recommendation_id: str
    paper_id: str
    selection_kind: str
    selection_rank: int | None
    title: str
    authors: tuple[str, ...]
    doi: str | None
    arxiv_id: str | None
    published_at: str | None
    venue: str | None
    publication_type: str | None
    url: str
    ai_summary: str
    recommendation_reason: str
    relevance_score: float | None
    novelty_score: float | None
    scientific_value_score: float | None
    recency_score: float | None
    overall_score: float | None
    relationship_to_library: str | None
    zotero_relationship: dict[str, object]
    date_evidence: dict[str, object]
    evidence: dict[str, object]
    source: dict[str, object]
    review_status: str


@dataclass(frozen=True)
class PaperResearchRadarRun:
    id: str
    task_key: str
    run_key: str
    generated_at: str
    ingested_at: str
    profile: dict[str, object]
    search_window: dict[str, object]
    candidate_count: int
    verified_candidate_count: int
    recommended_count: int
    warnings: tuple[str, ...]
    source_status: tuple[dict[str, object], ...]
    zotero_context: dict[str, object]
    diagnostics: dict[str, object]
    recommendations: tuple[PaperResearchRadarItem, ...]
    verified_alternatives: tuple[PaperResearchRadarItem, ...]


@dataclass(frozen=True)
class PaperResearchReviewResult:
    recommendation_id: str
    review_status: str
