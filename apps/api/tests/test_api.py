import sqlite3

from fastapi.testclient import TestClient

from app.main import app
from app.modules.literature.application.errors import ProviderNotConfiguredError
from app.modules.literature.application.service import LiteratureService
from app.modules.literature.domain.models import (
    Attachment,
    Collection,
    ExternalReference,
    LibraryChanges,
    LiteratureAssets,
    Note,
    Paper,
    PaperPage,
    ProviderFile,
)
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


def test_cached_search_detail_notes_attachments_and_pdf_endpoints(tmp_path) -> None:
    original_service = app.state.literature_service
    service = LiteratureService(
        _StubProvider(),
        SQLiteLiteratureRepository(f"sqlite:///{(tmp_path / 'v01.db').as_posix()}"),
    )
    app.state.literature_service = service
    try:
        assert client.post("/api/literature/sync").status_code == 200
        papers = client.get("/api/literature/papers?query=optical&author=missing")
        matching_papers = client.get("/api/literature/papers?query=optical")
        filtered_papers = client.get(
            "/api/literature/papers?year=2024&journal=Optics%20Letters&tag=diffraction"
        )
        filters = client.get("/api/literature/filters")
        detail = client.get("/api/literature/papers/zotero:123:PAPER")
        notes = client.get("/api/literature/papers/zotero:123:PAPER/notes")
        attachments = client.get("/api/literature/papers/zotero:123:PAPER/attachments")
        pdf = client.get(
            "/api/literature/papers/zotero:123:PAPER/pdf",
            headers={"Range": "bytes=0-3"},
        )
        download = client.get("/api/literature/papers/zotero:123:PAPER/pdf/download")
    finally:
        app.state.literature_service = original_service

    assert papers.json()["total"] == 0
    assert matching_papers.json()["items"][0]["title"] == "Optical Computing"
    assert filtered_papers.json()["total"] == 1
    assert filters.json() == {
        "years": [2024],
        "journals": ["Optics Letters"],
        "tags": ["diffraction"],
    }
    assert detail.json()["paper"]["doi"] == "10.1000/example"
    assert detail.json()["pdf_available"] is True
    assert notes.json()["items"][0]["content"] == "<p>Read only</p>"
    assert attachments.json()["items"][0]["availability"] == "available"
    assert pdf.status_code == 206
    assert pdf.headers["content-range"] == "bytes 0-3/4"
    assert pdf.content == b"%PDF"
    assert download.headers["content-disposition"].startswith("attachment;")


def test_linked_pdf_is_reported_without_attempting_a_download(tmp_path) -> None:
    database_path = tmp_path / "linked.db"
    original_service = app.state.literature_service
    service = LiteratureService(
        _StubProvider(),
        SQLiteLiteratureRepository(f"sqlite:///{database_path.as_posix()}"),
    )
    app.state.literature_service = service
    try:
        assert client.post("/api/literature/sync").status_code == 200
        with sqlite3.connect(database_path) as connection:
            connection.execute(
                "UPDATE literature_attachments SET downloadable = 0, link_mode = 'linked_file'"
            )
            connection.commit()
        attachments = client.get("/api/literature/papers/zotero:123:PAPER/attachments")
        pdf = client.get("/api/literature/papers/zotero:123:PAPER/pdf")
    finally:
        app.state.literature_service = original_service

    assert attachments.json()["items"][0]["availability"] == "linked_file"
    assert pdf.status_code == 404
    assert pdf.json()["detail"]["code"] == "pdf_unavailable"


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
            items=(
                Paper(
                    id="zotero:123:PAPER",
                    title="Optical Computing",
                    authors=("Ada Lovelace",),
                    abstract="A cached abstract.",
                    year=2024,
                    journal="Optics Letters",
                    doi="10.1000/example",
                    tags=("diffraction",),
                    external_ref=reference,
                ),
            ),
            total=1,
            library_version="42",
        )

    def list_changes(self, *, since: str) -> LibraryChanges:
        assert since == "42"
        return LibraryChanges(library_version="43")

    def list_assets(self) -> LiteratureAssets:
        reference = ExternalReference(provider="zotero", library_id="123", item_key="PDF")
        return LiteratureAssets(
            notes=(
                Note(
                    id="zotero:123:NOTE",
                    paper_id="zotero:123:PAPER",
                    content="<p>Read only</p>",
                ),
            ),
            attachments=(
                Attachment(
                    id="zotero:123:PDF",
                    paper_id="zotero:123:PAPER",
                    filename="optics.pdf",
                    content_type="application/pdf",
                    downloadable=True,
                    link_mode="imported_file",
                    external_ref=reference,
                ),
            ),
            library_version="42",
        )

    def open_attachment(
        self,
        attachment: Attachment,
        *,
        range_header: str | None = None,
    ) -> ProviderFile:
        assert attachment.id == "zotero:123:PDF"
        assert range_header in {None, "bytes=0-3"}
        return ProviderFile(
            filename=attachment.filename,
            content_type="application/pdf",
            chunks=(b"%PDF",),
            status_code=206 if range_header else 200,
            content_length="4",
            content_range="bytes 0-3/4" if range_header else None,
            accept_ranges="bytes",
        )


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
