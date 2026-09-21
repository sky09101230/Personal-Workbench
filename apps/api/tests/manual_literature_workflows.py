"""Verify workflows against a fresh copy of the configured DB; never mutate the original."""
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


def digest(connection, table):
    rows = sorted(json.dumps(tuple(row), ensure_ascii=False, default=str) for row in connection.execute(f'SELECT * FROM "{table}"'))
    return hashlib.sha256('\n'.join(rows).encode()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--live-check', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[3]
    source = Path((dotenv_values(root/'.env').get('DATABASE_URL') or 'sqlite:///./data/workbench.db').removeprefix('sqlite:///')).resolve()
    temporary = Path(tempfile.mkdtemp(prefix='literature-workflows-', dir=root/'.venv/tmp'))
    database = temporary/'acceptance.db'
    os.environ['DATABASE_URL'] = f'sqlite:///{database}'
    from app.modules.literature.infrastructure.cache.canonical import backup_database
    from app.modules.literature.infrastructure.cache.workflows import SQLiteLiteratureWorkflowRepository
    backup_database(str(source),str(database))
    with closing(sqlite3.connect(database)) as c:
        tables = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        before = {table:digest(c,table) for table in tables}
    repository = SQLiteLiteratureWorkflowRepository(f'sqlite:///{database}')
    was_pending = repository.migration_required
    if was_pending:
        repository.run_migration()
    else:
        repository.ensure_schema()
        with closing(sqlite3.connect(database)) as c:
            assert all(digest(c,table)==value for table,value in before.items())
    from app.main import app
    from fastapi.testclient import TestClient
    client = TestClient(app)
    batch = client.post('/api/literature/uploads/batches').json()
    writer = PdfWriter()
    writer.add_blank_page(width=300,height=300)
    writer.add_metadata({'/Title':'Isolated workflow acceptance PDF','/Author':'Acceptance fixture'})
    buffer = io.BytesIO(); writer.write(buffer)
    staged = client.post(f"/api/literature/uploads/batches/{batch['id']}/files?filename=acceptance.pdf",content=buffer.getvalue())
    assert staged.status_code==201, staged.text
    item = staged.json()
    edited = client.patch(f"/api/literature/uploads/batches/{batch['id']}/items/{item['id']}",json={'year':2026})
    assert edited.status_code==200, edited.text
    confirmed = client.post(f"/api/literature/uploads/batches/{batch['id']}/confirm").json()['results'][0]
    assert confirmed['status']=='confirmed',confirmed
    canonical = confirmed['paper_id']
    proposal = client.post(f'/api/literature/papers/{canonical}/metadata/proposals',json={'source':'manual_acceptance','proposed_metadata':{'journal':'Acceptance-only journal'}})
    assert proposal.status_code==201,proposal.text
    accepted = client.post(f"/api/literature/metadata/proposals/{proposal.json()['id']}/accept")
    assert accepted.status_code==200 and accepted.json()['status']=='accepted'
    pdf = client.get(f'/api/literature/papers/{canonical}/pdf',headers={'Range':'bytes=0-15'})
    assert pdf.status_code==206 and pdf.content==buffer.getvalue()[:16]
    report = {'database_copy':str(database),'original_table_count':len(tables),'original_tables_preserved_on_ddl_upgrade':not was_pending,'upload_review_confirm':'passed','metadata_proposal_accept':'passed','local_pdf_range':'passed'}
    if args.live_check:
        candidate = next((p for p in repository.list_papers(limit=100).items if any(a.downloadable and a.storage_kind=='zotero' and a.source_paper_id for a in repository.list_attachments(p.id))),None)
        if candidate:
            source_asset = next(a for a in repository.list_attachments(candidate.id) if a.downloadable and a.storage_kind=='zotero' and a.source_paper_id)
            result = app.state.zotero_import_service.import_selected([source_asset.source_paper_id])[0]
            assert result.status in {'imported','already_exists'},result
            materialized = app.state.materialization_service.materialize_paper(candidate.id)
            assert materialized.status in {'materialized','already_local'},materialized
            opened = app.state.literature_service.open_pdf(candidate.id,range_header='bytes=0-15')
            try:
                assert b''.join(opened.chunks).startswith(b'%PDF')
            finally:
                if opened.close: opened.close()
            report['live_selective_import']=result.status
            report['live_pdf_materialization']=materialized.status
            report['materialized_reader_range']='passed'
        else:
            report['live_check']='no_eligible_source_pdf'
    with closing(sqlite3.connect(database)) as c:
        report['integrity']=c.execute('PRAGMA integrity_check').fetchone()[0]
        report['foreign_key_errors']=c.execute('PRAGMA foreign_key_check').fetchall()
    assert report['integrity']=='ok' and not report['foreign_key_errors']
    (temporary/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    main()
