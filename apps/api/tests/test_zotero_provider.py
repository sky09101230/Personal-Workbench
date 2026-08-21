from collections.abc import Callable

import httpx
import pytest

from app.core.config import Settings
from app.modules.literature.application.errors import (
    ProviderAuthenticationError,
    ProviderNotConfiguredError,
)
from app.modules.literature.infrastructure.providers.zotero.provider import ZoteroWebProvider


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
    assert changes.deleted_paper_ids == ("zotero:123:OLD_PAPER",)
    assert changes.library_version == "501"
    assert requests[0].url.params["since"] == "456"
    assert requests[1].url.params["includeTrashed"] == "1"
    assert requests[2].url.path.endswith("/deleted")


def test_provider_rejects_missing_configuration_before_request() -> None:
    settings = Settings("sqlite:///./data/workbench.db", ["http://localhost:5173"], "", "")
    with pytest.raises(ProviderNotConfiguredError):
        ZoteroWebProvider(settings).list_collections()


def test_provider_maps_authentication_error() -> None:
    provider = _provider(lambda request: httpx.Response(403))
    with pytest.raises(ProviderAuthenticationError):
        provider.list_collections()


def _provider(handler: Callable[[httpx.Request], httpx.Response]) -> ZoteroWebProvider:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    settings = Settings("sqlite:///./data/workbench.db", ["http://localhost:5173"], "123", "test-key")
    return ZoteroWebProvider(settings, client=client)


def _collection(key: str, name: str, parent: str | None = None) -> dict[str, object]:
    data: dict[str, object] = {"name": name}
    if parent:
        data["parentCollection"] = parent
    return {"key": key, "library": {"id": 123}, "data": data}
