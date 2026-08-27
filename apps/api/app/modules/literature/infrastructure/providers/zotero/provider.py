import logging
import re
from collections.abc import Mapping
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from app.core.config import Settings
from app.modules.literature.application.errors import (
    InvalidCollectionIdentifierError,
    PdfUnavailableError,
    ProviderAuthenticationError,
    ProviderNotConfiguredError,
    ProviderUnavailableError,
)
from app.modules.literature.domain.models import (
    Attachment,
    ChangedPaper,
    Collection,
    ExternalReference,
    LibraryChanges,
    LiteratureAssets,
    Note,
    Paper,
    PaperPage,
    ProviderFile,
)

API_BASE_URL = "https://api.zotero.org"
API_VERSION = "3"
MAX_PAGE_SIZE = 100

logger = logging.getLogger(__name__)


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
        changed_assets, assets_version = self._list_assets_with_version(
            params={"format": "json", "since": since},
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
        trashed_paper_ids = tuple(
            self._resource_id(library_id, self._reference(record, self._data(record)).item_key)
            for record in changed_items
            if self._is_trashed(record)
        )
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
            assets_version,
        )
        return LibraryChanges(
            collections=tuple(self._map_collection(record) for record in changed_collections),
            papers=changed_papers,
            notes=changed_assets.notes,
            attachments=changed_assets.attachments,
            deleted_collection_ids=deleted_collection_ids,
            deleted_item_ids=tuple(
                dict.fromkeys(
                    (*deleted_paper_ids, *trashed_paper_ids, *changed_assets.deleted_item_ids)
                )
            ),
            library_version=library_version,
        )

    def list_assets(self) -> LiteratureAssets:
        assets, _ = self._list_assets_with_version(params={"format": "json"})
        return assets

    def open_attachment(
        self,
        attachment: Attachment,
        *,
        range_header: str | None = None,
    ) -> ProviderFile:
        reference = attachment.external_ref
        if (
            reference is None
            or reference.provider != self.name
            or reference.library_id != self.library_id
            or not attachment.downloadable
        ):
            raise PdfUnavailableError("The PDF attachment is not available through Zotero Web API")

        url = f"{API_BASE_URL}/users/{self.library_id}/items/{reference.item_key}/file"
        request_headers = self._headers()
        if range_header:
            request_headers["Range"] = range_header
        response = self._send_file_request(url, headers=request_headers)
        redirected = False
        if response.is_redirect:
            location = response.headers.get("Location")
            response.close()
            redirect_url = urljoin(url, location) if location else ""
            if urlparse(redirect_url).scheme != "https":
                raise PdfUnavailableError("Zotero returned an invalid attachment redirect")
            redirect_headers = {"Range": range_header} if range_header else {}
            response = self._send_file_request(redirect_url, headers=redirect_headers)
            redirected = True

        if response.status_code in {401, 403}:
            response.close()
            if redirected:
                raise PdfUnavailableError("The redirected Zotero PDF file is unavailable")
            raise ProviderAuthenticationError("Zotero rejected the configured credentials")
        if response.status_code in {404, 410}:
            response.close()
            raise PdfUnavailableError("The Zotero PDF file is unavailable")
        if response.status_code not in {200, 206}:
            status_code = response.status_code
            response.close()
            raise ProviderUnavailableError(f"Zotero returned HTTP {status_code} for an attachment")

        return ProviderFile(
            filename=attachment.filename or "paper.pdf",
            content_type=response.headers.get("Content-Type") or "application/pdf",
            chunks=response.iter_raw(),
            status_code=response.status_code,
            content_length=response.headers.get("Content-Length"),
            content_range=response.headers.get("Content-Range"),
            accept_ranges=response.headers.get("Accept-Ranges"),
            close=response.close,
        )

    def _list_assets_with_version(
        self,
        *,
        params: Mapping[str, str],
    ) -> tuple[LiteratureAssets, str | None]:
        records, library_version = self._list_all_with_version(
            "items",
            params={
                **params,
                "itemType": "note || attachment || annotation",
                "includeTrashed": "1",
            },
        )
        active_records = [record for record in records if not self._is_trashed(record)]
        deleted_item_ids = tuple(
            self._resource_id(
                self.library_id,
                self._reference(record, self._data(record)).item_key,
            )
            for record in records
            if self._is_trashed(record)
        )
        attachment_parents = {
            self._reference(record, self._data(record)).item_key: self._parent_key(record)
            for record in active_records
            if self._item_type(record) == "attachment" and self._parent_key(record)
        }

        attachments = tuple(
            attachment
            for record in active_records
            if self._item_type(record) == "attachment"
            if (attachment := self._map_attachment(record)) is not None
        )
        notes: list[Note] = []
        for record in active_records:
            item_type = self._item_type(record)
            if item_type == "note":
                note = self._map_note(record)
            elif item_type == "annotation":
                parent_attachment_key = self._parent_key(record)
                paper_key = attachment_parents.get(parent_attachment_key or "")
                if parent_attachment_key and not paper_key:
                    parent_record = self._get_item(parent_attachment_key)
                    paper_key = self._parent_key(parent_record)
                    if paper_key:
                        attachment_parents[parent_attachment_key] = paper_key
                note = self._map_annotation(record, paper_key)
            else:
                continue
            if note is not None:
                notes.append(note)

        return (
            LiteratureAssets(
                notes=tuple(notes),
                attachments=attachments,
                deleted_item_ids=deleted_item_ids,
                library_version=library_version,
            ),
            library_version,
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
                headers=self._headers(),
            )
        except httpx.RequestError as error:
            logger.warning("Zotero request failed: %s", error)
            raise ProviderUnavailableError("Zotero could not be reached") from error

        if response.status_code in {401, 403}:
            logger.warning(
                "Zotero rejected the configured credentials (HTTP %s)",
                response.status_code,
            )
            raise ProviderAuthenticationError("Zotero rejected the configured credentials")
        if response.is_error:
            logger.warning("Zotero returned HTTP %s for %s", response.status_code, path)
            raise ProviderUnavailableError(f"Zotero returned HTTP {response.status_code}")

        try:
            payload = response.json()
        except ValueError as error:
            logger.warning("Zotero returned invalid JSON for %s: %s", path, error)
            raise ProviderUnavailableError("Zotero returned invalid JSON") from error
        return payload, response

    def _headers(self) -> dict[str, str]:
        return {
            "Zotero-API-Version": API_VERSION,
            "Zotero-API-Key": self._settings.zotero_api_key,
        }

    def _send_file_request(self, url: str, *, headers: Mapping[str, str]) -> httpx.Response:
        self._require_configuration()
        try:
            request = self._client.build_request("GET", url, headers=headers)
            return self._client.send(request, stream=True, follow_redirects=False)
        except httpx.RequestError as error:
            logger.warning("Zotero attachment request failed: %s", error)
            raise ProviderUnavailableError("Zotero attachment could not be reached") from error

    def _get_item(self, item_key: str) -> Mapping[str, Any]:
        payload, _ = self._request_payload(
            f"items/{item_key}",
            params={"format": "json"},
        )
        if not isinstance(payload, dict):
            raise ProviderUnavailableError("Zotero returned an unexpected item response")
        return payload

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

    def _map_note(self, record: Mapping[str, Any]) -> Note | None:
        data = self._data(record)
        parent_key = self._parent_key(record)
        if not parent_key:
            return None
        reference = self._reference(record, data)
        return Note(
            id=self._resource_id(reference.library_id, reference.item_key),
            paper_id=self._resource_id(reference.library_id, parent_key),
            content=self._string(data.get("note")),
            external_ref=reference,
        )

    def _map_annotation(self, record: Mapping[str, Any], paper_key: str | None) -> Note | None:
        if not paper_key:
            return None
        data = self._data(record)
        reference = self._reference(record, data)
        text = self._optional_string(data.get("annotationText"))
        comment = self._optional_string(data.get("annotationComment"))
        content = "\n\n".join(value for value in (text, comment) if value)
        return Note(
            id=self._resource_id(reference.library_id, reference.item_key),
            paper_id=self._resource_id(reference.library_id, paper_key),
            content=content,
            kind="annotation",
            page_label=self._optional_string(data.get("annotationPageLabel")),
            color=self._optional_string(data.get("annotationColor")),
            external_ref=reference,
        )

    def _map_attachment(self, record: Mapping[str, Any]) -> Attachment | None:
        data = self._data(record)
        parent_key = self._parent_key(record)
        if not parent_key:
            return None
        reference = self._reference(record, data)
        content_type = self._optional_string(data.get("contentType"))
        link_mode = self._optional_string(data.get("linkMode"))
        filename = self._first_non_empty(data.get("filename"), data.get("title")) or "Attachment"
        return Attachment(
            id=self._resource_id(reference.library_id, reference.item_key),
            paper_id=self._resource_id(reference.library_id, parent_key),
            filename=filename,
            content_type=content_type,
            downloadable=(
                content_type == "application/pdf"
                and link_mode in {"imported_file", "imported_url"}
            ),
            link_mode=link_mode,
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
    def _parent_key(record: Mapping[str, Any]) -> str | None:
        data = record.get("data")
        parent = data.get("parentItem") if isinstance(data, dict) else None
        return parent if isinstance(parent, str) and parent else None

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
