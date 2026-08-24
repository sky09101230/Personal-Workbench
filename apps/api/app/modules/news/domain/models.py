from dataclasses import dataclass, field
from enum import Enum


class FeedItemType(str, Enum):
    PAPER = "paper"
    GITHUB_REPO = "github_repo"
    GITHUB_SKILL = "github_skill"
    AI_NEWS = "ai_news"
    X_POST = "x_post"


@dataclass(frozen=True)
class Topic:
    id: str
    name: str
    keywords: tuple[str, ...] = ()
    negative_keywords: tuple[str, ...] = ()
    enabled_sources: tuple[str, ...] = ()


@dataclass(frozen=True)
class FeedItem:
    id: str
    type: FeedItemType
    source: str
    title: str
    summary: str | None
    url: str
    authors: tuple[str, ...] = ()
    published_at: str | None = None
    fetched_at: str | None = None
    topics: tuple[str, ...] = ()
    metadata: dict[str, object] = field(default_factory=dict)
    read: bool = False
    saved: bool = False
    hidden: bool = False


@dataclass(frozen=True)
class FeedPage:
    items: tuple[FeedItem, ...]
    total: int
    limit: int
    offset: int


@dataclass(frozen=True)
class RefreshResult:
    providers: tuple[str, ...]
    fetched: int
    stored: int
    topic_matches: int
    refreshed_at: str
