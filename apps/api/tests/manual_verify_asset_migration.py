"""Verify a completed real acquisition against its saved baseline and first backup."""

import argparse
from collections import Counter
from contextlib import closing
from hashlib import file_digest, sha256
import json
from pathlib import Path
import sqlite3

from app.core.config import settings
from app.modules.literature.application.service import LiteratureService
from app.modules.literature.infrastructure.acquire_assets import apply_acquisition
from app.modules.literature.infrastructure.cache.canonical import _attachment
from app.modules.literature.infrastructure.cache.identity import SQLiteLiteratureIdentityRepository
from app.modules.literature.infrastructure.files import LocalLiteratureFiles
from app.modules.literature.infrastructure.providers.zotero.local_files import LocalZoteroFiles
from app.modules.literature.domain.models import ExternalReference
from manual_identity_acceptance import fingerprints


class Offline:
    calls = 0

    def describe_attachment(self, *args, **kwargs):
        self.calls += 1
        raise AssertionError('Owned replay called a source provider')

    def open_attachment(self, *args, **kwargs):
        self.calls += 1
        raise AssertionError('Owned Reader called a source provider')


def rows(path, table):
    with closing(sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)) as c:
        return {row[0]: tuple(row) for row in c.execute('SELECT * FROM ' + table)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', required=True)
    parser.add_argument('--baseline', required=True)
    parser.add_argument('--first-run', required=True)
    parser.add_argument('--large-baseline')
    parser.add_argument('--report', required=True)
    args = parser.parse_args()
    plan = json.loads(Path(args.plan).read_text(encoding='utf-8'))
    baseline = json.loads(Path(args.baseline).read_text(encoding='utf-8'))
    first = json.loads(Path(args.first_run).read_text(encoding='utf-8').splitlines()[0])
    assert first['plan_id'] == baseline['plan_id'] == plan['plan_id']
    database, vault = Path(plan['database']), Path(plan['vault'])
    assert database.resolve() == Path(settings.database_url.removeprefix('sqlite:///')).resolve(), 'Plan does not match the configured database'
    after = fingerprints(database)
    allowed = {'literature_assets', 'literature_origins', 'literature_workflow_schema', 'literature_maintenance_actions'}
    protected = 0
    for table, value in baseline['tables'].items():
        if table not in allowed:
            assert after[table] == value, f'Protected table changed: {table}'
            protected += 1
    # Even allowed tables must retain every original row; only ledger/data additions are allowed.
    for table in allowed:
        old, current = rows(first['backup'], table), rows(database, table)
        assert all(current.get(key) == row for key, row in old.items()), f'Existing row changed: {table}'
    repository = SQLiteLiteratureIdentityRepository(f'sqlite:///{database}')
    files = LocalLiteratureFiles(str(vault))
    offline = Offline()
    reader = LiteratureService(offline, repository, files)
    with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)) as c:
        assets = [_attachment(json.loads(row[0])) for row in c.execute('SELECT payload_json FROM literature_assets')]
        copies = c.execute('SELECT source_asset_id,asset_id,observed_snapshot_json FROM literature_asset_copies').fetchall()
        assert c.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert not c.execute('PRAGMA foreign_key_check').fetchall()
    owned = [asset for asset in assets if asset.storage_kind == 'local']
    default_readers = set()
    unique = {}
    for asset in owned:
        inspection = files.inspect(asset)
        assert inspection.state == 'verified'
        with (files.originals / asset.storage_key).open('rb') as stream:
            assert file_digest(stream, 'sha256').hexdigest() == asset.sha256
        unique[asset.sha256] = inspection.size_bytes
        if repository.get_paper(asset.paper_id) is not None:
            data = b''.join(reader.open_pdf(asset.paper_id, asset_id=asset.id).chunks)
            assert sha256(data).hexdigest() == asset.sha256
            partial = reader.open_pdf(asset.paper_id, asset_id=asset.id, range_header='bytes=0-31')
            assert partial.status_code == 206 and b''.join(partial.chunks) == data[:32]
            if asset.role == 'primary':
                chosen = reader.primary_attachment(asset.paper_id)
                assert chosen.storage_kind == 'local'
                opened = reader.open_pdf(asset.paper_id, range_header='bytes=0-31')
                assert opened.status_code == 206 and b''.join(opened.chunks).startswith(b'%PDF-')
                default_readers.add(asset.paper_id)
    unchanged_sources = 0
    if plan.get('local_zotero'):
        local = LocalZoteroFiles(plan['local_zotero'])
        by_id = {item['source_asset_id']: item for item in plan['assets']}
        owned_by_id = {asset.id: asset for asset in owned}
        original_hashes = {item['source_asset_id']: item['md5'] for item in baseline['local_sources'] if item['md5']}
        if args.large_baseline:
            large = json.loads(Path(args.large_baseline).read_text(encoding='utf-8'))
            matching = next(item['source_asset_id'] for item in plan['assets'] if item['source_snapshot']['external_ref']['item_key'] == large['key'])
            original_hashes[matching] = large['data']['md5']
        try:
            for source_id, asset_id, observed in copies:
                observation = json.loads(observed)
                if observation.get('source_channel') != 'zotero_local':
                    continue
                reference = ExternalReference(**by_id[source_id]['source_snapshot']['external_ref'])
                current = local.describe(reference)
                assert current and current['data']['md5'] == original_hashes[source_id]
                path, _ = local._locate(reference)
                with path.open('rb') as stream:
                    assert file_digest(stream, 'sha256').hexdigest() == owned_by_id[asset_id].sha256
                unchanged_sources += 1
        finally:
            local.close()
    # Replay only successfully owned source mappings with a provider that cannot fetch anything.
    replay_before = fingerprints(database)
    replay = apply_acquisition(plan, database, vault, offline, asset_ids=[source_id for source_id, _, _ in copies], limit=100, local_zotero=plan.get('local_zotero'))
    assert replay['counts'] == {'already_owned': len(copies)}
    assert fingerprints(database) == replay_before and offline.calls == 0
    missing = [item['source_asset_id'] for item in plan['assets'] if item['source_asset_id'] not in {row[0] for row in copies}]
    report = {'protected_tables_unchanged': protected, 'all_original_rows_retained': True, 'source_pdf_mappings': len(copies), 'owned_asset_records': len(owned), 'verified_content_objects': len(unique), 'unique_bytes': sum(unique.values()), 'owned_roles': dict(Counter(asset.role for asset in owned)), 'source_files_unchanged': unchanged_sources, 'offline_default_reader_papers': len(default_readers), 'offline_full_and_range_reads': len(owned), 'no_download_replay': replay['counts'], 'missing_source_assets': missing, 'orphan_sources': len(plan['orphan_sources']), 'integrity': 'ok', 'foreign_key_errors': []}
    with Path(args.report).open('x', encoding='utf-8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    print(json.dumps({key: value for key, value in report.items() if key != 'missing_source_assets'} | {'missing_source_count': len(missing)}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
