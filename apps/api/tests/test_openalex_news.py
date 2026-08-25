from datetime import date

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import app
from app.modules.news.application.errors import NewsSourceError
from app.modules.news.application.service import NewsService
from app.modules.news.domain.models import FeedItem, FeedItemType, Topic
from app.modules.news.infrastructure.cache.sqlite import SQLiteNewsRepository
from app.modules.news.infrastructure.providers.openalex.provider import (
    RECENT_DAYS,
    RESULTS_PER_TOPIC,
    OpenAlexPaperProvider,
)


client = TestClient(app)
TOPICS = (
    Topic(
        id="optical",
        name="Optical",
        keywords=("optical",),
        enabled_sources=("openalex",),
    ),
)


def test_openalex_maps_complete_work_and_recent_query() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"results": [_complete_work()]})

    provider = _provider(handler, api_key="secret", today=date(2026, 8, 24))

    items = provider.fetch_items(topics=TOPICS)

    assert len(items) == 1
    item = items[0]
    assert item.id == "openalex:W123"
    assert item.type is FeedItemType.PAPER
    assert item.source == "openalex"
    assert item.title == "Optical research methods"
    assert item.summary == "Optical research methods"
    assert item.authors == ("Ada Lovelace", "Grace Hopper")
    assert item.published_at == "2026-08-23"
    assert item.url == "https://doi.org/10.1000/example"
    assert item.metadata == {
        "doi": "10.1000/example",
        "venue": "Journal of Optical Research",
        "topics": ["Optical Computing"],
        "keywords": ["Diffractive optics"],
        "cited_by_count": 7,
        "open_access": {
            "is_oa": True,
            "oa_status": "gold",
            "oa_url": "https://example.org/paper",
        },
        "work_type": "article",
    }

    assert len(requests) == 1
    params = requests[0].url.params
    assert requests[0].url.path == "/works"
    assert params["search"] == "optical"
    assert params["filter"] == "from_publication_date:2026-08-17,to_publication_date:2026-08-24"
    assert params["sort"] == "publication_date:desc"
    assert params["per_page"] == str(RESULTS_PER_TOPIC)
    assert "cursor" not in params
    assert params["api_key"] == "secret"
    assert RECENT_DAYS == 7


def test_openalex_combines_topic_synonyms_with_boolean_or() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"results": []})

    topic = Topic(
        id="diffractive-neural-networks",
        name="Diffractive Neural Networks",
        keywords=(
            "diffractive neural network",
            "diffractive deep neural network",
            "D2NN",
        ),
        enabled_sources=("openalex",),
    )

    _provider(handler).fetch_items(topics=(topic,))

    assert requests[0].url.params["search"] == (
        '("diffractive neural network" OR "diffractive deep neural network" OR D2NN)'
    )


def test_openalex_handles_missing_abstract_and_url_fallbacks_without_key() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "api_key" not in request.url.params
        landing = _complete_work(work_id="W124", doi=None)
        landing["abstract_inverted_index"] = None
        fallback = _complete_work(work_id="W125", doi=None)
        fallback["abstract_inverted_index"] = None
        fallback["primary_location"] = None
        return httpx.Response(200, json={"results": [landing, fallback]})

    items = _provider(handler).fetch_items(topics=TOPICS)

    assert [item.summary for item in items] == [None, None]
    assert items[0].url == "https://example.org/landing"
    assert items[1].url == "https://openalex.org/W125"
    assert items[0].published_at == "2026-08-23"


def test_openalex_deduplicates_one_work_returned_for_multiple_topics() -> None:
    request_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        return httpx.Response(200, json={"results": [_complete_work()]})

    topics = (
        TOPICS[0],
        Topic(
            id="research",
            name="Research",
            keywords=("research",),
            enabled_sources=("openalex",),
        ),
    )
    repository = _RecordingRepository()
    service = NewsService(
        providers=(_provider(handler),),
        repository=repository,
        topics=topics,
    )

    result = service.refresh()

    assert request_count == 2
    assert result.fetched == 1
    assert result.stored == 1
    assert result.topic_matches == 2
    assert repository.item_ids == ("openalex:W123",)
    assert repository.item_topics == {"openalex:W123": ("optical", "research")}


@pytest.mark.parametrize("status_code", [401, 403, 429, 500])
def test_openalex_http_failures_become_stable_source_errors(status_code: int) -> None:
    provider = _provider(
        lambda request: httpx.Response(status_code, request=request, json={"error": "private"})
    )

    with pytest.raises(NewsSourceError) as raised:
        provider.fetch_items(topics=TOPICS)

    assert raised.value.code == "news_source_unavailable"
    assert "private" not in str(raised.value)


def test_openalex_timeout_becomes_stable_source_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("private timeout detail", request=request)

    with pytest.raises(NewsSourceError, match="timed out"):
        _provider(handler).fetch_items(topics=TOPICS)


