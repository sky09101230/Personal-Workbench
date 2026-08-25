from dataclasses import replace

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

class _Provider:
    def __init__(self, name: str, *items: FeedItem) -> None:
        self.name = name
        self._items = items
        self.item_types = tuple(dict.fromkeys(item.type for item in items))
        self.calls = 0

    def fetch_items(self, *, topics: tuple[Topic, ...]) -> tuple[FeedItem, ...]:
        del topics
        self.calls += 1
        return self._items


class _FailingProvider:
    name = "broken"
    item_types = tuple(FeedItemType)

    def fetch_items(self, *, topics: tuple[Topic, ...]) -> tuple[FeedItem, ...]:
        del topics
        raise RuntimeError("private upstream response")


class _Summarizer:
    def __init__(self) -> None:
        self.item_ids: tuple[str, ...] = ()

    def summarize(self, items: tuple[FeedItem, ...]) -> tuple[FeedItem, ...]:
        self.item_ids = tuple(item.id for item in items)
        return tuple(replace(item, summary="简洁的中文摘要。") for item in items)

class _RecordingRepository:
    def __init__(self) -> None:
        self.saved = False
        self.items: tuple[FeedItem, ...] = ()
        self.item_topics: dict[str, tuple[str, ...]] = {}
        self.item_types: tuple[FeedItemType, ...] | None = None

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
