from collections.abc import Callable

import httpx
import pytest

from app.core.config import Settings
from app.modules.literature.application.errors import (
    PdfUnavailableError,
    ProviderAuthenticationError,
    ProviderNotConfiguredError,
)
from app.modules.literature.infrastructure.providers.zotero.provider import ZoteroWebProvider
from app.modules.literature.domain.models import Attachment, ExternalReference


def test_list_collections_uses_v3_headers_and_paginates() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        start = request.url.params["start"]
        payload = [_collection("FIRST", "Optics")] if start == "0" else [_collection("SECOND", "D2NN", "FIRST")]
        return httpx.Response(200, json=payload, headers={"Total-Results": "2"})

    provider = _provider(handler)
    collections = provider.list_collections()

    assert [(collection.id, collection.parent_id) for collection in collections] == [
        ("zotero:123:FIRST", None),
        ("zotero:123:SECOND", "zotero:123:FIRST"),
    ]
    assert len(requests) == 2
    assert requests[0].url.path == "/users/123/collections"
    assert requests[0].headers["Zotero-API-Version"] == "3"
    assert requests[0].headers["Zotero-API-Key"] == "test-key"
    assert "key" not in requests[0].url.params


def test_list_papers_maps_only_workbench_papers() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/users/123/collections/COLL/items/top"
        assert request.url.params == httpx.QueryParams(
            {"format": "json", "itemType": "-attachment", "limit": "25", "start": "5"}
        )
        return httpx.Response(
            200,
            json=[
                {
                    "key": "PAPER",
                    "library": {"id": 123},
                    "data": {
                        "itemType": "journalArticle",
                        "title": "Diffractive Optical Computing",
                        "creators": [
                            {"firstName": "Aylin", "lastName": "Ozcan"},
                            {"name": "Research Group"},
                        ],
                        "abstractNote": "  A paper abstract. ",
                        "date": "2018-09-20",
                        "publicationTitle": "Science",
                        "DOI": "10.1126/example",
                        "tags": [{"tag": "optics"}, {"tag": "ML"}],
                    },
                },
                {"key": "NOTE", "library": {"id": 123}, "data": {"itemType": "note"}},
            ],
            headers={"Total-Results": "1", "Last-Modified-Version": "456"},
        )

    page = _provider(handler).list_papers(collection_id="zotero:123:COLL", limit=25, offset=5)

    assert page.total == 1
    assert page.library_version == "456"
    assert len(page.items) == 1
    assert page.items[0].id == "zotero:123:PAPER"
    assert page.items[0].authors == ("Aylin Ozcan", "Research Group")
    assert page.items[0].year == 2018
    assert page.items[0].journal == "Science"
    assert page.items[0].tags == ("optics", "ML")


def test_list_changes_uses_since_and_processes_deleted_objects() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/collections"):
            return httpx.Response(
                200,
                json=[_collection("COLL", "Changed")],
                headers={"Total-Results": "1", "Last-Modified-Version": "500"},
            )
        if request.url.path.endswith("/items/top"):
            return httpx.Response(
                200,
                json=[
                    {
                        "key": "PAPER",
                        "library": {"id": 123},
                        "data": {
                            "itemType": "journalArticle",
                            "title": "Changed paper",
                            "collections": ["COLL"],
                        },
                    }
                ],
                headers={"Total-Results": "1", "Last-Modified-Version": "500"},
            )
        if request.url.path.endswith("/items"):
            return httpx.Response(
                200,
                json=[],
                headers={"Total-Results": "0", "Last-Modified-Version": "500"},
            )
        return httpx.Response(
            200,
            json={"collections": ["OLD_COLL"], "items": ["OLD_PAPER"], "tags": []},
            headers={"Last-Modified-Version": "501"},
        )

    changes = _provider(handler).list_changes(since="456")

    assert changes.collections[0].id == "zotero:123:COLL"
    assert changes.papers[0].paper.id == "zotero:123:PAPER"
    assert changes.papers[0].collection_ids == ("zotero:123:COLL",)
    assert changes.deleted_collection_ids == ("zotero:123:OLD_COLL",)
    assert changes.deleted_item_ids == ("zotero:123:OLD_PAPER",)
    assert changes.library_version == "501"
    assert requests[0].url.params["since"] == "456"
    assert requests[1].url.params["includeTrashed"] == "1"
    assert requests[2].url.path.endswith("/items")
    assert requests[3].url.path.endswith("/deleted")


def test_provider_rejects_missing_configuration_before_request() -> None:
    settings = Settings("sqlite:///./data/workbench.db", ["http://localhost:5173"], "", "")
    with pytest.raises(ProviderNotConfiguredError):
        ZoteroWebProvider(settings).list_collections()


def test_provider_maps_authentication_error() -> None:
    provider = _provider(lambda request: httpx.Response(403))
    with pytest.raises(ProviderAuthenticationError):
        provider.list_collections()


