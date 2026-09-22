from dataclasses import asdict, replace
from contextlib import closing
from hashlib import md5
import json
from pathlib import Path
import sqlite3

import httpx
import pytest

from app.core.config import Settings
from app.modules.literature.application.errors import WorkflowConflictError, ProviderAuthenticationError, PdfUnavailableError, PdfSizeLimitError
from app.modules.literature.application.materialization import PdfMaterializationService
from app.modules.literature.application.service import LiteratureService
from app.modules.literature.domain.ai_models import LiteratureUserNote
from app.modules.literature.domain.canonical import Ingestion
from app.modules.literature.domain.models import Attachment, ExternalReference, Paper, ProviderFile, LibraryChanges
from app.modules.literature.infrastructure.acquire_assets import apply_acquisition, plan_acquisition
from app.modules.literature.infrastructure.cache.canonical import _json
from app.modules.literature.infrastructure.cache.identity import SQLiteLiteratureIdentityRepository
from app.modules.literature.infrastructure.files import LocalLiteratureFiles
from app.modules.literature.infrastructure import files as file_module
from app.modules.literature.infrastructure.providers.zotero.provider import ZoteroWebProvider
from app.modules.literature.infrastructure.providers.zotero.local_files import LocalZoteroFiles
from .manual_identity_acceptance import fingerprints
from .test_canonical_api import pdf_bytes


class Source:
    def __init__(self):
        self.data = pdf_bytes()
        self.downloads = 0
        self.descriptions = 0
        self.closed = 0
        self.offline = False
        self.changed = False
        self.wrong_md5 = False

    def describe_attachment(self, source):
        assert not self.offline, 'Unexpected provider request during owned replay'
        self.descriptions += 1
        return replace(source, paper_id=source.source_paper_id or source.paper_id, content_version='changed' if self.changed and self.descriptions % 2 == 0 else 'observed-7', source_md5='0' * 32 if self.wrong_md5 else md5(self.data).hexdigest())

    def open_attachment(self, source, **kwargs):
        assert not self.offline, 'Unexpected external read of an owned PDF'
        self.downloads += 1
        return ProviderFile(source.filename, 'application/pdf', (self.data,), content_length=str(len(self.data)), close=self.close_stream)

    def close_stream(self):
        self.closed += 1


@pytest.fixture
def acquisition(tmp_path):
    repository = SQLiteLiteratureIdentityRepository(f'sqlite:///{tmp_path / "acquire.db"}')
    files = LocalLiteratureFiles(str(tmp_path / 'vault'))
    p = Paper('zotero:1:PARENT', 'Acquisition preservation example', doi='10.1234/acquire')
    pid = repository.ingest(Ingestion(p, 'zotero_import', p.id)).paper_id
    source = repository.add_asset(Attachment('zotero:1:FILE', p.id, 'main.pdf', 'application/pdf', True, external_ref=ExternalReference('zotero', '1', 'FILE')))
    provider = Source()
    return repository, files, source, provider, PdfMaterializationService(repository, files, provider)


def test_acquisition_preserves_research_rows_and_reads_owned_offline(acquisition):
    repository, files, source, provider, service = acquisition
    repository.set_state(source.paper_id, reading_status='reading', tags=['keep'])
    repository.save_user_note(LiteratureUserNote('note', source.paper_id, 'Keep this note', 'manual', 'before', 'before'))
    collection = repository.create_collection('Keep collection')
    repository.set_membership(source.paper_id, collection.id, True)
    repository.select_primary_asset(source.paper_id, source.id)
    before = fingerprints(repository._database_path)
    result = service.acquire_asset(source)
    assert result.status == 'acquired' and result.observed_version == 'observed-7'
    assert provider.downloads == provider.closed == 1 and provider.descriptions == 2
    after = fingerprints(repository._database_path)
    for table in before:
        if table not in {'literature_assets', 'literature_asset_copies', 'literature_origins'}:
            assert before[table] == after[table], table
    with repository._connect() as c:
        stored = json.loads(c.execute('SELECT payload_json FROM literature_assets WHERE id=?', (source.id,)).fetchone()[0])
        assert stored == asdict(source)
        copy = c.execute('SELECT * FROM literature_asset_copies WHERE source_asset_id=?', (source.id,)).fetchone()
        assert json.loads(copy['source_snapshot_json'])['content_version'] is None
        assert json.loads(copy['observed_snapshot_json'])['content_version'] == 'observed-7'
    provider.offline = True
    assert service.acquire_asset(source).status == 'already_owned'
    assert fingerprints(repository._database_path) == after
    reader = LiteratureService(provider, repository, files)
    assert reader.primary_attachment(source.paper_id).id == result.asset_id
    assert b''.join(reader.open_pdf(source.paper_id, range_header='bytes=0-9').chunks) == provider.data[:10]
    assert repository.get_paper(source.paper_id).paper.primary_asset_id == source.id
    repository.apply_changes(provider='zotero', library_id='1', changes=LibraryChanges(deleted_item_ids=('zotero:1:FILE',)))
    assert b''.join(reader.open_pdf(source.paper_id).chunks) == provider.data


