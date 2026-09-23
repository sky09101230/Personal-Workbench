"""Opt-in real download into a copied DB/Vault; no live database mutation."""

import argparse
from dataclasses import replace
from hashlib import sha256
import json
import logging
from pathlib import Path
import tempfile

from app.core.config import settings
from app.modules.literature.application.service import LiteratureService
from app.modules.literature.infrastructure.acquire_assets import apply_acquisition, plan_acquisition
from app.modules.literature.infrastructure.cache.canonical import backup_database
from app.modules.literature.infrastructure.cache.identity import SQLiteLiteratureIdentityRepository
from app.modules.literature.infrastructure.files import LocalLiteratureFiles
from app.modules.literature.infrastructure.providers.zotero.provider import ZoteroWebProvider
from manual_identity_acceptance import fingerprints


class Offline:
    def open_attachment(self, *args, **kwargs):
        raise AssertionError('Owned replay unexpectedly called the provider')

    def describe_attachment(self, *args, **kwargs):
        raise AssertionError('Owned replay unexpectedly called the provider')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--zotero-data-dir', default=settings.zotero_data_dir or None)
    parser.add_argument('--offset', type=int, default=0)
    args = parser.parse_args()
    if not args.live:
        parser.error('Explicit --live is required for the real-source download rehearsal')
    logging.getLogger('app.modules.literature.infrastructure.providers.zotero.provider').setLevel(logging.CRITICAL)
    source = Path(settings.database_url.removeprefix('sqlite:///')).resolve()
    before = fingerprints(source)
    Path('.venv/tmp').mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='real-asset-rehearsal-', dir='.venv/tmp') as directory:
        root = Path(directory).resolve()
        database = root / 'copy.db'
        backup_database(str(source), str(database))
        plan = plan_acquisition(database, root / 'vault', local_zotero=args.zotero_data_dir)
        assert fingerprints(database) == before
        provider = ZoteroWebProvider(replace(settings, zotero_data_dir=args.zotero_data_dir or ''))
        try:
            result = apply_acquisition(plan, database, root / 'vault', provider, limit=1, offset=args.offset, local_zotero=args.zotero_data_dir)
        finally:
            provider.close()
        assert result['counts'] == {'acquired': 1}, result['results']
        acquired = result['results'][0]
        after = fingerprints(database)
        allowed = {'literature_workflow_schema', 'literature_maintenance_actions', 'literature_assets', 'literature_origins', 'literature_asset_acquisition_state'}
        for table, value in before.items():
            if table not in allowed:
                assert after[table] == value, table
        repository = SQLiteLiteratureIdentityRepository(f'sqlite:///{database}')
        files = LocalLiteratureFiles(str(root / 'vault'))
        reader = LiteratureService(Offline(), repository, files)
        data = b''.join(reader.open_pdf(acquired['paper_id'], asset_id=acquired['asset_id']).chunks)
        assert sha256(data).hexdigest() == acquired['sha256']
        ranged = reader.open_pdf(acquired['paper_id'], asset_id=acquired['asset_id'], range_header='bytes=0-31')
        assert ranged.status_code == 206 and b''.join(ranged.chunks) == data[:32]
        replay = apply_acquisition(plan, database, root / 'vault', Offline(), limit=1, offset=args.offset, local_zotero=args.zotero_data_dir)
        assert replay['counts'] == {'already_owned': 1} and fingerprints(database) == after
        assert fingerprints(source) == before
        print(json.dumps({'real_source_unchanged': True, 'historical_tables_checked': len(before), 'real_pdf_downloaded': True, 'size_bytes': acquired['size_bytes'], 'sha256': acquired['sha256'], 'observed_version': acquired['observed_version'], 'offline_full_and_range_reads': True, 'no_download_replay': True, 'research_rows_preserved': True}, indent=2))


if __name__ == '__main__':
    main()
