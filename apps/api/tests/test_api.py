from fastapi.testclient import TestClient

from app.main import app
from app.modules.literature.application.errors import ProviderNotConfiguredError
from app.modules.literature.application.service import LiteratureService
from app.modules.literature.domain.models import Collection, ExternalReference, LibraryChanges, Paper, PaperPage
from app.modules.literature.infrastructure.cache.sqlite import SQLiteLiteratureRepository


client = TestClient(app)


def test_health() -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "workbench-api"}


def test_literature_status_keeps_provider_behind_workbench_api() -> None:
    response = client.get("/api/literature/status")
    assert response.status_code == 200
    assert response.json()["module"] == "literature"
    assert response.json()["provider"] == "zotero"


def test_collections_require_zotero_configuration() -> None:
    original_service = app.state.literature_service
    app.state.literature_service = LiteratureService(_UnconfiguredProvider())
    try:
        response = client.get("/api/literature/collections")
    finally:
        app.state.literature_service = original_service

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "provider_not_configured"


def test_papers_endpoint_exposes_workbench_models() -> None:
    original_service = app.state.literature_service
    provider = _StubProvider()
    app.state.literature_service = LiteratureService(provider)
    try:
        response = client.get("/api/literature/papers?collection_id=zotero:123:COLL&limit=25&offset=5")
    finally:
        app.state.literature_service = original_service

    assert response.status_code == 200
    assert response.json()["items"][0]["title"] == "Optical Computing"
    assert response.json()["items"][0]["external_ref"]["item_key"] == "PAPER"
    assert provider.list_papers_args == ("zotero:123:COLL", 25, 5)


def test_sync_endpoint_runs_full_then_incremental_sync(tmp_path) -> None:
    original_service = app.state.literature_service
    provider = _StubProvider()
    app.state.literature_service = LiteratureService(
        provider,
        SQLiteLiteratureRepository(f"sqlite:///{(tmp_path / 'sync.db').as_posix()}"),
    )
    try:
        full_response = client.post("/api/literature/sync")
        incremental_response = client.post("/api/literature/sync")
    finally:
        app.state.literature_service = original_service

    assert full_response.status_code == 200
    assert full_response.json()["sync_mode"] == "full"
    assert full_response.json()["papers"] == 1
    assert incremental_response.status_code == 200
    assert incremental_response.json()["sync_mode"] == "incremental"
    assert incremental_response.json()["library_version"] == "43"


class _StubProvider:
    name = "zotero"
    configured = True
    library_id = "123"

    def list_collections(self) -> tuple[Collection, ...]:
        return ()

    def list_papers(
        self,
        *,
        collection_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> PaperPage:
        self.list_papers_args = (collection_id, limit, offset)
        reference = ExternalReference(provider="zotero", library_id="123", item_key="PAPER")
        return PaperPage(
            items=(Paper(id="zotero:123:PAPER", title="Optical Computing", external_ref=reference),),
            total=1,
            library_version="42",
        )

    def list_changes(self, *, since: str) -> LibraryChanges:
        assert since == "42"
        return LibraryChanges(library_version="43")


class _UnconfiguredProvider:
    name = "zotero"
    configured = False

    def list_collections(self) -> tuple[Collection, ...]:
        raise ProviderNotConfiguredError("Zotero credentials are not configured")

    def list_papers(
        self,
        *,
        collection_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> PaperPage:
        raise ProviderNotConfiguredError("Zotero credentials are not configured")
