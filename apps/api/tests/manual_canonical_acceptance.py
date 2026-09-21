"""Isolated manual/browser acceptance; run as a script from the repository root.

PYTHONPATH=apps/api python apps/api/tests/manual_canonical_acceptance.py --serve
The live database is only read through SQLite backup. All changes use a new copy.
"""

import argparse
from contextlib import closing
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import tempfile

from dotenv import dotenv_values
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject


ROOT = Path(__file__).resolve().parents[3]


def fixture_pdf():
    writer = PdfWriter()
    page = writer.add_blank_page(width=595, height=842)
    font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"), NameObject("/BaseFont"): NameObject("/Helvetica")})
    page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})})
    content = DecodedStreamObject()
    content.set_data(b"BT /F1 20 Tf 55 760 Td (Literature V2 acceptance PDF) Tj 0 -40 Td /F1 12 Tf (This local fixture verifies PDF rendering and selectable text.) Tj 0 -25 Td (Canonical paper identity is independent of file identity.) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(content)
    result = io.BytesIO()
    writer.write(result)
    return result.getvalue()


def table_digest(c, name):
    rows = sorted(json.dumps(tuple(r), ensure_ascii=False, default=str) for r in c.execute(f'SELECT * FROM "{name}"'))
    return hashlib.sha256("\n".join(rows).encode()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--live-check", action="store_true")
    args = parser.parse_args()
    source_url = dotenv_values(ROOT / ".env").get("DATABASE_URL") or "sqlite:///./data/workbench.db"
    source = Path(source_url.removeprefix("sqlite:///")).resolve()
    workspace = Path(tempfile.mkdtemp(prefix="literature-v2-acceptance-", dir=ROOT / ".venv/tmp"))
    target = workspace / "acceptance.db"
    os.environ["DATABASE_URL"] = f"sqlite:///{target}"
    from app.modules.literature.infrastructure.cache.canonical import backup_database, SQLiteCanonicalRepository
    backup_database(str(source), str(target))
    baseline_backup = workspace / "before-acceptance.db"
    backup_database(str(source), str(baseline_backup))
    with closing(sqlite3.connect(source)) as c:
        tables = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'") if not r[0].startswith("literature_ai_") and r[0] != "literature_user_notes"]
        before = {name: table_digest(c, name) for name in tables}
    repository = SQLiteCanonicalRepository(f"sqlite:///{target}")
    repository.run_migration()
    report = repository.migration_report()
    with closing(sqlite3.connect(target)) as c:
        unchanged = {name: before[name] == table_digest(c, name) for name in tables}
        assert all(unchanged.values()), unchanged
        report["unchanged_original_tables"] = len(unchanged)
        report["integrity"] = c.execute("PRAGMA integrity_check").fetchone()[0]
        aliases = dict(c.execute("SELECT alias,paper_id FROM literature_paper_aliases"))
        merged = c.execute("SELECT paper_id,COUNT(*) FROM literature_paper_aliases GROUP BY paper_id HAVING COUNT(*)>1").fetchall()
        report["merged_alias_groups"] = [{"paper_id": p, "aliases": count} for p,count in merged]
    for old, canonical in aliases.items():
        assert repository.get_paper(old).paper.id == canonical
    report["aliases_verified"] = len(aliases)
    # Reconstructing repositories proves replay safety; restoring a backup into another
    # file exercises rollback without overwriting subsequent user work.
    assert SQLiteCanonicalRepository(f"sqlite:///{target}").migration_report() == repository.migration_report()
    restored = workspace / "rollback-rehearsal.db"
    backup_database(str(baseline_backup), str(restored))
    with closing(sqlite3.connect(restored)) as c:
        assert all(table_digest(c, name) == before[name] for name in tables)
    report["rollback_rehearsal"] = "passed"
    (workspace / "fixture.pdf").write_bytes(fixture_pdf())
    from app.main import app
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles
    from fastapi.testclient import TestClient
    client = TestClient(app)
    assert client.get("/api/literature/papers").status_code == 200
    assert client.get("/api/news/papers/research/radar/latest").status_code == 200
    for table in ("literature_ai_analyses", "literature_user_notes", "literature_ai_conversations"):
        with closing(sqlite3.connect(source)) as c:
            originals = c.execute(f"SELECT id,paper_id FROM {table}").fetchall()
        for identifier, old in originals:
            suffix = {"literature_ai_analyses": "ai/analyses", "literature_user_notes": "user-notes", "literature_ai_conversations": "ai/conversations"}[table]
            data = client.get(f"/api/literature/papers/{old}/{suffix}").json()["items"]
            assert identifier in {item["id"] for item in data}
    report["real_legacy_ai_reads"] = "passed"
    if args.live_check:
        service = app.state.literature_service
        report["live"] = {}
        try:
            # Read-only remote operations; persistence affects only the acceptance copy.
            synced = service.sync()
            report["live"]["zotero_incremental_sync"] = {"mode": synced.sync_mode, "papers": synced.papers, "version": synced.library_version}
        except Exception as error:
            report["live"]["zotero_incremental_sync"] = {"error_type": type(error).__name__}
        readable = next((p for p in repository.list_papers(limit=100).items if p.pdf_available), None)
        if readable:
            try:
                streamed = service.open_pdf(readable.id, range_header="bytes=0-1023")
                try:
                    header = next(iter(streamed.chunks), b"")
                    report["live"]["zotero_pdf"] = {"status": streamed.status_code, "pdf_signature": header.startswith(b"%PDF")}
                finally:
                    if streamed.close:
                        streamed.close()
            except Exception as error:
                report["live"]["zotero_pdf"] = {"error_type": type(error).__name__}
        try:
            # A metadata-only new paper keeps the live AI check bounded and isolated.
            from app.modules.literature.domain.canonical import Ingestion
            from app.modules.literature.domain.models import Paper
            candidate = repository.ingest(Ingestion(Paper("", "Canonical identity acceptance", abstract="This test checks that a literature assistant can describe a local canonical paper independently of Zotero."), "manual", "live-ai-acceptance"))
            analysis = app.state.literature_ai_service.generate_analysis(candidate.paper_id, analysis_type="overview")
            report["live"]["ai_overview"] = {"persisted": bool(analysis.id), "canonical_id": analysis.paper_id == candidate.paper_id}
        except Exception as error:
            report["live"]["ai_overview"] = {"error_type": type(error).__name__}
    (workspace / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"workspace": str(workspace), "report": report}, indent=2), flush=True)
    if args.serve:
        dist = ROOT / "apps/web/dist"
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="acceptance-assets")
        @app.get("/{path:path}", include_in_schema=False)
        def frontend(path: str):
            return FileResponse(dist / "index.html")
        import uvicorn
        uvicorn.run(app, host="127.0.0.1", port=8765)


if __name__ == "__main__":
    main()
