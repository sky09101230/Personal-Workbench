from fastapi.testclient import TestClient

from app.main import app
from app.modules.news.application.service import NewsService
from app.modules.news.domain.models import FeedItem, FeedItemType, Topic
from app.modules.news.infrastructure.cache.sqlite import SQLiteNewsRepository
from app.modules.news.infrastructure.providers.demo.provider import (
    DEFAULT_TOPICS,
    DEMO_TOPICS,
    DemoNewsProvider,
)


client = TestClient(app)


def test_default_news_topics_cover_diffractive_optical_computing_and_metasurface() -> None:
    assert [topic.id for topic in DEFAULT_TOPICS] == [
        "diffractive-neural-networks",
        "optical-computing",
        "metasurface",
    ]
    assert DEFAULT_TOPICS[0].keywords == (
        "diffractive neural network",
        "diffractive deep neural network",
        "diffractive deep network",
        "diffractive optical neural network",
        "D2NN",
    )
    assert DEFAULT_TOPICS[0].negative_keywords == (
        "job posting",
        "smart grid",
        "electric vehicle",
    )
    assert DEFAULT_TOPICS[1].name == "Optical Computing"
    assert DEFAULT_TOPICS[1].keywords == ("optical computing",)
    assert DEFAULT_TOPICS[1].enabled_sources == ("openalex",)
    assert DEFAULT_TOPICS[2].name == "Metasurface"
    assert DEFAULT_TOPICS[2].keywords == ("metasurface",)
    assert DEFAULT_TOPICS[2].enabled_sources == ("openalex",)


def test_news_refresh_and_filtered_feed_api(tmp_path) -> None:
    original_service = app.state.news_service
    app.state.news_service = NewsService(
        providers=(DemoNewsProvider(),),
        repository=SQLiteNewsRepository(f"sqlite:///{(tmp_path / 'api.db').as_posix()}"),
        topics=DEMO_TOPICS,
    )
    try:
        empty_feed = client.get("/api/news/feed")
        topics = client.get("/api/news/topics")
        refresh = client.post("/api/news/refresh")
        repository_feed = client.get("/api/news/feed?type=github_repo&topic=research-tools")
        paged_feed = client.get("/api/news/feed?limit=2&offset=1")
    finally:
        app.state.news_service = original_service

    assert empty_feed.status_code == 200
    assert empty_feed.json()["total"] == 0
    assert [item["id"] for item in topics.json()["items"]] == ["optical-ml", "research-tools"]
    assert refresh.status_code == 200
    assert refresh.json()["providers"] == ["demo"]
    assert refresh.json()["stored"] == 5
    assert repository_feed.status_code == 200
    assert repository_feed.json()["total"] == 1
    assert repository_feed.json()["items"][0]["type"] == "github_repo"
    assert "research-tools" in repository_feed.json()["items"][0]["topics"]
    assert paged_feed.json()["limit"] == 2
    assert paged_feed.json()["offset"] == 1
    assert len(paged_feed.json()["items"]) == 2


def test_news_feed_query_validation() -> None:
    assert client.get("/api/news/feed?type=unsupported").status_code == 422
    assert client.get("/api/news/feed?limit=101").status_code == 422
    assert client.get("/api/news/feed?offset=-1").status_code == 422
    assert client.post("/api/news/refresh?type=unsupported").status_code == 422


def test_news_refresh_accepts_item_type_scope(tmp_path) -> None:
    original_service = app.state.news_service
    app.state.news_service = NewsService(
        providers=(DemoNewsProvider(),),
        repository=SQLiteNewsRepository(f"sqlite:///{(tmp_path / 'typed-refresh.db').as_posix()}"),
        topics=DEMO_TOPICS,
    )
    try:
        refresh = client.post("/api/news/refresh?type=paper")
        feed = client.get("/api/news/feed")
    finally:
        app.state.news_service = original_service

    assert refresh.status_code == 200
    assert refresh.json()["providers"] == ["demo"]
    assert refresh.json()["stored"] == 1
    assert feed.json()["total"] == 1
    assert feed.json()["items"][0]["type"] == "paper"


def test_news_refresh_without_matching_provider_preserves_cached_type(tmp_path) -> None:
    original_service = app.state.news_service
    repository = SQLiteNewsRepository(f"sqlite:///{(tmp_path / 'no-provider.db').as_posix()}")
    topic = Topic(id="research", name="Research", keywords=("research",))
    cached = FeedItem(
        id="github:cached",
        type=FeedItemType.GITHUB_REPO,
        source="github",
        title="Research repository",
        summary=None,
        url="https://example.com/repository",
    )
    repository.save_refresh(
        items=(cached,),
        topics=(topic,),
        item_topics={cached.id: (topic.id,)},
    )
    app.state.news_service = NewsService(providers=(), repository=repository, topics=(topic,))
    try:
        refresh = client.post("/api/news/refresh?type=github_repo")
        feed = client.get("/api/news/feed?type=github_repo")
    finally:
        app.state.news_service = original_service

    assert refresh.status_code == 200
    assert refresh.json()["providers"] == []
    assert refresh.json()["stored"] == 1
    assert feed.json()["total"] == 1
    assert feed.json()["items"][0]["id"] == "github:cached"


def test_news_refresh_returns_stable_source_error(tmp_path) -> None:
    original_service = app.state.news_service
    app.state.news_service = NewsService(
        providers=(_FailingProvider(),),
        repository=SQLiteNewsRepository(f"sqlite:///{(tmp_path / 'failure.db').as_posix()}"),
    )
    try:
        response = client.post("/api/news/refresh")
    finally:
        app.state.news_service = original_service

    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "news_source_unavailable"
    assert "private upstream response" not in response.text


class _FailingProvider:
    name = "broken"
    item_types = tuple(FeedItemType)

    def fetch_items(self, *, topics):
        del topics
        raise RuntimeError("private upstream response")
