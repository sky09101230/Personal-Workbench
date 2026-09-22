"""Isolated browser acceptance: production API + built UI, disposable data/providers.

Run from repo root after frontend build:
  .venv/Scripts/python.exe apps/web/scripts/literature-acceptance-server.py
Open http://127.0.0.1:8013/literature. Does not read or mutate the real library.
"""
import io
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps/api"))
session = Path(tempfile.mkdtemp(prefix="frontend-stage3-", dir=ROOT / ".venv/tmp"))
os.environ["DATABASE_URL"] = f"sqlite:///{session / 'acceptance.db'}"
for name in ("ZOTERO_USER_ID", "ZOTERO_API_KEY", "DEEPSEEK_API_KEY", "OPENALEX_API_KEY", "WORKBENCH_AGENT_TOKEN"):
    os.environ[name] = ""

from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient
from pypdf import PdfWriter
import uvicorn
from app.main import app
from app.modules.literature.application.ai.service import LiteratureAIService
from app.modules.literature.application.materialization import PdfMaterializationService
from app.modules.literature.application.zotero_import import ZoteroImportService
from app.modules.literature.domain.canonical import Ingestion
from app.modules.literature.domain.models import Attachment, ChangedPaper, Collection, ExternalReference, LibraryChanges, Note, Paper, PaperPage, ProviderFile
from tests.test_literature_ai_service import _Context, _Provider


def pdf(title=None):
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    if title:
        writer.add_metadata({"/Title": title, "/Author": "Acceptance Researcher"})
    stream = io.BytesIO()
    writer.write(stream)
    return stream.getvalue()


for filename, title in (("review.pdf", "Staged review sample"), ("incomplete.pdf", None), ("cancel.pdf", "Cancel this staged paper")):
    (session / filename).write_bytes(pdf(title))


class Connector:
    name = "zotero"
    library_id = "fixture"
    configured = True
    papers = (
        Paper("opaque/selective:one", "Selective connector sample", ("Ada Researcher",), year=2026, external_ref=ExternalReference("zotero", "fixture", "ONE")),
        Paper("opaque/selective:two", "Second connector sample", ("Ben Researcher",), year=2025, external_ref=ExternalReference("zotero", "fixture", "TWO")),
    )

    def list_collections(self):
        return (Collection("source/collection", "Connector sample collection"),)

    def list_papers(self, *, collection_id=None, limit=50, offset=0):
        return PaperPage(self.papers[offset:offset + limit], len(self.papers))

    def get_import_item(self, key):
        paper = next(p for p in self.papers if p.id == key)
        return LibraryChanges(collections=self.list_collections(), papers=(ChangedPaper(paper, ("source/collection",)),), notes=(Note("source-note:" + key, paper.id, "Imported source note"),), attachments=(Attachment("asset:" + key, paper.id, "connector.pdf", "application/pdf", True, external_ref=paper.external_ref),))

    def open_attachment(self, asset, **kwargs):
        return ProviderFile(asset.filename, "application/pdf", (pdf("Connector PDF"),))


literature = app.state.literature_service
repository = app.state.upload_workflow_service.repository
files = app.state.upload_workflow_service.files
connector = Connector()
object.__setattr__(literature, "provider", connector)
app.state.zotero_import_service = ZoteroImportService(repository, connector)
app.state.materialization_service = PdfMaterializationService(repository, files, connector)
app.state.literature_ai_service = LiteratureAIService(literature, _Provider(), _Context(), repository)
paper_id = repository.ingest(Ingestion(Paper("", "Metadata review sample", ("Test Author",)), "manual_pdf", "fixture-review")).paper_id
review = app.state.metadata_review_service
client = TestClient(app)
for changes in ({"journal": "Accepted Journal"}, {"abstract": "Reject this candidate"}, {"year": 2026}, {"title": "Stale candidate title"}):
    response = client.post(f"/api/literature/papers/{paper_id}/metadata/proposals", json={"source": "acceptance", "proposed_metadata": changes})
    assert response.status_code == 201, response.text
radar = json.loads((ROOT / "apps/api/tests/fixtures/literature_radar_v2.json").read_text(encoding="utf-8"))
assert client.post("/api/news/papers/research/ingest", json=radar).status_code == 200
dist = ROOT / "apps/web/dist"
app.mount("/assets", StaticFiles(directory=dist / "assets"), name="acceptance-assets")


@app.get("/{path:path}", include_in_schema=False)
def frontend(path: str):
    return FileResponse(dist / "index.html")


print(f"Acceptance files: {session}", flush=True)
print("Fixture providers only; no external API calls.", flush=True)
uvicorn.run(app, host="127.0.0.1", port=8013, log_level="warning")
