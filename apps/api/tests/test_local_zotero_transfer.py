from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from hashlib import md5, sha256
import json

from fastapi.testclient import TestClient
import pytest

from app.main import app
from app.modules.literature.application.local_transfer import LocalTransferService, LocalTransferError
from app.modules.literature.domain.canonical import Ingestion
from app.modules.literature.domain.models import Attachment, ExternalReference, Paper
from app.modules.literature.infrastructure.cache.identity import SQLiteLiteratureIdentityRepository
from app.modules.literature.infrastructure.files import LocalLiteratureFiles
from .test_canonical_api import pdf_bytes


@pytest.fixture
def transfer(tmp_path, override_service):
    repository = SQLiteLiteratureIdentityRepository(f'sqlite:///{tmp_path / "library.db"}')
    files = LocalLiteratureFiles(str(tmp_path / 'vault'))
    paper = Paper('opaque-parent', 'Local recovery', external_ref=ExternalReference('zotero', '123', 'PARENT01'))
    pid = repository.ingest(Ingestion(paper, 'zotero_import', paper.id)).paper_id
    source = repository.add_asset(Attachment('opaque-file', paper.id, 'main.pdf', 'application/pdf', True, external_ref=ExternalReference('zotero', '123', 'FILE0001')))
    now = [100.0]
    service = LocalTransferService(repository, files, clock=lambda: now[0])
    override_service('local_transfer_service', service)
    return service, source, now


def envelope(data):
    o = {'library_id': '123', 'item_key': 'FILE0001', 'parent_key': 'PARENT01', 'version': '2', 'sha256': sha256(data).hexdigest(), 'md5': md5(data).hexdigest(), 'size_bytes': len(data)}
    return {'schema_version': 1, 'before': o, 'after': dict(o)}


def test_api_acquires_preserves_and_replays(transfer):
    svc, source, _ = transfer
    svc.repository.set_state(source.paper_id, reading_status='reading', tags=['keep'])
    svc.repository.record_asset_failure(source, 'source_unavailable')
    client = TestClient(app)
    base = f'/api/literature/papers/{source.paper_id}/assets/{source.id}'
    intent = client.post(base + '/local-intent').json()
    assert intent['source']['parent_key'] == 'PARENT01'
    data = pdf_bytes()
    headers = {'Content-Type': 'application/pdf', 'X-Transfer-Intent': intent['intent'], 'X-Zotero-Observation': json.dumps(envelope(data))}
    first = client.post(base + '/local-transfer', content=data, headers=headers)
    assert first.status_code == 200, first.text
    assert first.json()['status'] == 'acquired'
    assert client.post(base + '/local-transfer', content=data, headers=headers).json()['status'] == 'already_owned'
    paper = svc.repository.get_paper(source.paper_id).paper
    assert paper.reading_status == 'reading' and paper.tags == ('keep',)
    assert svc.repository.asset_acquisition_state(source)['status'] == 'acquired'
    owned = svc.repository.owned_asset(source)
    assert b''.join(svc.files.open(owned).chunks) == data
    evidence = svc.repository.provenance(source.paper_id)['origins'][-1]['evidence']
    assert evidence['observed_snapshot']['source_channel'] == 'zotero_local_agent_client_reported'
    assert not list(svc.files.staging.glob('*'))


@pytest.mark.parametrize('field,value,error', [('parent_key','WRONG001','source_binding_mismatch'), ('library_id','999','source_binding_mismatch'), ('item_key','WRONG001','source_binding_mismatch'), ('sha256','0'*64,'source_checksum_mismatch')])
def test_reject_observation_binding(transfer, field, value, error):
    svc, source, _ = transfer
    data = pdf_bytes()
    obs = envelope(data)
    obs['before'][field] = obs['after'][field] = value
    token = svc.create(source.paper_id, source.id)['intent']
    with pytest.raises(LocalTransferError, match=error):
        svc.receive(source.paper_id, source.id, token, obs, data)
    assert svc.repository.owned_asset(source) is None


def test_expiry_stale_and_concurrent(transfer):
    svc, source, now = transfer
    token = svc.create(source.paper_id, source.id)['intent']
    now[0] += 601
    with pytest.raises(LocalTransferError, match='intent_expired'):
        svc.validate(source.paper_id, source.id, token)
    token = svc.create(source.paper_id, source.id)['intent']
    data = pdf_bytes()
    def send(_):
        return svc.receive(source.paper_id, source.id, token, envelope(data), data).status
    with ThreadPoolExecutor(2) as pool:
        assert sorted(pool.map(send, range(2))) == ['acquired', 'already_owned']
    with pytest.raises(LocalTransferError):
        svc.validate(source.paper_id, 'different-asset', token)
    with svc.repository._connect() as db:
        db.execute('UPDATE literature_assets SET active=0 WHERE id=?', (source.id,))
    with pytest.raises(LocalTransferError):
        svc.validate(source.paper_id, source.id, token)


def test_invalid_pdf_changed_source_and_header(transfer):
    svc, source, _ = transfer
    token = svc.create(source.paper_id, source.id)['intent']
    with pytest.raises(ValueError):
        svc.receive(source.paper_id, source.id, token, envelope(b'invalid'), b'invalid')
    data = pdf_bytes()
    obs = envelope(data)
    obs['after']['version'] = '3'
    with pytest.raises(LocalTransferError, match='source_changed'):
        svc.receive(source.paper_id, source.id, token, obs, data)
    client = TestClient(app)
    response = client.post(f'/api/literature/papers/{source.paper_id}/assets/{source.id}/local-transfer', content=data, headers={'X-Transfer-Intent': token, 'X-Zotero-Observation': '{}'})
    assert response.status_code == 422
    assert svc.repository.owned_asset(source) is None