@pytest.mark.parametrize("payload", [{"unexpected": []}, {"results": "not-a-list"}])
def test_openalex_malformed_response_becomes_stable_source_error(payload: object) -> None:
    provider = _provider(lambda request: httpx.Response(200, request=request, json=payload))

    with pytest.raises(NewsSourceError, match="malformed"):
        provider.fetch_items(topics=TOPICS)


def test_openalex_refresh_failure_preserves_existing_cache(tmp_path) -> None:
    repository = SQLiteNewsRepository(f"sqlite:///{(tmp_path / 'preserve.db').as_posix()}")
    cached = FeedItem(
        id="openalex:W999",
        type=FeedItemType.PAPER,
        source="openalex",
        title="Cached optical paper",
        summary=None,
        url="https://openalex.org/W999",
    )
    repository.save_refresh(
        items=(cached,),
        topics=TOPICS,
        item_topics={cached.id: ("optical",)},
    )
    provider = _provider(
        lambda request: httpx.Response(429, request=request, json={"error": "rate limited"})
    )

    with pytest.raises(NewsSourceError):
        NewsService(providers=(provider,), repository=repository, topics=TOPICS).refresh()

    page = repository.list_feed(item_type=FeedItemType.PAPER)
    assert page.total == 1
    assert page.items[0].id == "openalex:W999"
    assert page.items[0].title == "Cached optical paper"


def test_papers_feed_api_returns_provider_normalized_openalex_schema(tmp_path) -> None:
    original_service = app.state.news_service
    provider = _provider(
        lambda request: httpx.Response(200, request=request, json={"results": [_complete_work()]})
    )
    app.state.news_service = NewsService(
        providers=(provider,),
        repository=SQLiteNewsRepository(f"sqlite:///{(tmp_path / 'api.db').as_posix()}"),
        topics=TOPICS,
    )
    try:
        refresh = client.post("/api/news/refresh")
        feed = client.get("/api/news/feed?type=paper")
    finally:
        app.state.news_service = original_service

    assert refresh.status_code == 200
    assert refresh.json()["providers"] == ["openalex"]
    assert feed.status_code == 200
    assert feed.json()["total"] == 1
    item = feed.json()["items"][0]
    assert item["id"] == "openalex:W123"
    assert item["type"] == "paper"
    assert item["source"] == "openalex"
    assert item["authors"] == ["Ada Lovelace", "Grace Hopper"]
    assert item["published_at"] == "2026-08-23"
    assert item["url"] == "https://doi.org/10.1000/example"
    assert item["topics"] == ["optical"]
    assert item["metadata"]["venue"] == "Journal of Optical Research"
    assert item["metadata"]["doi"] == "10.1000/example"
    assert item["metadata"]["cited_by_count"] == 7


def _provider(handler, *, api_key: str = "", today: date = date(2026, 8, 24)):
    transport = httpx.MockTransport(handler)
    return OpenAlexPaperProvider(
        Settings(
            database_url="sqlite:///./data/workbench.db",
            cors_origins=["http://localhost:5173"],
            zotero_user_id="",
            zotero_api_key="",
            openalex_api_key=api_key,
        ),
        client=httpx.Client(transport=transport),
        today=lambda: today,
    )


def _complete_work(*, work_id: str = "W123", doi: str | None = "https://doi.org/10.1000/example"):
    return {
        "id": f"https://openalex.org/{work_id}",
        "doi": doi,
        "title": "Optical research methods",
        "display_name": "Optical research methods",
        "abstract_inverted_index": {
            "research": [1],
            "methods": [2],
            "Optical": [0],
        },
        "authorships": [
            {"author": {"display_name": "Ada Lovelace"}},
            {"author": {"display_name": "Grace Hopper"}},
        ],
        "publication_date": "2026-08-23",
        "primary_location": {
            "landing_page_url": "https://example.org/landing",
            "source": {"display_name": "Journal of Optical Research"},
        },
        "topics": [{"id": "https://openalex.org/T1", "display_name": "Optical Computing"}],
        "keywords": [{"id": "https://openalex.org/keywords/diffractive-optics", "display_name": "Diffractive optics"}],
        "cited_by_count": 7,
        "open_access": {
            "is_oa": True,
            "oa_status": "gold",
            "oa_url": "https://example.org/paper",
            "any_repository_has_fulltext": None,
        },
        "type": "article",
    }


class _RecordingRepository:
    def __init__(self) -> None:
        self.item_ids: tuple[str, ...] = ()
        self.item_topics: dict[str, tuple[str, ...]] = {}

    def save_refresh(self, *, items, topics, item_topics) -> int:
        del topics
        feed_items = tuple(items)
        self.item_ids = tuple(item.id for item in feed_items)
        self.item_topics = {key: tuple(value) for key, value in item_topics.items()}
        return len(feed_items)

    def list_feed(self, **kwargs):
        raise NotImplementedError
