from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from app.core.config import load_settings
from app.modules.literature.application.errors import LocalAssetError
from app.modules.literature.application.ingestion import LiteratureIngestionService
from app.modules.literature.application.service import LiteratureService
from app.modules.literature.domain.models import Attachment
from app.modules.literature.infrastructure.files import LocalLiteratureFiles
from app.modules.literature.infrastructure.vault import inspect_vault
from .test_canonical_api import NoZotero, pdf_bytes
from .test_literature_workflows import workflow


def local_asset(key, digest=None):
    return Attachment('local', 'paper', 'paper.pdf', 'application/pdf', True, storage_kind='local', storage_key=key, sha256=digest)


@pytest.mark.skipif(os.name != 'nt', reason='Windows extended path representation')
def test_extended_path_spelling_during_directory_creation(tmp_path, monkeypatch):
    from app.modules.literature.infrastructure.files import _resolved

    path = tmp_path / 'new-directory'
    original = Path.resolve
    def extended(self, *args, **kwargs):
        resolved = original(self, *args, **kwargs)
        return Path('\\\\?\\' + str(resolved)) if self == path else resolved
    monkeypatch.setattr(Path, 'resolve', extended)
    assert _resolved(path) == path


def test_configured_vault_root_and_default_composition(tmp_path, monkeypatch):
    import app.main as main

    monkeypatch.setenv('LITERATURE_VAULT_ROOT', str(tmp_path / 'independent'))
    configured = load_settings()
    assert configured.literature_vault_root == str(tmp_path / 'independent')
    settings = replace(configured, database_url=f'sqlite:///{tmp_path / "db" / "workbench.db"}')
    monkeypatch.setattr(main, 'settings', settings)
    assert main.create_app().state.literature_service.files.root == tmp_path / 'independent'
    monkeypatch.setattr(main, 'settings', replace(settings, literature_vault_root=''))
    assert main.create_app().state.literature_service.files.root == tmp_path / 'db' / 'literature-assets'


def test_independent_originals_legacy_links_and_concurrent_duplicates(tmp_path):
    files = LocalLiteratureFiles(str(tmp_path / 'vault'))
    data = pdf_bytes()
    staged, digest = files.stage_pdf(data, 'first.pdf')
    key = files.finalize_pdf(staged, digest, keep_staging=True)
    (files.staging / staged).write_bytes(b'changed staging')
    assert b''.join(files.open(local_asset(key, digest)).chunks) == data
    with pytest.raises(ValueError, match='hash mismatch'):
        files.finalize_pdf(staged, digest)
    assert (files.originals / key).read_bytes() == data
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: files.store_pdf(data, 'renamed.pdf'), range(8)))
    assert set(results) == {(key, digest)}
    assert len(list(files.originals.iterdir())) == 1
    # Finalization also detaches retained staging in a legacy crash/retry layout.
    second = pdf_bytes(150)
    staged2, digest2 = files.stage_pdf(second, 'old-link.pdf')
    os.link(files.staging / staged2, files.originals / (digest2 + '.pdf'))
    files.finalize_pdf(staged2, digest2, keep_staging=True)
    (files.staging / staged2).write_bytes(b'changed old staging')
    assert (files.originals / (digest2 + '.pdf')).read_bytes() == second


def test_integrity_ranges_and_corrupt_target_never_overwrite(tmp_path, monkeypatch):
    files = LocalLiteratureFiles(str(tmp_path / 'vault'))
    data = pdf_bytes()
    key, digest = files.store_pdf(data, 'paper.pdf')
    asset = local_asset(key, digest)
    result = files.inspect(asset)
    assert result.state == 'verified' and result.size_bytes == len(data) and result.sha256 == digest
    assert b''.join(files.open(asset, range_header='bytes=-10').chunks) == data[-10:]
    assert files.open(asset, range_header='bytes=' + '9' * 5000 + '-').status_code == 416
    assert files.inspect(replace(asset, storage_key='../outside.pdf')).state == 'invalid'
    assert files.inspect(replace(asset, sha256='0' * 64)).state == 'invalid'
    assert files.inspect(replace(asset, storage_kind='s3')).state == 'unsupported_backend'
    assert files.inspect(replace(asset, storage_kind='zotero')).state == 'remote_only'
    original = files.originals / key
    original.write_bytes(b'X' + data[1:])
    assert files.inspect(asset).state == 'corrupt'
    with pytest.raises(LocalAssetError) as error:
        files.open(asset, range_header='bytes=0-3')
    assert error.value.state == 'corrupt'
    with pytest.raises(ValueError, match='inconsistent'):
        files.store_pdf(data, 'retry.pdf')
    assert original.read_bytes() == b'X' + data[1:]
    original.unlink()
    assert files.inspect(asset).state == 'missing'
    # Publication failure must leave staged bytes usable and no partial original.
    staged, digest = files.stage_pdf(data, 'retry.pdf')
    def fail_link(*args, **kwargs):
        raise OSError('injected publication failure')
    monkeypatch.setattr(os, 'link', fail_link)
    with pytest.raises(OSError):
        files.finalize_pdf(staged, digest)
    assert (files.staging / staged).read_bytes() == data
    assert list(files.originals.iterdir()) == []


