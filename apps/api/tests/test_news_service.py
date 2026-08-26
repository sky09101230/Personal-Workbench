from dataclasses import replace
from datetime import datetime, timezone

from app.modules.news.application.errors import NewsSourceError
from app.modules.news.application.service import NewsService
from app.modules.news.domain.models import FeedItem, FeedItemType, FeedPage, Topic


def test_refresh_collects_providers_and_matches_simple_topics() -> None:
    repository = _RecordingRepository()
    service = NewsService(
        providers=(
            _Provider(
                "papers",
                FeedItem(
                    id="papers:1",
                    type=FeedItemType.PAPER,
                    source="papers",
                    title="Optical research result",
                    summary="No blocked phrase here.",
                    url="https://example.com/paper",
                ),
            ),
            _Provider(
                "github",
                FeedItem(
                    id="github:1",
                    type=FeedItemType.GITHUB_REPO,
                    source="github",
                    title="Optical job posting archive",
                    summary=None,
                    url="https://example.com/repo",
                ),
                uses_topics=True,
            ),
        ),
        repository=repository,
        topics=(
            Topic(
                id="optical",
                name="Optical",
                keywords=("optical",),
                negative_keywords=("job posting",),
                enabled_sources=("papers", "github"),
            ),
        ),
    )

    result = service.refresh()

    assert result.providers == ("papers", "github")
    assert result.fetched == 2
    assert result.stored == 1
    assert result.topic_matches == 1
    assert repository.item_topics == {"papers:1": ("optical",)}


def test_provider_failure_does_not_call_repository() -> None:
    repository = _RecordingRepository()
    service = NewsService(
        providers=(_FailingProvider(),),
        repository=repository,
    )

    try:
        service.refresh()
    except NewsSourceError as error:
        assert error.code == "news_source_unavailable"
    else:
        raise AssertionError("Expected NewsSourceError")

    assert repository.saved is False


def test_refresh_summarizes_and_persists_only_topic_matched_papers() -> None:
    repository = _RecordingRepository()
    summarizer = _Summarizer()
    matched = FeedItem(
        id="papers:matched",
        type=FeedItemType.PAPER,
        source="papers",
        title="Diffractive optical system",
        summary="The original optical abstract used for Topic Match.",
        url="https://example.com/matched",
    )
    unmatched = FeedItem(
        id="papers:unmatched",
        type=FeedItemType.PAPER,
        source="papers",
        title="Unrelated system",
        summary="No relevant phrase.",
        url="https://example.com/unmatched",
    )
    service = NewsService(
        providers=(_Provider("papers", matched, unmatched),),
        repository=repository,
        topics=(Topic(id="optical", name="Optical", keywords=("optical",)),),
        summarizer=summarizer,
    )

    result = service.refresh()

    assert result.fetched == 2
    assert result.stored == 1
    assert result.topic_matches == 1
    assert summarizer.item_ids == ("papers:matched",)
    assert repository.items[0].summary == "简洁的中文摘要。"
    assert repository.item_topics == {"papers:matched": ("optical",)}


def test_refresh_selects_only_providers_for_requested_item_type() -> None:
    repository = _RecordingRepository()
    paper_provider = _Provider(
        "papers",
        FeedItem(
            id="papers:1",
            type=FeedItemType.PAPER,
            source="papers",
            title="Optical paper",
            summary=None,
            url="https://example.com/paper",
        ),
    )
    github_provider = _Provider(
        "github",
        FeedItem(
            id="github:1",
            type=FeedItemType.GITHUB_REPO,
            source="github",
            title="Optical repository",
            summary=None,
            url="https://example.com/repository",
        ),
    )
    service = NewsService(
        providers=(paper_provider, github_provider),
        repository=repository,
        topics=(Topic(id="optical", name="Optical", keywords=("optical",)),),
    )

    result = service.refresh(item_type=FeedItemType.PAPER)

    assert result.providers == ("papers",)
    assert paper_provider.calls == 1
    assert github_provider.calls == 0
    assert repository.item_types == (FeedItemType.PAPER,)
    assert tuple(item.id for item in repository.items) == ("papers:1",)


def test_refresh_keeps_items_from_provider_that_does_not_use_topics() -> None:
    repository = _RecordingRepository()
    provider = _Provider(
        "github",
        FeedItem(
            id="github:repo",
            type=FeedItemType.GITHUB_REPO,
            source="github",
            title="Repository without paper keywords",
            summary=None,
            url="https://example.com/repository",
        ),
        uses_topics=False,
    )
    service = NewsService(
        providers=(provider,),
        repository=repository,
        topics=(
            Topic(
                id="papers-only",
                name="Papers only",
                keywords=("diffractive",),
                enabled_sources=("openalex",),
            ),
        ),
    )

    result = service.refresh(item_type=FeedItemType.GITHUB_REPO)

    assert result.stored == 1
    assert result.topic_matches == 0
    assert repository.item_topics == {"github:repo": ()}