def test_duplicate_bytes_roles_and_removed_papers(acquisition):
    repository, files, source, provider, service = acquisition
    first = service.acquire_asset(source)
    other = repository.add_asset(replace(source, id='zotero:1:OTHER', filename='renamed.pdf', external_ref=ExternalReference('zotero', '1', 'OTHER')))
    assert service.acquire_asset(other).asset_id == first.asset_id
    supplement = repository.add_asset(replace(source, id='zotero:1:SUPP', role='supplementary', filename='supplement.pdf', external_ref=ExternalReference('zotero', '1', 'SUPP')))
    repository.set_state(source.paper_id, deleted=True)
    acquired = service.acquire_asset(supplement)
    assert acquired.status == 'acquired' and acquired.asset_id != first.asset_id
    assert repository.owned_asset(supplement).role == 'supplementary'
    assert repository.get_paper(source.paper_id) is None
    assert len(list(files.originals.glob('*.pdf'))) == 1


@pytest.mark.parametrize('failure,expected', [('changed', 'source_changed_during_download'), ('wrong_md5', 'source_checksum_mismatch')])
def test_source_changes_and_checksums_prevent_association(acquisition, failure, expected):
    repository, files, source, provider, service = acquisition
    setattr(provider, failure, True)
    result = service.acquire_asset(source)
    assert result.status == 'failed' and result.error == expected
    assert provider.closed == 1 and repository.owned_asset(source) is None
    assert not files.originals.exists()


def test_failed_commit_reuses_published_content_and_corrupt_owned_is_not_replaced(acquisition, monkeypatch):
    repository, files, source, provider, service = acquisition
    original = repository.record_owned_asset
    def fail(*args):
        raise WorkflowConflictError('injected source race')
    monkeypatch.setattr(repository, 'record_owned_asset', fail)
    assert service.acquire_asset(source).error == 'source_descriptor_changed'
    assert repository.owned_asset(source) is None
    assert len(list(files.originals.glob('*.pdf'))) == 1
    monkeypatch.setattr(repository, 'record_owned_asset', original)
    assert service.acquire_asset(source).status == 'acquired'
    owned = repository.owned_asset(source)
    (files.originals / owned.storage_key).write_bytes(b'corrupted')
    provider.offline = True
    assert service.acquire_asset(source).error == 'owned_asset_corrupt'
    assert (files.originals / owned.storage_key).read_bytes() == b'corrupted'


def test_planning_is_readonly_and_batch_apply_rejects_stale_plan(acquisition):
    repository, files, source, provider, _ = acquisition
    database = Path(repository._database_path)
    before = database.read_bytes()
    plan = plan_acquisition(database, files.root)
    assert database.read_bytes() == before and not files.root.exists()
    assert len(plan['assets']) == 1
    result = apply_acquisition(plan, database, files.root, provider)
    assert result['counts'] == {'acquired': 1} and Path(result['backup']).is_file()
    provider.offline = True
    before = fingerprints(database)
    replay = apply_acquisition(plan, database, files.root, provider)
    assert replay['counts'] == {'already_owned': 1} and fingerprints(database) == before
    with repository._connect() as c:
        c.execute('UPDATE literature_assets SET payload_json=? WHERE id=?', (_json(asdict(replace(source, filename='changed.pdf'))), source.id))
    stale = apply_acquisition(plan, database, files.root, provider)
    assert stale['results'][0]['error'] == 'planned_source_changed'
    tampered = {**plan, 'vault': str(files.root / 'wrong')}
    with pytest.raises(ValueError):
        apply_acquisition(tampered, database, files.root, provider)


def test_provider_describes_exact_reference_parent_version_and_md5():
    def handle(request):
        assert request.url.path == '/users/1/items/FILE'
        assert request.headers['Zotero-API-Key'] == 'fixture-key'
        return httpx.Response(200, json={'key': 'FILE', 'version': 7, 'library': {'id': 1}, 'data': {'itemType': 'attachment', 'parentItem': 'PARENT', 'filename': 'paper.pdf', 'contentType': 'application/pdf', 'linkMode': 'imported_file', 'md5': 'a' * 32}})
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        provider = ZoteroWebProvider(Settings('sqlite:///unused.db', [], '1', 'fixture-key'), client=client)
        described = provider.describe_attachment(Attachment('asset', 'paper', 'old.pdf', external_ref=ExternalReference('zotero', '1', 'FILE')))
    assert described.paper_id == 'zotero:1:PARENT'
    assert described.content_version == '7' and described.source_md5 == 'a' * 32


