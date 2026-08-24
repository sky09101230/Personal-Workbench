from dataclasses import dataclass
from datetime import datetime, timezone

from app.modules.news.application.errors import InvalidFeedItemError, NewsError, NewsSourceError
from app.modules.news.application.ports import NewsRepository, NewsSourcePort
from app.modules.news.domain.models import FeedItem, FeedItemType, FeedPage, RefreshResult, Topic


@dataclass(frozen=True)
class NewsService:
    providers: tuple[NewsSourcePort, ...]
    repository: NewsRepository
    topics: tuple[Topic, ...] = ()

    def list_feed(
        self,
        *,
        item_type: FeedItemType | None = None,
        topic_id: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> FeedPage:
        return self.repository.list_feed(
            item_type=item_type,
            topic_id=topic_id,
            limit=limit,
            offset=offset,
        )

    def list_topics(self) -> tuple[Topic, ...]:
        return self.topics

    def refresh(self) -> RefreshResult:
        items: list[FeedItem] = []
        for provider in self.providers:
            try:
                provider_items = provider.fetch_items()
            except NewsError:
                raise
            except Exception as error:
                raise NewsSourceError(f"News source '{provider.name}' could not be refreshed") from error
            for item in provider_items:
                _validate_item(provider, item)
                items.append(item)

        item_topics = {
            item.id: tuple(topic.id for topic in self.topics if _matches_topic(item, topic))
            for item in items
        }
        stored = self.repository.save_refresh(
            items=items,
            topics=self.topics,
            item_topics=item_topics,
        )
        return RefreshResult(
            providers=tuple(provider.name for provider in self.providers),
            fetched=len(items),
            stored=stored,
            topic_matches=sum(len(matches) for matches in item_topics.values()),
            refreshed_at=datetime.now(timezone.utc).isoformat(),
        )


def _validate_item(provider: NewsSourcePort, item: FeedItem) -> None:
    if item.source != provider.name:
        raise InvalidFeedItemError("Feed item source does not match its provider")
    if not item.id.startswith(f"{provider.name}:"):
        raise InvalidFeedItemError("Feed item id must be namespaced by its provider")
    if not item.title.strip() or not item.url.strip():
        raise InvalidFeedItemError("Feed item title and url are required")


def _matches_topic(item: FeedItem, topic: Topic) -> bool:
    if topic.enabled_sources and item.source not in topic.enabled_sources:
        return False
    text = " ".join((item.title, item.summary or "", *item.authors)).casefold()
    if any(keyword.casefold() in text for keyword in topic.negative_keywords):
        return False
    return not topic.keywords or any(keyword.casefold() in text for keyword in topic.keywords)
