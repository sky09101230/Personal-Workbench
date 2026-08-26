from datetime import datetime, timezone

import httpx
import pytest

from app.modules.news.application.errors import NewsSourceError
from app.modules.news.domain.models import FeedItemType, Topic
from app.modules.news.infrastructure.providers.github.trending.provider import (
    GitHubTrendingProvider,
)


TRENDING_HTML = """
<!doctype html>
<html>
  <body>
    <article class="Box-row">
      <h2 class="h3 lh-condensed">
        <a href="/octo/alpha"> octo / alpha </a>
      </h2>
      <p class="col-9 color-fg-muted my-1 pr-4">A useful &amp; focused repository.</p>
      <span itemprop="programmingLanguage">Python</span>
      <a href="/octo/alpha/stargazers"><svg></svg> 1,234 </a>
      <a href="/octo/alpha/forks"><svg></svg> 56 </a>
      <span class="d-inline-block float-sm-right">78 stars today</span>
    </article>
    <article class="Box-row">
      <h2><a href="/sample/beta">sample / beta</a></h2>
      <a href="/sample/beta/stargazers">90</a>
      <a href="/sample/beta/forks">4</a>
      <span class="d-inline-block float-sm-right">3 stars today</span>
    </article>
  </body>
</html>
"""


def test_provider_requests_all_periods_and_normalizes_ranked_repositories() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            text=TRENDING_HTML,
            headers={"Content-Type": "text/html; charset=utf-8"},
        )

    provider = GitHubTrendingProvider(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        clock=lambda: datetime(2026, 8, 25, 3, tzinfo=timezone.utc),
    )

    items = provider.fetch_items(
        topics=(Topic(id="papers", name="Papers", enabled_sources=("openalex",)),)
    )

    assert len(requests) == 3
    assert [request.url.path for request in requests] == ["/trending"] * 3
    assert [request.url.params["since"] for request in requests] == [
        "daily",
        "weekly",
        "monthly",
    ]
    assert requests[0].headers["accept"] == "text/html,application/xhtml+xml"
    assert len(items) == 6
    assert all(item.type is FeedItemType.GITHUB_REPO for item in items)
    assert items[0].id == "github_trending:daily:octo/alpha"
    assert items[0].source == "github_trending"
    assert items[0].title == "octo/alpha"
    assert items[0].summary == "A useful & focused repository."
    assert items[0].url == "https://github.com/octo/alpha"
    assert items[0].fetched_at == "2026-08-25T03:00:00+00:00"
    assert items[0].topics == ()
    assert items[0].metadata == {
        "owner": "octo",
        "repository": "alpha",
        "language": "Python",
        "stars": 1234,
        "forks": 56,
        "stars_period": 78,
        "rank": 1,
        "period": "daily",
    }
    assert items[1].summary is None
    assert items[1].metadata["language"] is None
    assert items[1].metadata["rank"] == 2
    assert items[2].id == "github_trending:weekly:octo/alpha"
    assert items[2].metadata["rank"] == 1
    assert items[2].metadata["period"] == "weekly"
    assert items[4].id == "github_trending:monthly:octo/alpha"
    assert items[4].metadata["period"] == "monthly"


@pytest.mark.parametrize(
    ("status_code", "content_type", "body"),
    [
        (429, "text/html", TRENDING_HTML),
        (200, "application/json", "{}"),
        (200, "text/html", "<html><body>No ranking</body></html>"),
        (
            200,
            "text/html",
            '<article class="Box-row"><h2><a href="/owner/repo">owner/repo</a></h2></article>',
        ),
    ],
)
def test_provider_rejects_upstream_and_malformed_responses(
    status_code: int,
    content_type: str,
    body: str,
) -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                status_code,
                text=body,
                headers={"Content-Type": content_type},
            )
        )
    )

    with pytest.raises(NewsSourceError) as raised:
        GitHubTrendingProvider(client=client).fetch_items(topics=())

    assert raised.value.code == "news_source_unavailable"


def test_provider_maps_timeout_to_stable_news_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    provider = GitHubTrendingProvider(
        client=httpx.Client(transport=httpx.MockTransport(handler))
    )

    with pytest.raises(NewsSourceError) as raised:
        provider.fetch_items(topics=())

    assert raised.value.code == "news_source_unavailable"


def test_provider_fails_whole_refresh_when_later_period_fails() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.params["since"] == "monthly":
            return httpx.Response(503, text="unavailable", headers={"Content-Type": "text/html"})
        return httpx.Response(
            200,
            text=TRENDING_HTML,
            headers={"Content-Type": "text/html"},
        )

    provider = GitHubTrendingProvider(
        client=httpx.Client(transport=httpx.MockTransport(handler))
    )

    with pytest.raises(NewsSourceError):
        provider.fetch_items(topics=())

    assert [request.url.params["since"] for request in requests] == [
        "daily",
        "weekly",
        "monthly",
    ]
