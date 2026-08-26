import re
from collections.abc import Callable, Mapping
from datetime import date, datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

import httpx

from app.core.config import Settings
from app.modules.news.application.errors import NewsSourceError
from app.modules.news.domain.models import FeedItem, FeedItemType, Topic


API_BASE_URL = "https://api.openalex.org"
RECENT_DAYS = 7
RESULTS_PER_TOPIC = 10
_WORK_ID = re.compile(r"^W\d+$")
_SELECT_FIELDS = (
    "id,doi,title,display_name,abstract_inverted_index,authorships,"
    "publication_date,primary_location,topics,keywords,cited_by_count,"
    "open_access,type"
)


class OpenAlexPaperProvider:
    """Discover recent papers through the official OpenAlex Works API."""

    name = "openalex"
    item_types = (FeedItemType.PAPER,)
    uses_topics = True

    def __init__(
        self,
        app_settings: Settings,
        client: httpx.Client | None = None,
        today: Callable[[], date] | None = None,
    ) -> None:
        self._settings = app_settings
        self._client = client or httpx.Client(timeout=15.0)
        self._today = today or (lambda: datetime.now(timezone.utc).date())

    def fetch_items(self, *, topics: tuple[Topic, ...]) -> tuple[FeedItem, ...]:
        fetched_at = datetime.now(timezone.utc).isoformat()
        items_by_id: dict[str, FeedItem] = {}
        for topic in topics:
            keywords = tuple(keyword.strip() for keyword in topic.keywords if keyword.strip())
            if not keywords or (topic.enabled_sources and self.name not in topic.enabled_sources):
                continue

            for record in self._request_works(keywords):
                item = _map_work(record, fetched_at=fetched_at)
                if _matches_negative_keyword(item, topic):
                    continue
                items_by_id.setdefault(item.id, item)
        return tuple(items_by_id.values())

    def _request_works(self, keywords: tuple[str, ...]) -> tuple[Mapping[str, Any], ...]:
        to_date = self._today()
        from_date = to_date - timedelta(days=RECENT_DAYS)
        params = {
            "search": _search_query(keywords),
            "filter": f"from_publication_date:{from_date.isoformat()},to_publication_date:{to_date.isoformat()}",
            "sort": "publication_date:desc",
            "per_page": str(RESULTS_PER_TOPIC),
            "select": _SELECT_FIELDS,
        }
        if self._settings.openalex_api_key:
            params["api_key"] = self._settings.openalex_api_key

        try:
            response = self._client.get(f"{API_BASE_URL}/works", params=params)
        except httpx.TimeoutException as error:
            raise NewsSourceError("OpenAlex request timed out") from error
        except httpx.HTTPError as error:
            raise NewsSourceError("OpenAlex is unavailable") from error

        if response.status_code in {401, 403}:
            raise NewsSourceError("OpenAlex authentication failed")
        if response.status_code == 429:
            raise NewsSourceError("OpenAlex rate limit exceeded")
        if response.is_error:
            raise NewsSourceError("OpenAlex is unavailable")

        try:
            payload = response.json()
        except ValueError as error:
            raise NewsSourceError("OpenAlex returned a malformed response") from error
        if not isinstance(payload, Mapping) or not isinstance(payload.get("results"), list):
            raise NewsSourceError("OpenAlex returned a malformed response")

        results: list[Mapping[str, Any]] = []
        for record in payload["results"]:
            if not isinstance(record, Mapping):
                raise NewsSourceError("OpenAlex returned a malformed response")
            results.append(record)
        return tuple(results)


def _search_query(keywords: tuple[str, ...]) -> str:
    unique_keywords = tuple(dict.fromkeys(keywords))
    if len(unique_keywords) == 1:
        return unique_keywords[0]
    return "(" + " OR ".join(_search_term(keyword) for keyword in unique_keywords) + ")"


def _search_term(keyword: str) -> str:
    escaped = keyword.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"' if " " in escaped else escaped