def test_list_assets_maps_notes_annotations_and_pdf_availability() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/users/123/items"
        return httpx.Response(
            200,
            json=[
                {
                    "key": "NOTE",
                    "library": {"id": 123},
                    "data": {"itemType": "note", "parentItem": "PAPER", "note": "<p>Note</p>"},
                },
                {
                    "key": "PDF",
                    "library": {"id": 123},
                    "data": {
                        "itemType": "attachment",
                        "parentItem": "PAPER",
                        "linkMode": "imported_file",
                        "contentType": "application/pdf",
                        "filename": "paper.pdf",
                    },
                },
                {
                    "key": "LINKED",
                    "library": {"id": 123},
                    "data": {
                        "itemType": "attachment",
                        "parentItem": "PAPER",
                        "linkMode": "linked_file",
                        "contentType": "application/pdf",
                        "filename": "linked.pdf",
                    },
                },
                {
                    "key": "ANN",
                    "library": {"id": 123},
                    "data": {
                        "itemType": "annotation",
                        "parentItem": "PDF",
                        "annotationText": "Important",
                        "annotationComment": "Check this",
                        "annotationPageLabel": "3",
                        "annotationColor": "#ffd400",
                    },
                },
            ],
            headers={"Total-Results": "4", "Last-Modified-Version": "502"},
        )

    assets = _provider(handler).list_assets()

    assert assets.library_version == "502"
    assert [(note.kind, note.paper_id) for note in assets.notes] == [
        ("note", "zotero:123:PAPER"),
        ("annotation", "zotero:123:PAPER"),
    ]
    assert assets.notes[1].page_label == "3"
    assert [(item.filename, item.downloadable) for item in assets.attachments] == [
        ("paper.pdf", True),
        ("linked.pdf", False),
    ]


def test_open_attachment_forwards_range_without_exposing_key_in_url() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            206,
            stream=httpx.ByteStream(b"%PDF"),
            headers={
                "Content-Type": "application/pdf",
                "Content-Length": "4",
                "Content-Range": "bytes 0-3/4",
                "Accept-Ranges": "bytes",
            },
        )

    attachment = Attachment(
        id="zotero:123:PDF",
        paper_id="zotero:123:PAPER",
        filename="paper.pdf",
        content_type="application/pdf",
        downloadable=True,
        link_mode="imported_file",
        external_ref=ExternalReference(provider="zotero", library_id="123", item_key="PDF"),
    )
    provider_file = _provider(handler).open_attachment(attachment, range_header="bytes=0-3")

    assert b"".join(provider_file.chunks) == b"%PDF"
    assert provider_file.status_code == 206
    assert requests[0].url.path == "/users/123/items/PDF/file"
    assert "key" not in requests[0].url.params
    assert requests[0].headers["Range"] == "bytes=0-3"
    provider_file.close and provider_file.close()


def test_incremental_sync_removes_trashed_parent_and_child_items() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/collections"):
            return httpx.Response(200, json=[], headers={"Total-Results": "0"})
        if request.url.path.endswith("/items/top"):
            return httpx.Response(
                200,
                json=[
                    {
                        "key": "PAPER",
                        "library": {"id": 123},
                        "data": {"itemType": "journalArticle", "title": "Old", "deleted": 1},
                    }
                ],
                headers={"Total-Results": "1"},
            )
        if request.url.path.endswith("/items"):
            return httpx.Response(
                200,
                json=[
                    {
                        "key": "NOTE",
                        "library": {"id": 123},
                        "data": {"itemType": "note", "parentItem": "PAPER", "deleted": 1},
                    }
                ],
                headers={"Total-Results": "1"},
            )
        return httpx.Response(200, json={"collections": [], "items": [], "tags": []})

    changes = _provider(handler).list_changes(since="501")

    assert changes.papers == ()
    assert changes.notes == ()
    assert changes.deleted_item_ids == ("zotero:123:PAPER", "zotero:123:NOTE")


def test_attachment_redirect_does_not_forward_zotero_key() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.host == "api.zotero.org":
            return httpx.Response(302, headers={"Location": "https://storage.example/paper.pdf"})
        return httpx.Response(403)

    attachment = Attachment(
        id="zotero:123:PDF",
        paper_id="zotero:123:PAPER",
        filename="paper.pdf",
        content_type="application/pdf",
        downloadable=True,
        external_ref=ExternalReference(provider="zotero", library_id="123", item_key="PDF"),
    )

    with pytest.raises(PdfUnavailableError):
        _provider(handler).open_attachment(attachment)

    assert requests[0].headers["Zotero-API-Key"] == "test-key"
    assert "Zotero-API-Key" not in requests[1].headers


def _provider(handler: Callable[[httpx.Request], httpx.Response]) -> ZoteroWebProvider:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    settings = Settings("sqlite:///./data/workbench.db", ["http://localhost:5173"], "123", "test-key")
    return ZoteroWebProvider(settings, client=client)


def _collection(key: str, name: str, parent: str | None = None) -> dict[str, object]:
    data: dict[str, object] = {"name": name}
    if parent:
        data["parentCollection"] = parent
    return {"key": key, "library": {"id": 123}, "data": data}
