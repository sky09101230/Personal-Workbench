import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urlparse

import httpx

from app.modules.news.application.errors import NewsSourceError
from app.modules.news.domain.models import FeedItem, FeedItemType, Topic


TRENDING_URL = "https://github.com/trending"
TRENDING_PERIODS = ("daily", "weekly", "monthly")
_COUNT = re.compile(r"(\d[\d,]*)")

logger = logging.getLogger(__name__)


class GitHubTrendingProvider:
    """Fetch and normalize the official GitHub Trending rankings."""

    name = "github_trending"
    item_types = (FeedItemType.GITHUB_REPO,)
    uses_topics = False

    def __init__(
        self,
        client: httpx.Client | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._client = client or httpx.Client(timeout=15.0)
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def fetch_items(self, *, topics: tuple[Topic, ...]) -> tuple[FeedItem, ...]:
        del topics
        fetched_at = self._clock().astimezone(timezone.utc).isoformat()
        items_by_id: dict[str, FeedItem] = {}
        for period in TRENDING_PERIODS:
            for repository in self._fetch_period(period):
                item = _to_feed_item(repository, period=period, fetched_at=fetched_at)
                if item is not None:
                    items_by_id.setdefault(item.id, item)
        return tuple(items_by_id.values())

    def _fetch_period(self, period: str) -> tuple["_TrendingRepository", ...]:
        try:
            response = self._client.get(
                TRENDING_URL,
                params={"since": period},
                headers={
                    "Accept": "text/html,application/xhtml+xml",
                    "User-Agent": "Personal-Workbench/0.1",
                },
            )
        except httpx.TimeoutException as error:
            logger.warning("GitHub Trending %s request timed out: %s", period, error)
            raise NewsSourceError(f"GitHub Trending {period} request timed out") from error
        except httpx.HTTPError as error:
            logger.warning("GitHub Trending is unavailable: %s", error)
            raise NewsSourceError("GitHub Trending is unavailable") from error

        if response.is_error:
            logger.warning(
                "GitHub Trending is unavailable (HTTP %s, period=%s)",
                response.status_code,
                period,
            )
            raise NewsSourceError("GitHub Trending is unavailable")
        content_type = response.headers.get("content-type", "").partition(";")[0].strip().lower()
        if content_type != "text/html":
            logger.warning("GitHub Trending returned unexpected content %s", content_type)
            raise NewsSourceError("GitHub Trending returned unexpected content")

        parser = _TrendingParser()
        try:
            parser.feed(response.text)
            parser.close()
        except (UnicodeError, ValueError) as error:
            logger.warning("GitHub Trending returned malformed HTML: %s", error)
            raise NewsSourceError("GitHub Trending returned malformed HTML") from error

        repositories = tuple(
            repository
            for repository in parser.repositories
            if _is_complete(repository)
        )
        if not repositories:
            logger.warning("GitHub Trending %s returned no valid repositories", period)
            raise NewsSourceError(f"GitHub Trending {period} returned no valid repositories")
        return repositories


@dataclass
class _TrendingRepository:
    rank: int
    owner: str | None = None
    repository: str | None = None
    description: str | None = None
    language: str | None = None
    stars: int | None = None
    forks: int | None = None
    stars_period: int | None = None


class _TrendingParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.repositories: list[_TrendingRepository] = []
        self._current: _TrendingRepository | None = None
        self._article_rank = 0
        self._in_heading = False
        self._capture_field: str | None = None
        self._capture_tag: str | None = None
        self._capture_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        classes = set((attributes.get("class") or "").split())
        if tag == "article" and "Box-row" in classes:
            self._article_rank += 1
            self._current = _TrendingRepository(rank=self._article_rank)
            return
        if self._current is None:
            return
        if tag == "h2":
            self._in_heading = True
            return
        if tag == "a":
            href = attributes.get("href") or ""
            if self._in_heading:
                identity = _repository_identity(href)
                if identity is not None:
                    self._current.owner, self._current.repository = identity
            if href.endswith("/stargazers"):
                self._start_capture("stars", tag)
            elif href.endswith("/forks"):
                self._start_capture("forks", tag)
            return
        if tag == "p" and "col-9" in classes:
            self._start_capture("description", tag)
        elif tag == "span" and attributes.get("itemprop") == "programmingLanguage":
            self._start_capture("language", tag)
        elif tag == "span" and "float-sm-right" in classes:
            self._start_capture("stars_period", tag)

    def handle_endtag(self, tag: str) -> None:
        if self._current is None:
            return
        if self._capture_tag == tag:
            self._finish_capture()
        if tag == "h2":
            self._in_heading = False
        elif tag == "article":
            self.repositories.append(self._current)
            self._current = None
            self._in_heading = False
            self._capture_field = None
            self._capture_tag = None
            self._capture_text = []

    def handle_data(self, data: str) -> None:
        if self._capture_field is not None:
            self._capture_text.append(data)

    def _start_capture(self, field: str, tag: str) -> None:
        if self._capture_field is None:
            self._capture_field = field
            self._capture_tag = tag
            self._capture_text = []

    def _finish_capture(self) -> None:
        if self._current is None or self._capture_field is None:
            return
        value = " ".join("".join(self._capture_text).split())
        if self._capture_field in {"stars", "forks", "stars_period"}:
            setattr(self._current, self._capture_field, _parse_count(value))
        else:
            setattr(self._current, self._capture_field, value or None)
        self._capture_field = None
        self._capture_tag = None
        self._capture_text = []


def _repository_identity(href: str) -> tuple[str, str] | None:
    parsed = urlparse(href)
    if parsed.scheme or parsed.netloc or not parsed.path.startswith("/"):
        return None
    parts = tuple(part for part in parsed.path.split("/") if part)
    if len(parts) != 2:
        return None
    owner, repository = parts
    return (owner, repository) if owner.strip() and repository.strip() else None


def _parse_count(value: str) -> int | None:
    match = _COUNT.search(value)
    return int(match.group(1).replace(",", "")) if match else None


def _to_feed_item(
    repository: _TrendingRepository,
    *,
    period: str,
    fetched_at: str,
) -> FeedItem | None:
    if not _is_complete(repository):
        return None
    full_name = f"{repository.owner}/{repository.repository}"
    return FeedItem(
        id=f"github_trending:{period}:{full_name.casefold()}",
        type=FeedItemType.GITHUB_REPO,
        source="github_trending",
        title=full_name,
        summary=repository.description,
        url=f"https://github.com/{full_name}",
        fetched_at=fetched_at,
        metadata={
            "owner": repository.owner,
            "repository": repository.repository,
            "language": repository.language,
            "stars": repository.stars,
            "forks": repository.forks,
            "stars_period": repository.stars_period,
            "rank": repository.rank,
            "period": period,
        },
    )


def _is_complete(repository: _TrendingRepository) -> bool:
    return (
        repository.owner is not None
        and repository.repository is not None
        and repository.stars is not None
        and repository.forks is not None
        and repository.stars_period is not None
    )
