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
    published_at: str | None
    venue: str | None
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
    source: dict[str, str] = field(default_factory=dict)
    created_at: str = ""


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
    source: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class PaperResearchIngest:
    schema_version: str
    task_key: str
    run_key: str
    generated_at: str
    agent: PaperResearchAgent
    query_plan: tuple[str, ...]
    papers: tuple[PaperResearchPaperInput, ...]


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
