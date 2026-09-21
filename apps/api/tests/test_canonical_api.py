import copy
import io
import json
from pathlib import Path
import sqlite3

from fastapi.testclient import TestClient
from pypdf import PdfWriter
import pytest

from app.main import app
from app.modules.literature.application.ai.service import LiteratureAIService
from app.modules.literature.application.ingestion import LiteratureIngestionService
from app.modules.literature.application.service import LiteratureService
from app.modules.literature.domain.canonical import Ingestion
from app.modules.literature.domain.models import Attachment, ChangedPaper, ExternalReference, LibraryChanges, Paper
from app.modules.literature.domain.ai_models import LiteratureAIConversation, LiteratureAIMessage, LiteratureUserNote
from app.modules.literature.infrastructure.cache.canonical import SQLiteCanonicalRepository
from app.modules.literature.infrastructure.cache.sqlite import SQLiteLiteratureRepository
from app.modules.literature.infrastructure.files import LocalLiteratureFiles
from app.modules.news.application.service import NewsService
from app.modules.news.infrastructure.cache.sqlite import SQLiteNewsRepository
from .test_literature_ai_service import _Context, _Provider


class NoZotero:
    name = "zotero"
    library_id = "1"
    configured = False


def pdf_bytes(width=100):
    writer = PdfWriter()
    writer.add_blank_page(width=width, height=100)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


@pytest.fixture
def setup(tmp_path, override_service):
    url = f"sqlite:///{tmp_path / 'api.db'}"
    repository = SQLiteCanonicalRepository(url)
    files = LocalLiteratureFiles(str(tmp_path / "assets"))
    literature = LiteratureService(NoZotero(), repository, files)
    news = NewsService(providers=(), repository=SQLiteNewsRepository(url), topics=())
    ingestion = LiteratureIngestionService(repository, files, news.export_recommendation)
    override_service("literature_service", literature)
    override_service("news_service", news)
    override_service("literature_ingestion_service", ingestion)
    override_service("literature_ai_service", LiteratureAIService(literature, _Provider(), _Context(), repository))
    return TestClient(app), repository, literature, ingestion, news


def radar(client):
    payload = json.loads((Path(__file__).parent / "fixtures/literature_radar_v2.json").read_text())
    response = client.post("/api/news/papers/research/ingest", json=payload)
    assert response.status_code == 200
    return client.get("/api/news/papers/research/radar/latest").json()["run"], payload


def test_radar_save_new_existing_replay_history_and_review(setup):
    client, repository, _, _, _ = setup
    run, payload = radar(client)
    assert repository.list_papers().total == 0
    first = run["recommendations"][0]
    source = Paper("zotero:1:existing", first["title"], tuple(first["authors"]), doi=first["doi"], external_ref=ExternalReference("zotero", "1", "existing"))
    canonical = repository.ingest(Ingestion(source, "zotero_import", source.id)).paper_id
    rid = first["recommendation_id"]
    for _ in range(2):
        response = client.post(f"/api/literature/imports/radar/{rid}")
        assert response.status_code == 200, response.text
        assert response.json()["paper_id"] == canonical
    assert repository.list_papers().total == 1
    assert repository.provenance(canonical)["references"][0]["provider"] == "zotero"
    assert repository.provenance(canonical)["origins"][-1]["kind"] in {"radar", "zotero_import"}
    assert client.post("/api/literature/imports/radar-saved", json={"recommendation_ids": [rid]}).json()["saved"][rid] == canonical
    assert client.get("/api/news/papers/research/radar/latest").json()["run"]["recommendations"][0]["review_status"] == "new"
    second = run["recommendations"][1]["recommendation_id"]
    assert client.post(f"/api/literature/imports/radar/{second}").json()["created"] is True
    assert repository.list_papers().total == 2
    replay = copy.deepcopy(payload)
    replay["run_key"] += "-second"
    replay["ingest_identity"] = "sha256:" + "b" * 64
    replay["generated_at"] = "2026-08-30T07:30:00+08:00"
    assert client.post("/api/news/papers/research/ingest", json=replay).status_code == 200
    newer = client.get("/api/news/papers/research/radar/latest").json()["run"]["recommendations"][0]["recommendation_id"]
    assert client.post(f"/api/literature/imports/radar/{newer}").json()["paper_id"] == canonical
    origins = [o for o in repository.provenance(canonical)["origins"] if o["kind"] == "radar"]
    assert len(origins) == 2
    assert all(o["evidence"]["selection_rank"] == 1 for o in origins)


def test_pdf_upload_reader_ranges_and_independent_assets(setup):
    client, repository, _, _, _ = setup
    data = pdf_bytes()
    first = client.post("/api/literature/imports/pdf?filename=test.pdf", content=data)
    assert first.status_code == 201, first.text
    paper_id = first.json()["paper_id"]
    duplicate = client.post("/api/literature/imports/pdf?filename=test.pdf", content=data)
    assert duplicate.json()["paper_id"] == paper_id
    assert duplicate.json()["asset"]["id"] == first.json()["asset"]["id"]
    assert repository.list_papers().total == 1
    assert client.get(f"/api/literature/papers/{paper_id}/pdf").content == data
    response = client.get(f"/api/literature/papers/{paper_id}/pdf", headers={"Range": "bytes=0-9"})
    assert response.status_code == 206 and response.content == data[:10]
    assert response.headers["content-range"] == f"bytes 0-9/{len(data)}"
    assert client.get(f"/api/literature/papers/{paper_id}/pdf", headers={"Range": "bytes=-10"}).content == data[-10:]
    assert client.get(f"/api/literature/papers/{paper_id}/pdf", headers={"Range": "bytes=99999-"}).status_code == 416
    assert "attachment" in client.get(f"/api/literature/papers/{paper_id}/pdf/download").headers["content-disposition"]
    supplementary = client.post(f"/api/literature/imports/pdf?filename=supp.pdf&paper_id={paper_id}&role=supplementary", content=pdf_bytes(200))
    assert supplementary.status_code == 201
    assert len(repository.list_attachments(paper_id)) == 2
    assert client.get(f"/api/literature/papers/{paper_id}/pdf").content == data
    assert client.get(f"/api/literature/papers/{paper_id}/pdf?asset_id={supplementary.json()['asset']['id']}").content == pdf_bytes(200)
    assert client.post("/api/literature/imports/pdf", content=b"%PDF-invalid").status_code == 422
    assert repository.list_papers().total == 1
    assert client.post("/api/literature/imports/pdf?paper_id=unknown", content=data).status_code == 404


