"""Exercise production Vault/Reader on a real DB backup; never mutate the source."""

import io
import json
from pathlib import Path
import tempfile
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pypdf import PdfWriter

from app.core.config import settings
from app.modules.literature.application.ingestion import LiteratureIngestionService
from app.modules.literature.application.service import LiteratureService
from app.modules.literature.infrastructure.cache.canonical import backup_database
from app.modules.literature.infrastructure.cache.workflows import SQLiteLiteratureWorkflowRepository
from app.modules.literature.infrastructure.files import LocalLiteratureFiles
from app.modules.literature.infrastructure.vault import inspect_vault
from app.modules.literature.presentation.router import router
from manual_identity_acceptance import fingerprints


class OfflineProvider:
    name = 'zotero'
    configured = False

    def open_attachment(self, *args, **kwargs):
        raise AssertionError('Owned asset unexpectedly contacted the external provider')


def main():
    source = Path(settings.database_url.removeprefix('sqlite:///')).resolve()
    real_before = fingerprints(source)
    real_root = settings.literature_vault_root or source.parent / 'literature-assets'
    real_inventory = inspect_vault(source, real_root)
    Path('.venv/tmp').mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='vault-acceptance-', dir='.venv/tmp') as directory:
        work = Path(directory).resolve()
        database = work / 'copy.db'
        backup_database(str(source), str(database))
        repository = SQLiteLiteratureWorkflowRepository(f'sqlite:///{database}')
        files = LocalLiteratureFiles(str(work / 'vault'))
        seeded = inspect_vault(source, real_root, copy_to=files.root, apply=True)
        assert seeded['ready_to_switch'], 'Source has pending staging or owned assets requiring integrity review'
        writer = PdfWriter()
        writer.add_blank_page(width=612, height=792)
        writer.add_metadata({'/Title': 'Vault relocation acceptance'})
        buffer = io.BytesIO()
        writer.write(buffer)
        data = buffer.getvalue()
        ingestion = LiteratureIngestionService(repository, files, lambda _: None)
        paper, asset = ingestion.upload_pdf(data, 'acceptance.pdf', title='Vault acceptance ' + str(uuid4()))
        before_copy = fingerprints(database)
        destination = work / 'relocated'
        plan = inspect_vault(database, files.root, copy_to=destination)
        assert plan['status'] == 'planned'
        assert not destination.exists()
        applied = inspect_vault(database, files.root, copy_to=destination, apply=True)
        assert applied['ready_to_switch']
        replay = inspect_vault(database, files.root, copy_to=destination, apply=True)
        assert all(item['status'] == 'already_verified' for item in replay['copies'])
        assert fingerprints(database) == before_copy
        assert (files.originals / asset.storage_key).read_bytes() == data
        # Use the real presentation router without the application's global source/DB startup.
        app = FastAPI()
        app.state.literature_service = LiteratureService(OfflineProvider(), repository, LocalLiteratureFiles(str(destination)))
        app.include_router(router, prefix='/api/literature')
        with TestClient(app) as client:
            path = '/api/literature/papers/' + paper.paper_id
            assert client.get(path + '/pdf').content == data
            response = client.get(path + '/pdf', headers={'Range': 'bytes=0-31'})
            assert response.status_code == 206 and response.content == data[:32]
            verified = next(item for item in client.get(path + '/assets/integrity').json()['items'] if item['asset_id'] == asset.id)
            assert verified['state'] == 'verified' and verified['sha256'] == asset.sha256
        assert fingerprints(source) == real_before
        print(json.dumps({
            'real_inventory': real_inventory['counts'],
            'real_source_unchanged': True,
            'dry_run_created_no_destination': True,
            'relocation_verified': applied['ready_to_switch'],
            'replay': replay['copies'],
            'database_tables_preserved': len(before_copy),
            'source_bytes_preserved': True,
            'offline_reader_full_and_range': True,
            'canonical_id_and_key_unchanged': True,
        }, indent=2))


if __name__ == '__main__':
    main()
