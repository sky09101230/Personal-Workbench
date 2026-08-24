from collections.abc import Iterable, Mapping
from typing import Protocol

from app.modules.news.domain.models import FeedItem, FeedItemType, FeedPage, Topic


class NewsSourcePort(Protocol):
    name: str

    def fetch_items(self) -> tuple[FeedItem, ...]:
        """Return provider data normalized to the News domain contract."""
        ...


class NewsRepository(Protocol):
    def save_refresh(
        self,
        *,
        items: Iterable[FeedItem],
        topics: Iterable[Topic],
        item_topics: Mapping[str, Iterable[str]],
    ) -> int:
        ...

    def list_feed(
        self,
        *,
        item_type: FeedItemType | None = None,
        topic_id: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> FeedPage:
        ...
