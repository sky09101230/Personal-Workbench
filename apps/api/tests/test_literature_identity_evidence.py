from contextlib import closing
from dataclasses import replace
import json
import sqlite3

import pytest

from app.modules.literature.application.ingestion import LiteratureIngestionService
from app.modules.literature.application.zotero_import import ZoteroImportService
from app.modules.literature.domain.ai_models import LiteratureUserNote
from app.modules.literature.domain.canonical import IdentityConflictError, Ingestion
from app.modules.literature.domain.models import Paper, ExternalReference, ChangedPaper, LibraryChanges
from app.modules.literature.infrastructure.cache.audit_identity import audit_identity
from app.modules.literature.infrastructure.cache.workflows import SQLiteLiteratureWorkflowRepository
from .test_literature_workflows import workflow
from .test_canonical_api import pdf_bytes


def test_shared_strong_evidence_and_disagreement_preserve_ownership(workflow):
    repository, _, _, _, _ = workflow
    p = Paper('source-a', 'Preprint without a publication DOI', arxiv_id='2609.12345', external_ref=ExternalReference('zotero', '1', 'A'))
    first = repository.ingest(Ingestion(p, 'zotero_import', 'A'))
    assert repository.ingest(Ingestion(replace(p, id='second-source', external_ref=None), 'radar', 'one')).paper_id == first.paper_id
    other = repository.ingest(Ingestion(Paper('', 'Distinct published article', doi='10.1234/other'), 'manual', 'other'))
    before = repository.provenance(first.paper_id)
    with pytest.raises(IdentityConflictError) as error:
        repository.ingest(Ingestion(replace(p, doi='10.1234/other'), 'zotero_import', 'A'))
    assert set(error.value.candidates) == {first.paper_id, other.paper_id}
    assert repository.provenance(first.paper_id) == before
    assert repository.list_papers().total == 2


def test_weak_candidates_reach_upload_and_source_responses(workflow, override_service):
    repository, files, upload, _, client = workflow
    p = Paper('', 'Identical bibliographic evidence only', ('Alice',), year=2026, doi='10.1234/accepted')
    canonical = repository.ingest(Ingestion(p, 'manual', 'one')).paper_id
    repository.save_user_note(LiteratureUserNote('keep-note', canonical, 'Keep this note', 'manual', 'before', 'before'))
    batch = upload.create_batch()
    item = upload.stage_file(batch.id, 'review.pdf', pdf_bytes())
    upload.update_item_metadata(batch.id, item.id, {'title': p.title, 'authors': ['Alice'], 'year': 2026})
    result = client.post(f'/api/literature/uploads/batches/{batch.id}/confirm').json()['results'][0]
    assert result['status'] == 'conflict'
    assert result['candidates'] == [canonical]
    assert (files.staging / item.staging_key).is_file()
    assert upload.get_batch(batch.id).items[0].candidate_metadata['title'] == p.title
    assert repository.list_papers().total == 1
    with repository._connect() as c:
        record = c.execute('SELECT payload_json FROM literature_identity_conflicts WHERE legacy_id=?', (item.id,)).fetchone()
        assert json.loads(record[0])['candidates'] == [canonical]
    upload.update_item_metadata(batch.id, item.id, {'doi': p.doi})
    assert upload.confirm_batch(batch.id)[0]['paper_id'] == canonical
    assert repository.list_user_notes(canonical)[0].content == 'Keep this note'

    incoming = replace(p, id='source-b', doi=None, external_ref=ExternalReference('zotero', '1', 'B'))
    changes = LibraryChanges(papers=(ChangedPaper(incoming),), library_version='3')
    class Provider:
        def get_import_item(self, identifier):
            return changes
    result = ZoteroImportService(repository, Provider()).import_selected(['source-b'])[0]
    assert result.status == 'conflict' and result.candidates == (canonical,)
    override_service('zotero_import_service', ZoteroImportService(repository, Provider()))
    response = client.post('/api/literature/imports/zotero/selective', json={'item_keys': ['source-b']})
    assert response.status_code == 200, response.text
    assert response.json()['results'][0]['candidates'] == [canonical]
    # Source sync retains an independent record and explicit uncertainty.
    repository.apply_changes(provider='zotero', library_id='1', changes=changes)
    preserved = repository.get_paper('source-b').paper
    assert preserved.id != canonical and preserved.metadata_status == 'conflict'
    assert repository.provenance(preserved.id)['identifiers'] == []
    conflict = repository.provenance(preserved.id)['conflicts'][0]
    assert json.loads(conflict['payload_json'])['candidates'] == [canonical]


