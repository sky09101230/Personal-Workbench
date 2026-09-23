from dataclasses import asdict, replace
import json

from fastapi.testclient import TestClient

from app.main import app
from app.modules.literature.application.errors import PdfUnavailableError
from app.modules.literature.application.ingestion import LiteratureIngestionService
from app.modules.literature.application.materialization import PdfMaterializationService
from app.modules.literature.application.service import LiteratureService
from app.modules.literature.application.upload import UploadWorkflowService
from app.modules.literature.application.zotero_import import ZoteroImportService
from app.modules.literature.domain.canonical import Ingestion
from app.modules.literature.domain.models import Attachment, ChangedPaper, ExternalReference, LibraryChanges, Paper
from app.modules.literature.infrastructure.cache.audit_identity import audit_identity
from app.modules.literature.infrastructure.cache.canonical import _json
from app.modules.literature.infrastructure.cache.identity import SQLiteLiteratureIdentityRepository
from app.modules.literature.infrastructure.extraction import extract_metadata
from app.modules.literature.infrastructure.files import LocalLiteratureFiles
from app.modules.literature.infrastructure.acquire_assets import plan_acquisition
from app.modules.literature.infrastructure.reconcile_asset_state import reconcile_asset_state
from .test_literature_asset_acquisition import acquisition, Source
from .test_canonical_api import NoZotero, pdf_bytes


def test_source_failure_stale_state_and_successful_retry(acquisition, override_service):
    repository, files, source, provider, materializer = acquisition
    literature = LiteratureService(provider, repository, files)
    override_service('literature_service', literature)
    override_service('materialization_service', materializer)
    client = TestClient(app)
    base = f'/api/literature/papers/{source.paper_id}'
    assert client.get(base).json()['paper']['pdf_state'] == 'source_only'
    repository.record_asset_failure(source, 'source_unavailable')
    assert client.get(base).json()['paper']['pdf_state'] == 'needs_recovery'
    assert client.get(base + '/assets/integrity').json()['items'][0]['state'] == 'source_unavailable'
    newer = replace(source, content_version='changed')
    with repository._connect() as c:
        c.execute('UPDATE literature_assets SET payload_json=? WHERE id=?', (_json(asdict(newer)), source.id))
    assert repository.asset_acquisition_state(newer) is None
    assert client.get(base).json()['paper']['pdf_state'] == 'source_only'
    response = client.post(base + '/assets/' + source.id + '/acquire')
    assert response.status_code == 200 and response.json()['status'] == 'acquired'
    assert repository.asset_acquisition_state(newer)['status'] == 'acquired'
    assert client.get(base).json()['paper']['pdf_state'] == 'owned_primary'
    check = next(item for item in client.get(base + '/assets/integrity').json()['items'] if item['asset_id'] == source.id)
    assert check['state'] == 'owned_copy' and check['owned_asset_id'] == response.json()['asset_id']
    assert check['acquisition_error'] is None
    assert client.post(base + '/assets/not-owned-by-paper/acquire').status_code == 404


def test_selected_import_attempts_all_its_pdfs_and_preserves_metadata_success(tmp_path, override_service):
    repository = SQLiteLiteratureIdentityRepository(f'sqlite:///{tmp_path / "import.db"}')
    files = LocalLiteratureFiles(str(tmp_path / 'vault'))
    p = Paper('zotero:1:SELECT', 'Selected import readiness', doi='10.1234/ready')
    class Mixed(Source):
        fail_supplement = True
        def get_import_item(self, item_key):
            assert item_key == p.id
            return LibraryChanges(papers=(ChangedPaper(p),), attachments=(
                Attachment('zotero:1:GOOD', p.id, 'primary.pdf', 'application/pdf', True, external_ref=ExternalReference('zotero', '1', 'GOOD')),
                Attachment('zotero:1:BAD', p.id, 'supplement.pdf', 'application/pdf', True, external_ref=ExternalReference('zotero', '1', 'BAD'), role='supplementary'),
            ))
        def describe_attachment(self, source):
            if source.external_ref.item_key == 'BAD' and self.fail_supplement:
                raise PdfUnavailableError('Fixture source missing')
            return super().describe_attachment(source)
    provider = Mixed()
    materializer = PdfMaterializationService(repository, files, provider)
    override_service('zotero_import_service', ZoteroImportService(repository, provider, materializer.acquire_asset))
    override_service('literature_service', LiteratureService(provider, repository, files))
    override_service('materialization_service', materializer)
    client = TestClient(app)
    result = client.post('/api/literature/imports/zotero/selective', json={'item_keys': [p.id]}).json()['results'][0]
    assert result['status'] == 'imported'
    assert sorted(asset['status'] for asset in result['asset_results']) == ['acquired', 'failed']
    assert {asset['filename'] for asset in result['asset_results']} == {'primary.pdf', 'supplement.pdf'}
    pid = result['paper_id']
    assert repository.get_paper(pid).paper.title == p.title
    assert repository.get_paper(pid).paper.pdf_state == 'owned_primary'
    replay = client.post('/api/literature/imports/zotero/selective', json={'item_keys': [p.id]}).json()['results'][0]
    assert replay['status'] == 'already_exists'
    assert sorted(asset['status'] for asset in replay['asset_results']) == ['already_owned', 'failed']
    assert provider.downloads == 1
    provider.fail_supplement = False
    missing = next(asset['source_asset_id'] for asset in result['asset_results'] if asset['status'] == 'failed')
    recovered = client.post(f'/api/literature/papers/{pid}/assets/{missing}/acquire').json()
    assert recovered['status'] == 'acquired'
    assert repository.get_paper(pid).paper.doi == p.doi
    assert any(asset.storage_kind == 'local' and asset.role == 'supplementary' for asset in repository.list_attachments(pid))