def test_redirected_directories_cannot_read_write_or_cleanup(tmp_path):
    outside = tmp_path / 'outside'
    outside.mkdir()
    sentinel = outside / 'keep.pending'
    sentinel.write_bytes(b'keep')
    files = LocalLiteratureFiles(str(tmp_path / 'vault'))
    files.root.mkdir()
    for name in ('staging', 'originals'):
        link = files.root / name
        if os.name == 'nt':
            process = subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(outside)], capture_output=True)
            assert process.returncode == 0, process.stderr
        else:
            link.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError):
        files.stage_pdf(pdf_bytes(), 'unsafe.pdf')
    with pytest.raises(ValueError):
        files.cleanup_staging(0)
    assert files.inspect(local_asset('0' * 64 + '.pdf')).state == 'invalid'
    assert sentinel.read_bytes() == b'keep'


def test_integrity_api_and_reader_offline(workflow):
    repository, files, _, _, client = workflow
    ingestion = LiteratureIngestionService(repository, files, lambda _: None)
    result, asset = ingestion.upload_pdf(pdf_bytes(), 'offline.pdf')
    url = f'/api/literature/papers/{result.paper_id}'
    response = client.get(url + '/assets/integrity')
    assert response.status_code == 200
    assert response.json()['items'][0]['state'] == 'verified'
    assert str(files.root) not in response.text
    assert client.get(url + '/pdf', headers={'Range': 'bytes=0-9'}).content == pdf_bytes()[:10]
    (files.originals / asset.storage_key).write_bytes(b'broken')
    response = client.get(url + '/pdf', headers={'Range': 'bytes=0-9'})
    assert response.status_code == 409 and response.json()['detail']['code'] == 'local_asset_corrupt'
    assert client.get(url + '/assets/integrity').json()['items'][0]['state'] == 'corrupt'
    (files.originals / asset.storage_key).unlink()
    assert client.get(url + '/assets/integrity').json()['items'][0]['state'] == 'missing'


def test_relocation_dry_run_replay_and_legacy_keys(workflow, tmp_path):
    repository, files, upload, _, _ = workflow
    ingestion = LiteratureIngestionService(repository, files, lambda _: None)
    paper, asset = ingestion.upload_pdf(pdf_bytes(), 'relocate.pdf')
    # Exercise the old flat layout; records and keys must not change on relocation.
    (files.originals / asset.storage_key).rename(files.root / asset.storage_key)
    database = Path(repository._database_path)
    before = database.read_bytes()
    source_bytes = (files.root / asset.storage_key).read_bytes()
    target = tmp_path / 'relocated'
    report = inspect_vault(database, files.root, copy_to=target)
    assert report['status'] == 'planned' and not target.exists()
    command = [sys.executable, '-m', 'app.modules.literature.infrastructure.vault', '--database', str(database), '--root', str(files.root), '--copy-to', str(target)]
    planned = subprocess.run(command, capture_output=True, text=True, env={**os.environ, 'PYTHONPATH': str(Path(__file__).resolve().parents[1])})
    assert planned.returncode == 0, planned.stderr
    assert json.loads(planned.stdout)['status'] == 'planned' and not target.exists()
    report = inspect_vault(database, files.root, copy_to=target, apply=True)
    assert report['ready_to_switch'] and report['copies'][0]['status'] == 'copied_verified'
    replay = inspect_vault(database, files.root, copy_to=target, apply=True)
    assert replay['copies'][0]['status'] == 'already_verified'
    moved = LocalLiteratureFiles(str(target))
    reader = LiteratureService(NoZotero(), repository, moved)
    assert b''.join(reader.open_pdf(paper.paper_id).chunks) == source_bytes
    assert database.read_bytes() == before
    assert (files.root / asset.storage_key).read_bytes() == source_bytes
    with pytest.raises(ValueError):
        inspect_vault(database, files.root, copy_to=files.root / 'child', apply=True)
    batch = upload.create_batch()
    item = upload.stage_file(batch.id, 'pending.pdf', pdf_bytes(200))
    blocked_target = tmp_path / 'blocked'
    blocked = inspect_vault(database, files.root, copy_to=blocked_target, apply=True)
    assert blocked['status'] == 'blocked' and not blocked_target.exists()
    upload.cancel_batch(batch.id)
    (files.root / asset.storage_key).unlink()
    assert inspect_vault(database, files.root, copy_to=blocked_target, apply=True)['status'] == 'blocked'
    assert not blocked_target.exists()
