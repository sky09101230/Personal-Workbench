from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Lock
from zoneinfo import ZoneInfo

from app.modules.news.application.errors import InvalidFeedItemError, NewsError, NewsSourceError
from app.modules.news.application.ports import NewsRepository, NewsSourcePort, NewsSummarizerPort
from app.modules.news.domain.models import FeedItem, FeedItemType, FeedPage, RefreshResult, Topic
from app.modules.news.application.research import normalize_research_ingest
from app.modules.news.domain.research_models import (
    PaperResearchFeedPage,
    PaperResearchIngest,
    PaperResearchIngestResult,
)


_SHANGHAI = ZoneInfo("Asia/Shanghai")


@dataclass(frozen=True)
class NewsService:
    providers: tuple[NewsSourcePort, ...]
    repository: NewsRepository
    topics: tuple[Topic, ...] = ()
    summarizer: NewsSummarizerPort | None = None
    slot_limited_sources: tuple[str, ...] = ()
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)
    refresh_lock: Lock = field(default_factory=Lock, compare=False, repr=False)

    def list_feed(
        self,
        *,
        item_type: FeedItemType | None = None,
        topic_id: str | None = None,
        period: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> FeedPage:
        return self.repository.list_feed(
            item_type=item_type,
            topic_id=topic_id,
            period=period,
            limit=limit,
            offset=offset,
        )

    def list_topics(self) -> tuple[Topic, ...]:
        return self.topics

    def ingest_paper_research(
        self,
        payload: PaperResearchIngest,
    ) -> PaperResearchIngestResult:
        return self.repository.ingest_paper_research(normalize_research_ingest(payload))

    def list_paper_research(
        self,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> PaperResearchFeedPage:
        return self.repository.list_paper_research(limit=limit, offset=offset)

    def refresh(self, *, item_type: FeedItemType | None = None) -> RefreshResult:
        with self.refresh_lock:
            return self._refresh_locked(item_type=item_type)

    def _refresh_locked(self, *, item_type: FeedItemType | None) -> RefreshResult:
        now = self.clock()
        current_slot = _half_day_slot(now)
        selected_providers = tuple(
            provider
            for provider in self.providers
            if item_type is None or item_type in provider.item_types
        )
        provider_names = tuple(provider.name for provider in selected_providers)
        if not selected_providers:
            cached = self.repository.list_feed(item_type=item_type, limit=1, offset=0)
            return RefreshResult(
                providers=(),
                fetched=0,
                stored=cached.total,
                topic_matches=0,
                refreshed_at=now.astimezone(timezone.utc).isoformat(),
            )
        has_slot_limited_provider = any(
            provider.name in self.slot_limited_sources for provider in selected_providers
        )
        topics_current = (
            self.repository.topics_match(self.topics) if has_slot_limited_provider else False
        )
        providers = tuple(
            provider
            for provider in selected_providers
            if not (
                provider.name in self.slot_limited_sources
                and topics_current
                and self.repository.get_source_refresh_slot(provider.name) == current_slot
            )
        )
        if not providers:
            cached = self.repository.list_feed(item_type=item_type, limit=1, offset=0)
            return RefreshResult(
                providers=provider_names,
                fetched=0,
                stored=cached.total,
                topic_matches=0,
                refreshed_at=now.astimezone(timezone.utc).isoformat(),
            )

        fetched = 0
        items_by_id: dict[str, FeedItem] = {}
        for provider in providers:
            try:
                provider_items = provider.fetch_items(topics=self.topics)
            except NewsError:
                raise
            except Exception as error:
                raise NewsSourceError(f"News source '{provider.name}' could not be refreshed") from error
            for item in provider_items:
                _validate_item(provider, item)
                if item_type is not None and item.type is not item_type:
                    continue
                fetched += 1
                items_by_id.setdefault(item.id, item)

        items = tuple(items_by_id.values())
        topic_sources = {provider.name for provider in providers if provider.uses_topics}
        item_topics = {
            item.id: (
                tuple(topic.id for topic in self.topics if _matches_topic(item, topic))
                if item.source in topic_sources
                else ()
            )
            for item in items
        }
        items = tuple(
            item
            for item in items
            if item.source not in topic_sources or item_topics[item.id]
        )
        item_topics = {item.id: item_topics[item.id] for item in items}
        items = _summarize_items(items, self.summarizer)
        source_slots = {
            provider.name: current_slot
            for provider in providers
            if provider.name in self.slot_limited_sources
        }
        refreshed_types = (
            (item_type,)
            if item_type is not None
            else tuple(
                dict.fromkeys(
                    provider_item_type
                    for provider in providers
                    for provider_item_type in provider.item_types
                )
            )
        )
        stored = self.repository.save_refresh(
            items=items,
            topics=self.topics,
            item_topics=item_topics,
            source_slots=source_slots,
            item_types=refreshed_types,
        )
        return RefreshResult(
            providers=provider_names,
            fetched=fetched,
            stored=stored,
            topic_matches=sum(len(matches) for matches in item_topics.values()),
            refreshed_at=now.astimezone(timezone.utc).isoformat(),
        )


def _half_day_slot(now: datetime) -> str:
    if now.tzinfo is None:
        raise ValueError("News refresh clock must return a timezone-aware datetime")
    local = now.astimezone(_SHANGHAI)
    period = "AM" if local.hour < 12 else "PM"
    return f"{local.date().isoformat()}-{period}"


def _summarize_items(
    items: tuple[FeedItem, ...],
    summarizer: NewsSummarizerPort | None,
) -> tuple[FeedItem, ...]:
    if summarizer is None:
        return items
    candidates = tuple(item for item in items if item.type in summarizer.item_types)
    if not candidates:
        return items
    summarized_by_id = {item.id: item for item in summarizer.summarize(candidates)}
    return tuple(summarized_by_id.get(item.id, item) for item in items)


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
