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
    assert result.stored == 2
    assert result.topic_matches == 1
    assert repository.item_topics == {"papers:1": ("optical",), "github:1": ()}


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


class _Provider:
    def __init__(self, name: str, *items: FeedItem) -> None:
        self.name = name
        self._items = items

    def fetch_items(self) -> tuple[FeedItem, ...]:
        return self._items


class _FailingProvider:
    name = "broken"

    def fetch_items(self) -> tuple[FeedItem, ...]:
        raise RuntimeError("private upstream response")


class _RecordingRepository:
    def __init__(self) -> None:
        self.saved = False
        self.item_topics: dict[str, tuple[str, ...]] = {}

    def save_refresh(self, *, items, topics, item_topics) -> int:
        self.saved = True
        feed_items = tuple(items)
        self.item_topics = {key: tuple(value) for key, value in item_topics.items()}
        return len(feed_items)

    def list_feed(self, **kwargs) -> FeedPage:
        return FeedPage(items=(), total=0, limit=20, offset=0)
