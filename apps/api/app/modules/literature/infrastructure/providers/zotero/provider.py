import re
from collections.abc import Mapping
from typing import Any

import httpx

from app.core.config import Settings
from app.modules.literature.application.errors import (
    InvalidCollectionIdentifierError,
    ProviderAuthenticationError,
    ProviderNotConfiguredError,
    ProviderUnavailableError,
)
from app.modules.literature.domain.models import (
    ChangedPaper,
    Collection,
    ExternalReference,
    LibraryChanges,
    Paper,
    PaperPage,
)

API_BASE_URL = "https://api.zotero.org"
API_VERSION = "3"
MAX_PAGE_SIZE = 100


class ZoteroWebProvider:
    """Read-only Zotero Web API v3 adapter for the personal user library."""

    name = "zotero"

    def __init__(self, app_settings: Settings, client: httpx.Client | None = None) -> None:
        self._settings = app_settings
        self._client = client or httpx.Client(timeout=15.0)

    @property
    def configured(self) -> bool:
        return self._settings.zotero_configured

    @property
    def library_id(self) -> str:
        return self._settings.zotero_user_id

    def list_collections(self) -> tuple[Collection, ...]:
        records = self._list_all("collections")
        return tuple(self._map_collection(record) for record in records)

    def list_papers(
        self,
        *,
        collection_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> PaperPage:
        if not 1 <= limit <= MAX_PAGE_SIZE:
            raise ValueError(f"limit must be between 1 and {MAX_PAGE_SIZE}")
        if offset < 0:
            raise ValueError("offset must be non-negative")

        path = "items/top"
        if collection_id:
            path = f"collections/{self._collection_key(collection_id)}/items/top"

        records, response = self._request(
            path,
            params={
                "format": "json",
                "itemType": "-attachment",
                "limit": str(limit),
                "start": str(offset),
            },
        )
        papers = tuple(
            self._map_paper(record)
            for record in records
            if self._item_type(record) not in {"attachment", "note", "annotation"}
        )
        return PaperPage(
            items=papers,
            total=self._total_results(response, default=len(papers)),
            library_version=response.headers.get("Last-Modified-Version"),
        )

    def list_changes(self, *, since: str) -> LibraryChanges:
        if not since:
            raise ValueError("since must be a library version")

        changed_collections, collections_version = self._list_all_with_version(
            "collections",
            params={"format": "json", "since": since},
        )
        changed_items, items_version = self._list_all_with_version(
            "items/top",
            params={
                "format": "json",
                "since": since,
                "itemType": "-attachment",
                "includeTrashed": "1",
            },
        )
        deleted_payload, deleted_response = self._request_payload(
            "deleted",
            params={"format": "json", "since": since},
        )
        if not isinstance(deleted_payload, dict):
            raise ProviderUnavailableError("Zotero returned an unexpected deleted response")

        changed_papers = tuple(
            ChangedPaper(
                paper=self._map_paper(record),
                collection_ids=self._collection_ids(record),
            )
            for record in changed_items
            if self._item_type(record) not in {"attachment", "note", "annotation"}
            and not self._is_trashed(record)
        )
        library_id = self._settings.zotero_user_id
        deleted_collection_ids = tuple(
            self._resource_id(library_id, key)
            for key in self._deleted_keys(deleted_payload, "collections")
        )
        deleted_paper_ids = tuple(
            self._resource_id(library_id, key)
            for key in self._deleted_keys(deleted_payload, "items")
        )
        library_version = self._latest_version(
            since,
            collections_version,
            items_version,
            deleted_response.headers.get("Last-Modified-Version"),
        )
        return LibraryChanges(
            collections=tuple(self._map_collection(record) for record in changed_collections),
            papers=changed_papers,
            deleted_collection_ids=deleted_collection_ids,
            deleted_paper_ids=deleted_paper_ids,
            library_version=library_version,
        )

    def _list_all(self, path: str) -> list[dict[str, Any]]:
        records, _ = self._list_all_with_version(path)
        return records

    def _list_all_with_version(
        self,
        path: str,
        *,
        params: Mapping[str, str] | None = None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        records: list[dict[str, Any]] = []
        offset = 0
        base_params = dict(params or {})
        library_version: str | None = None
        while True:
            page, response = self._request(
                path,
                params={**base_params, "limit": str(MAX_PAGE_SIZE), "start": str(offset)},
            )
            records.extend(page)
            library_version = response.headers.get("Last-Modified-Version") or library_version
            offset += len(page)
            total = self._total_results(response, default=offset)
            if not page or offset >= total:
                return records, library_version

    def _request(
        self,
        path: str,
        *,
        params: Mapping[str, str],
    ) -> tuple[list[dict[str, Any]], httpx.Response]:
        payload, response = self._request_payload(path, params=params)
        if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
            raise ProviderUnavailableError("Zotero returned an unexpected response shape")
        return payload, response

    def _request_payload(
        self,
        path: str,
        *,
        params: Mapping[str, str],
    ) -> tuple[Any, httpx.Response]:
        self._require_configuration()
        url = f"{API_BASE_URL}/users/{self._settings.zotero_user_id}/{path}"
        try:
            response = self._client.get(
                url,
                params=params,
                headers={
                    "Zotero-API-Version": API_VERSION,
                    "Zotero-API-Key": self._settings.zotero_api_key,
                },
            )
        except httpx.RequestError as error:
            raise ProviderUnavailableError("Zotero could not be reached") from error

        if response.status_code in {401, 403}:
            raise ProviderAuthenticationError("Zotero rejected the configured credentials")
        if response.is_error:
            raise ProviderUnavailableError(f"Zotero returned HTTP {response.status_code}")

        try:
            payload = response.json()
        except ValueError as error:
            raise ProviderUnavailableError("Zotero returned invalid JSON") from error
        return payload, response

    def _require_configuration(self) -> None:
        if not self.configured:
            raise ProviderNotConfiguredError("Zotero credentials are not configured")

    def _map_collection(self, record: Mapping[str, Any]) -> Collection:
        data = self._data(record)
        reference = self._reference(record, data)
        parent_key = data.get("parentCollection")
        parent_id = self._resource_id(reference.library_id, parent_key) if isinstance(parent_key, str) else None
        return Collection(
            id=self._resource_id(reference.library_id, reference.item_key),
            name=self._string(data.get("name")),
            parent_id=parent_id,
            external_ref=reference,
        )

    def _map_paper(self, record: Mapping[str, Any]) -> Paper:
        data = self._data(record)
        reference = self._reference(record, data)
        authors = tuple(
            name
            for creator in self._creators(data)
            if (name := self._creator_name(creator))
        )
        return Paper(
            id=self._resource_id(reference.library_id, reference.item_key),
            title=self._string(data.get("title")),
            authors=authors,
            abstract=self._optional_string(data.get("abstractNote")),
            year=self._year(data.get("date")),
            journal=self._first_non_empty(
                data.get("publicationTitle"),
                data.get("proceedingsTitle"),
                data.get("bookTitle"),
            ),
            doi=self._optional_string(data.get("DOI")),
            tags=tuple(
                tag["tag"]
                for tag in data.get("tags", [])
                if isinstance(tag, dict) and isinstance(tag.get("tag"), str) and tag["tag"]
            ),
            external_ref=reference,
        )

    def _reference(self, record: Mapping[str, Any], data: Mapping[str, Any]) -> ExternalReference:
        key = record.get("key") or data.get("key")
        if not isinstance(key, str) or not key:
            raise ProviderUnavailableError("Zotero response omitted an item key")
        library = record.get("library")
        library_id = library.get("id") if isinstance(library, dict) else None
        if library_id is None:
            library_id = self._settings.zotero_user_id
        return ExternalReference(provider=self.name, library_id=str(library_id), item_key=key)

    @staticmethod
    def _data(record: Mapping[str, Any]) -> Mapping[str, Any]:
        data = record.get("data")
        if not isinstance(data, dict):
            raise ProviderUnavailableError("Zotero response omitted item data")
        return data

    @staticmethod
    def _item_type(record: Mapping[str, Any]) -> str:
        data = record.get("data")
        return data.get("itemType", "") if isinstance(data, dict) else ""

    def _collection_ids(self, record: Mapping[str, Any]) -> tuple[str, ...]:
        data = record.get("data")
        collections = data.get("collections") if isinstance(data, dict) else None
        if not isinstance(collections, list):
            return ()
        library_id = self._settings.zotero_user_id
        return tuple(
            self._resource_id(library_id, key)
            for key in collections
            if isinstance(key, str) and key
        )

    @staticmethod
    def _is_trashed(record: Mapping[str, Any]) -> bool:
        data = record.get("data")
        return bool(data.get("deleted")) if isinstance(data, dict) else False

    @staticmethod
    def _deleted_keys(payload: Mapping[str, Any], name: str) -> tuple[str, ...]:
        values = payload.get(name, [])
        if not isinstance(values, list):
            raise ProviderUnavailableError("Zotero returned invalid deleted object keys")
        return tuple(value for value in values if isinstance(value, str) and value)

    @staticmethod
    def _latest_version(since: str, *versions: str | None) -> str:
        candidates = [version for version in (since, *versions) if version]
        try:
            return str(max(int(version) for version in candidates))
        except ValueError:
            return candidates[-1]

    def _collection_key(self, collection_id: str) -> str:
        prefix = f"{self.name}:{self._settings.zotero_user_id}:"
        if not collection_id.startswith(prefix):
            raise InvalidCollectionIdentifierError("Collection does not belong to this Zotero library")
        key = collection_id.removeprefix(prefix)
        if not key or ":" in key:
            raise InvalidCollectionIdentifierError("Collection identifier is invalid")
        return key

    def _resource_id(self, library_id: str, item_key: Any) -> str:
        return f"{self.name}:{library_id}:{item_key}"

    @staticmethod
    def _string(value: Any) -> str:
        return value.strip() if isinstance(value, str) else ""

    def _optional_string(self, value: Any) -> str | None:
        string = self._string(value)
        return string or None

    def _first_non_empty(self, *values: Any) -> str | None:
        for value in values:
            string = self._optional_string(value)
            if string:
                return string
        return None

    @staticmethod
    def _creators(data: Mapping[str, Any]) -> list[Mapping[str, Any]]:
        creators = data.get("creators")
        return [creator for creator in creators if isinstance(creator, dict)] if isinstance(creators, list) else []

    def _creator_name(self, creator: Mapping[str, Any]) -> str:
        literal_name = self._optional_string(creator.get("name"))
        if literal_name:
            return literal_name
        return " ".join(
            part
            for part in (self._optional_string(creator.get("firstName")), self._optional_string(creator.get("lastName")))
            if part
        )

    @staticmethod
    def _year(value: Any) -> int | None:
        if not isinstance(value, str):
            return None
        match = re.search(r"(?<!\d)(\d{4})(?!\d)", value)
        return int(match.group(1)) if match else None

    @staticmethod
    def _total_results(response: httpx.Response, *, default: int) -> int:
        raw_total = response.headers.get("Total-Results")
        try:
            return int(raw_total) if raw_total is not None else default
        except ValueError:
            return default