def test_backend_identity_flows_through_manual_staged_and_source_ingestion(tmp_path):
    class AlternateStore(LocalLiteratureFiles):
        storage_kind = 'alternate-test-backend'
    repository = SQLiteLiteratureIdentityRepository(f'sqlite:///{tmp_path / "backend.db"}')
    files = AlternateStore(str(tmp_path / 'alternate'))
    manual = LiteratureIngestionService(repository, files, lambda _: None)
    first, asset = manual.upload_pdf(pdf_bytes(), 'manual.pdf')
    assert asset.storage_kind == files.storage_kind
    upload = UploadWorkflowService(repository, files, extract_metadata)
    batch = upload.create_batch()
    item = upload.stage_file(batch.id, 'staged.pdf', pdf_bytes(200))
    upload.update_item_metadata(batch.id, item.id, {'title': 'Staged backend example'})
    confirmed = upload.confirm_batch(batch.id)[0]
    assert repository.list_attachments(confirmed['paper_id'])[0].storage_kind == files.storage_kind
    p = Paper('source', 'Provider backend example', doi='10.1234/backend')
    pid = repository.ingest(Ingestion(p, 'manual', 'source')).paper_id
    source = repository.add_asset(Attachment('external-file', p.id, 'source.pdf', 'application/pdf', True))
    acquired = PdfMaterializationService(repository, files, Source()).acquire_asset(source)
    assert acquired.status == 'acquired'
    assert repository.owned_asset(source).storage_kind == files.storage_kind
    assert b''.join(LiteratureService(NoZotero(), repository, files).open_pdf(pid).chunks) == pdf_bytes()


def test_identity_audit_separates_reviewed_quarantined_and_open_history(tmp_path):
    path = tmp_path / 'audit.db'
    repository = SQLiteLiteratureIdentityRepository(f'sqlite:///{path}')
    pid = repository.ingest(Ingestion(Paper('', 'Audited identity', doi='10.1234/audit'), 'manual', 'one')).paper_id
    with repository._connect() as c:
        repository._conflict(c, pid, 'Contradicting source claim', {'paper_id': pid})
    conflict = repository.list_identity_conflicts()['items'][0]
    repository.decide_identity_conflict(conflict['id'], snapshot=conflict['snapshot'], decision='keep_current', reason='The current identifier is supported; the incoming claim is rejected.')
    report = audit_identity(path)
    assert report['unresolved_records'] == [] and len(report['reviewed_records']) == 1
    assert report['status'] == 'no_detected_identity_issues'
    with repository._connect() as c:
        repository._conflict(c, 'missing-parent', 'Source asset parent unresolved', {'paper_id': 'missing-parent'})
    orphan = next(item for item in repository.list_identity_conflicts()['items'] if not item['paper_ids'])
    repository.decide_identity_conflict(orphan['id'], snapshot=orphan['snapshot'], decision='quarantine', reason='Retain unassociated source data for a future recovery attempt.')
    before = path.read_bytes()
    report = audit_identity(path)
    assert report['status'] == 'quarantined_sources' and len(report['quarantined_records']) == 1
    assert len(report['conflict_history']) == 2 and path.read_bytes() == before


def test_saved_report_reconciliation_is_readonly_then_idempotent(acquisition):
    from pathlib import Path
    import pytest
    repository, files, source, _, _ = acquisition
    database = Path(repository._database_path)
    plan = plan_acquisition(database, files.root)
    reports = [[{'event': 'started', 'plan_id': plan['plan_id']}, {'event': 'asset', 'source_asset_id': source.id, 'status': 'failed', 'error': 'source_unavailable'}, {'event': 'completed', 'plan_id': plan['plan_id']}]]
    before = database.read_bytes()
    assert reconcile_asset_state(database, plan, reports)['failed_observations'] == 1
    assert database.read_bytes() == before
    assert reconcile_asset_state(database, plan, reports, apply=True)['recorded'] == 1
    assert reconcile_asset_state(database, plan, reports, apply=True)['recorded'] == 0
    assert repository.get_paper(source.paper_id).paper.pdf_state == 'needs_recovery'
    with pytest.raises(ValueError):
        reconcile_asset_state(database, {**plan, 'plan_id': 'invalid'}, reports, apply=True)