def test_rejected_source_identifier_cannot_fill_canonical_blank(workflow):
    repository, _, _, _, _ = workflow
    source = Paper('source-a', 'Unresolved source document', external_ref=ExternalReference('zotero', '1', 'A'))
    first = repository.ingest(Ingestion(source, 'zotero_import', source.id)).paper_id
    owner = repository.ingest(Ingestion(Paper('', 'Published document', doi='10.1234/owned'), 'manual', 'other')).paper_id
    changes = LibraryChanges(papers=(ChangedPaper(replace(source, doi='10.1234/owned')),), library_version='2')
    repository.apply_changes(provider='zotero', library_id='1', changes=changes)
    saved = repository.get_paper(first).paper
    assert saved.doi is None and saved.metadata_status == 'conflict'
    assert repository.provenance(owner)['identifiers'][0]['value'] == '10.1234/owned'
    assert repository.provenance(first)['identifiers'] == []


def test_file_replay_and_explicit_targets_do_not_merge_papers(workflow):
    repository, files, upload, _, _ = workflow
    service = LiteratureIngestionService(repository, files, lambda _: None)
    first, asset = service.upload_pdf(pdf_bytes(), 'first.pdf')
    replay, repeated = service.upload_pdf(pdf_bytes(), 'renamed.pdf')
    assert replay.paper_id == first.paper_id and repeated.id == asset.id
    assert 'file_import_replay' in replay.reason
    other = repository.ingest(Ingestion(Paper('', 'Different scholarly identity', doi='10.1234/other'), 'manual', 'other'))
    associated, shared = service.upload_pdf(pdf_bytes(), 'same-bytes.pdf', paper_id=other.paper_id)
    assert associated.paper_id == other.paper_id != first.paper_id
    assert shared.sha256 == asset.sha256 and shared.id != asset.id
    assert len(list(files.originals.iterdir())) == 1
    batch = upload.create_batch()
    item = upload.stage_file(batch.id, 'contradictory.pdf', pdf_bytes())
    upload.update_item_metadata(batch.id, item.id, {'title': 'Different scholarly identity', 'doi': '10.1234/other'})
    result = upload.confirm_batch(batch.id)[0]
    assert result['status'] == 'conflict'
    assert set(result['candidates']) == {first.paper_id, other.paper_id}
    assert repository.list_papers().total == 2
    assert repository.get_paper(first.paper_id).paper.doi is None


def test_radar_weak_identity_conflict_exposes_candidates(workflow, override_service):
    repository, files, _, _, client = workflow
    p = Paper('', 'A weakly matching Radar paper title', ('Alice',), year=2026)
    existing = repository.ingest(Ingestion(p, 'manual', 'one'))
    export = {'paper': {'title': p.title, 'authors': ['Alice'], 'published_at': '2026-09-22'}, 'appearances': [{'recommendation_id': 'candidate'}]}
    override_service('literature_ingestion_service', LiteratureIngestionService(repository, files, lambda _: export))
    response = client.post('/api/literature/imports/radar/candidate')
    assert response.status_code == 409
    assert response.json()['detail']['candidates'] == [existing.paper_id]
    assert repository.saved_origins(['candidate']) == {}


def test_audit_readonly_reports_historical_risks_and_legacy(tmp_path):
    path = tmp_path / 'audit.db'
    repository = SQLiteLiteratureWorkflowRepository(f'sqlite:///{path}')
    paper = repository.ingest(Ingestion(Paper('old-alias', 'Audit paper', doi='10.1234/audit'), 'manual', 'audit'))
    with repository._connect() as c:
        c.execute("UPDATE literature_paper_aliases SET reason='corroborated_title_year_author'")
        c.execute("DELETE FROM literature_identifiers")
        repository._conflict(c, 'old-alias', 'Identity review', {'private': 'must not leak'})
    before = path.read_bytes()
    report = audit_identity(path)
    assert audit_identity(path) == report and path.read_bytes() == before
    assert report['scientific_verification'] is False
    assert report['status'] == 'needs_review'
    assert report['weak_aliases'][0]['paper_id'] == paper.paper_id
    assert report['issues'][0]['code'] == 'identifier_not_indexed'
    assert 'must not leak' not in json.dumps(report)
    legacy = tmp_path / 'legacy.db'
    with closing(sqlite3.connect(legacy)) as c, c:
        c.execute('CREATE TABLE literature_papers (id TEXT PRIMARY KEY)')
    before = legacy.read_bytes()
    assert audit_identity(legacy)['status'] == 'canonical_schema_missing'
    assert legacy.read_bytes() == before
    missing = tmp_path / 'missing.db'
    with pytest.raises(sqlite3.OperationalError):
        audit_identity(missing)
    assert not missing.exists()