def _map_work(record: Mapping[str, Any], *, fetched_at: str) -> FeedItem:
    work_key = _work_key(record.get("id"))
    title = _string(record.get("title")) or _string(record.get("display_name"))
    if work_key is None or title is None:
        raise NewsSourceError("OpenAlex returned a malformed response")

    doi = _doi(record)
    primary_location = _mapping(record.get("primary_location"))
    landing_page = _url(primary_location.get("landing_page_url"))
    openalex_url = f"https://openalex.org/{work_key}"
    url = f"https://doi.org/{doi}" if doi else landing_page or openalex_url

    source = _mapping(primary_location.get("source"))
    metadata: dict[str, object] = {
        "doi": doi,
        "venue": _string(source.get("display_name")),
        "topics": _display_names(record.get("topics")),
        "keywords": _display_names(record.get("keywords")),
        "cited_by_count": _integer(record.get("cited_by_count")),
        "open_access": _open_access(record.get("open_access")),
        "work_type": _string(record.get("type")),
    }
    return FeedItem(
        id=f"openalex:{work_key}",
        type=FeedItemType.PAPER,
        source="openalex",
        title=title,
        summary=_abstract(record.get("abstract_inverted_index")),
        url=url,
        authors=_authors(record.get("authorships")),
        published_at=_publication_date(record.get("publication_date")),
        fetched_at=fetched_at,
        metadata=metadata,
    )


def _work_key(value: object) -> str | None:
    raw = _string(value)
    if raw is None:
        return None
    key = raw.rstrip("/").rsplit("/", 1)[-1]
    return key if _WORK_ID.fullmatch(key) else None


def _doi(record: Mapping[str, Any]) -> str | None:
    value = _string(record.get("doi"))
    if value is None:
        value = _string(_mapping(record.get("ids")).get("doi"))
    if value is None:
        return None
    normalized = value.removeprefix("https://doi.org/").removeprefix("http://doi.org/")
    normalized = normalized.removeprefix("doi:").strip()
    return normalized or None


def _authors(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    names: list[str] = []
    for authorship in value:
        if not isinstance(authorship, Mapping):
            continue
        author = _mapping(authorship.get("author"))
        name = _string(author.get("display_name")) or _string(authorship.get("raw_author_name"))
        if name and name not in names:
            names.append(name)
    return tuple(names)


def _abstract(value: object) -> str | None:
    if not isinstance(value, Mapping):
        return None
    words_by_position: dict[int, str] = {}
    for word, positions in value.items():
        if not isinstance(word, str) or not isinstance(positions, list):
            continue
        for position in positions:
            if isinstance(position, int) and not isinstance(position, bool) and position >= 0:
                words_by_position.setdefault(position, word)
    if not words_by_position:
        return None
    return " ".join(words_by_position[position] for position in sorted(words_by_position))


def _publication_date(value: object) -> str | None:
    raw = _string(value)
    if raw is None:
        return None
    try:
        date.fromisoformat(raw)
    except ValueError:
        return None
    return raw


def _display_names(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    names: list[str] = []
    for entry in value[:10]:
        if not isinstance(entry, Mapping):
            continue
        name = _string(entry.get("display_name"))
        if name and name not in names:
            names.append(name)
    return names


def _open_access(value: object) -> dict[str, object]:
    data = _mapping(value)
    fields = ("is_oa", "oa_status", "oa_url", "any_repository_has_fulltext")
    return {field: data[field] for field in fields if data.get(field) is not None}


def _matches_negative_keyword(item: FeedItem, topic: Topic) -> bool:
    text = " ".join((item.title, item.summary or "", *item.authors)).casefold()
    return any(keyword.casefold() in text for keyword in topic.negative_keywords if keyword)


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _string(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _integer(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _url(value: object) -> str | None:
    raw = _string(value)
    if raw is None:
        return None
    parsed = urlparse(raw)
    return raw if parsed.scheme in {"http", "https"} and parsed.netloc else None