def test_current_slot_provider_does_not_block_due_provider() -> None:
    repository = _RecordingRepository(
        topics_current=True,
        source_slots={"openalex": "2026-08-25-AM"},
    )
    openalex = _Provider(
        "openalex",
        FeedItem(
            id="openalex:paper",
            type=FeedItemType.PAPER,
            source="openalex",
            title="Diffractive paper",
            summary=None,
            url="https://example.com/paper",
        ),
    )
    github = _Provider(
        "github",
        FeedItem(
            id="github:repo",
            type=FeedItemType.GITHUB_REPO,
            source="github",
            title="Trending repository",
            summary=None,
            url="https://example.com/repository",
        ),
        uses_topics=False,
    )
    service = NewsService(
        providers=(openalex, github),
        repository=repository,
        slot_limited_sources=("openalex",),
        clock=lambda: datetime(
            2026,
            8,
            25,
            1,
            tzinfo=timezone.utc,
        ),
    )

    result = service.refresh()

    assert result.providers == ("openalex", "github")
    assert openalex.calls == 0
    assert github.calls == 1
    assert repository.item_types == (FeedItemType.GITHUB_REPO,)
    assert tuple(item.id for item in repository.items) == ("github:repo",)


def test_refresh_sends_every_supported_github_item_to_summarizer() -> None:
    repository = _RecordingRepository()
    summarizer = _GitHubSummarizer()
    daily = FeedItem(
        id="github:daily:repo",
        type=FeedItemType.GITHUB_REPO,
        source="github",
        title="owner/repo",
        summary=None,
        url="https://github.com/owner/repo",
    )
    weekly = replace(daily, id="github:weekly:repo", summary="Source description")
    service = NewsService(
        providers=(_Provider("github", daily, weekly, uses_topics=False),),
        repository=repository,
        summarizer=summarizer,
    )

    result = service.refresh(item_type=FeedItemType.GITHUB_REPO)

    assert result.stored == 2
    assert summarizer.item_ids == (daily.id, weekly.id)
    assert [item.summary for item in repository.items] == ["GitHub AI summary", "GitHub AI summary"]


class _Provider:
    def __init__(self, name: str, *items: FeedItem, uses_topics: bool = True) -> None:
        self.name = name
        self._items = items
        self.item_types = tuple(dict.fromkeys(item.type for item in items))
        self.uses_topics = uses_topics
        self.calls = 0

    def fetch_items(self, *, topics: tuple[Topic, ...]) -> tuple[FeedItem, ...]:
        del topics
        self.calls += 1
        return self._items


class _FailingProvider:
    name = "broken"
    item_types = tuple(FeedItemType)
    uses_topics = True

    def fetch_items(self, *, topics: tuple[Topic, ...]) -> tuple[FeedItem, ...]:
        del topics
        raise RuntimeError("private upstream response")


class _Summarizer:
    item_types = (FeedItemType.PAPER,)

    def __init__(self) -> None:
        self.item_ids: tuple[str, ...] = ()

    def summarize(self, items: tuple[FeedItem, ...]) -> tuple[FeedItem, ...]:
        self.item_ids = tuple(item.id for item in items)
        return tuple(replace(item, summary="简洁的中文摘要。") for item in items)


class _GitHubSummarizer:
    item_types = (FeedItemType.GITHUB_REPO,)

    def __init__(self) -> None:
        self.item_ids: tuple[str, ...] = ()

    def summarize(self, items: tuple[FeedItem, ...]) -> tuple[FeedItem, ...]:
        self.item_ids = tuple(item.id for item in items)
        return tuple(replace(item, summary="GitHub AI summary") for item in items)

class _RecordingRepository:
    def __init__(
        self,
        *,
        topics_current: bool = False,
        source_slots: dict[str, str] | None = None,
    ) -> None:
        self.saved = False
        self.items: tuple[FeedItem, ...] = ()
        self.item_topics: dict[str, tuple[str, ...]] = {}
        self.item_types: tuple[FeedItemType, ...] | None = None
        self._topics_current = topics_current
        self._source_slots = source_slots or {}

    def topics_match(self, topics) -> bool:
        del topics
        return self._topics_current

    def get_source_refresh_slot(self, source: str) -> str | None:
        return self._source_slots.get(source)

    def save_refresh(
        self,
        *,
        items,
        topics,
        item_topics,
        source_slots=None,
        item_types=None,
    ) -> int:
        del topics, source_slots
        self.saved = True
        feed_items = tuple(items)
        self.items = feed_items
        self.item_topics = {key: tuple(value) for key, value in item_topics.items()}
        self.item_types = None if item_types is None else tuple(item_types)
        return len(feed_items)

    def list_feed(self, **kwargs) -> FeedPage:
        return FeedPage(items=(), total=0, limit=20, offset=0)