def local_database(root):
    root.mkdir()
    c = sqlite3.connect(root / 'zotero.sqlite')
    c.execute('PRAGMA journal_mode=WAL')
    c.executescript("""
        CREATE TABLE settings (setting TEXT,key TEXT,value);
        CREATE TABLE libraries (libraryID INTEGER PRIMARY KEY,type TEXT);
        CREATE TABLE items (itemID INTEGER PRIMARY KEY,libraryID INTEGER,key TEXT,version INTEGER);
        CREATE TABLE itemAttachments (itemID INTEGER PRIMARY KEY,parentItemID INTEGER,path TEXT,contentType TEXT,linkMode INTEGER);
        CREATE TABLE deletedItems (itemID INTEGER PRIMARY KEY);
        INSERT INTO settings VALUES ('account','userID',1);
        INSERT INTO libraries VALUES (1,'user');
        INSERT INTO items VALUES (1,1,'PARENT',1);
        INSERT INTO items VALUES (2,1,'FILE',1);
        INSERT INTO itemAttachments VALUES (2,1,'storage:paper.pdf','application/pdf',1);
    """)
    folder = root / 'storage' / 'FILE'
    folder.mkdir(parents=True)
    (folder / 'paper.pdf').write_bytes(pdf_bytes())
    return c


def test_local_source_snapshot_respects_uncommitted_wal_and_has_no_absolute_locator(tmp_path):
    root = tmp_path / 'zotero'
    def no_network(request):
        raise AssertionError('Local registered PDF unexpectedly used Web API')
    with closing(local_database(root)) as writer, httpx.Client(transport=httpx.MockTransport(no_network)) as client:
        provider = ZoteroWebProvider(Settings('sqlite:///unused.db', [], '1', '', zotero_data_dir=str(root)), client=client)
        try:
            writer.execute('UPDATE items SET version=2 WHERE itemID=2')
            source = Attachment('source', 'zotero:1:PARENT', 'cached.pdf', 'application/pdf', True, external_ref=ExternalReference('zotero', '1', 'FILE'))
            before = provider.describe_attachment(source)
            assert before.content_version.startswith('local:1:')
            assert writer.execute('SELECT version FROM items WHERE itemID=2').fetchone()[0] == 2
            writer.commit()
            after = provider.describe_attachment(source)
            assert after.content_version.startswith('local:2:')
            assert after.source_channel == 'zotero_local' and after.source_locator == 'storage/FILE/paper.pdf'
            assert str(root) not in json.dumps(asdict(after))
            opened = provider.open_attachment(after, range_header='bytes=0-9')
            assert opened.status_code == 206 and b''.join(opened.chunks) == pdf_bytes()[:10]
            assert (root / 'storage/FILE/paper.pdf').read_bytes() == pdf_bytes()
        finally:
            provider.close()


def test_local_source_rejects_wrong_account_and_escaping_registered_path(tmp_path):
    root = tmp_path / 'zotero'
    with closing(local_database(root)) as c:
        local = LocalZoteroFiles(root)
        try:
            with pytest.raises(ProviderAuthenticationError):
                local.describe(ExternalReference('zotero', 'other-account', 'FILE'))
            c.execute("UPDATE itemAttachments SET path='storage:../escape.pdf'")
            c.commit()
            (root / 'storage/escape.pdf').write_bytes(pdf_bytes())
            assert local.describe(ExternalReference('zotero', '1', 'FILE')) is None
        finally:
            local.close()


def test_local_snapshot_rejects_continuously_changing_source(tmp_path, monkeypatch):
    root = tmp_path / 'zotero'
    with closing(local_database(root)):
        local = LocalZoteroFiles(root)
        original = local._source_signature
        counter = 0
        def changing():
            nonlocal counter
            counter += 1
            signature = original()
            signature[''] = (signature[''][0], counter, signature[''][2])
            return signature
        monkeypatch.setattr(local, '_source_signature', changing)
        try:
            with pytest.raises(PdfUnavailableError, match='changed while taking'):
                local.describe(ExternalReference('zotero', '1', 'FILE'))
        finally:
            local.close()


def test_source_stream_staging_is_bounded_and_excluded_from_upload_cleanup(tmp_path, monkeypatch):
    import os
    files = LocalLiteratureFiles(str(tmp_path / 'vault'))
    data = pdf_bytes()
    staged = files.stage_source_pdf(iter([data[:20], data[20:]]), 'source.pdf')
    assert staged.size_bytes == len(data) and staged.md5 == md5(data).hexdigest()
    assert staged.staging_key.endswith('.acquiring')
    os.utime(files.staging / staged.staging_key, (1, 1))
    assert files.cleanup_staging(0) == 0
    key = files.finalize_pdf(staged.staging_key, staged.sha256)
    assert (files.originals / key).read_bytes() == data
    monkeypatch.setattr(file_module, 'MAX_SOURCE_PDF_BYTES', len(data) - 1)
    with pytest.raises(PdfSizeLimitError):
        files.stage_source_pdf(iter([data[:20], data[20:]]), 'too-large.pdf')
    assert list(files.staging.iterdir()) == []
    assert (files.originals / key).read_bytes() == data
