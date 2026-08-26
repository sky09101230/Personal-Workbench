from collections.abc import Iterable, Mapping
from typing import Protocol

from app.modules.news.domain.models import FeedItem, FeedItemType, FeedPage, Topic


class NewsSourcePort(Protocol):
    name: str
    item_types: tuple[FeedItemType, ...]
    uses_topics: bool

    def fetch_items(self, *, topics: tuple[Topic, ...]) -> tuple[FeedItem, ...]:
        """Return provider data normalized to the News domain contract."""
        ...


class NewsSummarizerPort(Protocol):
    item_types: tuple[FeedItemType, ...]

    def summarize(self, items: tuple[FeedItem, ...]) -> tuple[FeedItem, ...]:
        """Return summary-enriched items without changing their identity or order."""
        ...


class NewsRepository(Protocol):
    def get_source_refresh_slot(self, source: str) -> str | None:
        ...

    def topics_match(self, topics: Iterable[Topic]) -> bool:
        ...

    def save_refresh(
        self,
        *,
        items: Iterable[FeedItem],
        topics: Iterable[Topic],
        item_topics: Mapping[str, Iterable[str]],
        source_slots: Mapping[str, str] | None = None,
        item_types: Iterable[FeedItemType] | None = None,
    ) -> int:
        ...

    def list_feed(
        self,
        *,
        item_type: FeedItemType | None = None,
        topic_id: str | None = None,
        period: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> FeedPage:
        ...