def test_concurrent_pdf_upload_and_primary_change(setup, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from app.modules.literature.infrastructure.ai.paper_context import PaperContextBuilder
    from app.modules.literature.infrastructure.ai import paper_context
    from .test_literature_ai_context import _Pdf
    _, repository, literature, ingestion, _ = setup
    repository.ensure_schema()
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: ingestion.upload_pdf(pdf_bytes(), "same.pdf"), range(4)))
    assert len({r[0].paper_id for r in results}) == 1
    assert len({r[1].id for r in results}) == 1
    canonical = results[0][0].paper_id
    calls = []
    def parse(stream):
        calls.append(stream.read())
        return _Pdf([f"file version {len(calls)}"])
    monkeypatch.setattr(paper_context, "PdfReader", parse)
    builder = PaperContextBuilder(literature, repository)
    assert builder.build_analysis_context(canonical, deep=False).payload["pages"][0]["text"] == "file version 1"
    # Validation uses its own real PdfReader; only text extraction is stubbed.
    ingestion.upload_pdf(pdf_bytes(250), "new.pdf", paper_id=canonical)
    assert builder.build_analysis_context(canonical, deep=False).payload["pages"][0]["text"] == "file version 2"
    assert len(calls) == 2


def test_native_state_collections_tags_and_removed_paper(setup):
    client, repository, _, _, _ = setup
    source = Paper("zotero:1:A", "Original title", tags=("remote",), external_ref=ExternalReference("zotero", "1", "A"))
    canonical = repository.ingest(Ingestion(source, "zotero_import", source.id)).paper_id
    collection = client.post("/api/literature/collections", json={"name": "My collection"}).json()
    assert client.patch(f"/api/literature/papers/{canonical}/collections/{collection['id']}", json={"present": True}).status_code == 200
    assert client.patch(f"/api/literature/papers/{canonical}/state", json={"reading_status": "reading", "tags": ["native"]}).status_code == 200
    repository.apply_changes(provider="zotero", library_id="1", changes=LibraryChanges(papers=(ChangedPaper(source),), library_version="2"))
    saved = repository.get_paper(canonical)
    assert saved.paper.tags == ("native",) and saved.paper.reading_status == "reading"
    assert saved.collections[0].id == collection["id"]
    assert client.get("/api/literature/papers?reading_status=read").json()["total"] == 0
    assert client.get("/api/literature/papers?reading_status=reading").json()["total"] == 1
    assert client.delete(f"/api/literature/papers/{canonical}").status_code == 200
    repository.apply_changes(provider="zotero", library_id="1", changes=LibraryChanges(papers=(ChangedPaper(source),), library_version="3"))
    assert client.get(f"/api/literature/papers/{canonical}").status_code == 404


def test_legacy_ai_alias_conversations_selection_and_notes(tmp_path, override_service):
    path = tmp_path / "legacy.db"
    old = SQLiteLiteratureRepository(f"sqlite:///{path}")
    p = Paper("zotero:1:OLD", "Historical paper", abstract="Historical abstract")
    old.replace_library(provider="zotero", library_id="1", collections=(), papers=(p,), collection_papers={}, notes=(), attachments=(), library_version="1")
    old.create_conversation(LiteratureAIConversation("old-conversation", p.id, "before", "before"))
    old.save_message(LiteratureAIMessage("old-message", "old-conversation", "user", {"question": "Original question"}, None, None, "before"))
    old.save_user_note(LiteratureUserNote("old-note", p.id, "Original note", "manual", "before", "before"))
    new = SQLiteCanonicalRepository(f"sqlite:///{path}")
    new.run_migration()
    literature = LiteratureService(NoZotero(), new)
    ai = LiteratureAIService(literature, _Provider(), _Context(), new)
    override_service("literature_service", literature)
    override_service("literature_ai_service", ai)
    canonical = new.get_paper(p.id).paper.id
    client = TestClient(app)
    for identifier in (p.id, canonical):
        assert client.get(f"/api/literature/papers/{identifier}/user-notes").json()["items"][0]["content"] == "Original note"
        assert ai.list_messages(identifier, "old-conversation")[0].content["question"] == "Original question"
        assert ai.create_conversation(identifier).paper_id == canonical
    overview = ai.generate_analysis(p.id, analysis_type="overview")
    assert overview.paper_id == canonical
    assert ai.add_analysis_to_notes(p.id, overview.id).paper_id == canonical
    ai.ask_paper(p.id, "old-conversation", question="Continue")
    selection = ai.run_selection(p.id, action="explain", page_number=1, selected_text="text", context_before="", context_after="", question=None)
    assert selection.paper_id == canonical
    assert len(ai.list_messages(canonical, "old-conversation")) == 3
    unrelated = new.ingest(Ingestion(Paper("", "Unrelated document"), "manual", "unrelated")).paper_id
    assert client.get(f"/api/literature/papers/{unrelated}/ai/conversations/old-conversation/messages").status_code == 404
