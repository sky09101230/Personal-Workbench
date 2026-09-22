"""Plan first, then explicitly acquire bounded batches without rewriting research data."""

import argparse
from collections import Counter
from contextlib import closing
from dataclasses import asdict, replace
from datetime import datetime, timezone
from hashlib import sha256
import json
import logging
import os
from pathlib import Path
import sqlite3
from uuid import uuid4

from app.modules.literature.application.materialization import PdfMaterializationService
from app.modules.literature.infrastructure.cache.canonical import _attachment, _json, backup_database
from app.modules.literature.infrastructure.cache.identity import SQLiteLiteratureIdentityRepository
from app.modules.literature.infrastructure.files import LocalLiteratureFiles


def plan_acquisition(database, root, *, local_zotero=None):
    database = Path(database).resolve()
    files = LocalLiteratureFiles(str(root))
    with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)) as c:
        c.row_factory = sqlite3.Row
        c.execute('PRAGMA query_only = ON')
        c.execute('BEGIN')
        tables = {row[0] for row in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {'literature_assets', 'literature_documents', 'literature_canonical_migrations'} <= tables or not c.execute('SELECT 1 FROM literature_canonical_migrations WHERE version=1').fetchone():
            raise ValueError('Explicit canonical migration is required before asset planning')
        assets, excluded = [], []
        for row in c.execute('SELECT a.id,a.payload_json,a.active,d.id AS owner FROM literature_assets a LEFT JOIN literature_documents d ON d.id=a.paper_id ORDER BY a.id'):
            asset = replace(_attachment(json.loads(row['payload_json'])), active=bool(row['active']))
            reason = 'managed_asset' if asset.storage_kind == 'local' else 'unsupported_backend' if asset.storage_kind != 'zotero' else 'not_pdf' if asset.content_type != 'application/pdf' else 'unavailable_source' if not asset.active or not asset.downloadable else 'missing_owner' if not row['owner'] else None
            if reason:
                excluded.append({'asset_id': asset.id, 'reason': reason})
            else:
                assets.append({'source_asset_id': asset.id, 'source_snapshot': asdict(asset)})
        orphans = []
        if 'literature_identity_conflicts' in tables:
            for row in c.execute("SELECT id,legacy_id,payload_json FROM literature_identity_conflicts WHERE reason='Source asset parent unresolved' ORDER BY id"):
                payload = json.loads(row['payload_json'])
                orphans.append({'conflict_id': row['id'], 'source_id': row['legacy_id'], 'content_type': payload.get('content_type'), 'status': 'unresolved_parent'})
    plan = {'format_version': 1, 'database': str(database), 'vault': str(files.root), 'local_zotero': str(Path(local_zotero).resolve()) if local_zotero else None, 'assets': assets, 'excluded': excluded, 'orphan_sources': orphans}
    plan['plan_id'] = sha256(_json(plan).encode()).hexdigest()
    return plan


def apply_acquisition(plan, database, root, provider, *, offset=0, limit=20, asset_ids=(), refresh=False, on_result=None, local_zotero=None):
    if not 1 <= limit <= 100 or offset < 0:
        raise ValueError('Batch must contain 1 to 100 planned assets')
    database = Path(database).resolve()
    files = LocalLiteratureFiles(str(root))
    if plan.get('format_version') != 1 or Path(plan.get('database', '')) != database or Path(plan.get('vault', '')) != files.root:
        raise ValueError('Plan database/Vault binding does not match')
    if plan.get('local_zotero') != (str(Path(local_zotero).resolve()) if local_zotero else None):
        raise ValueError('Local Zotero source differs from the plan')
    payload = {key: value for key, value in plan.items() if key != 'plan_id'}
    if sha256(_json(payload).encode()).hexdigest() != plan.get('plan_id'):
        raise ValueError('Plan contents changed; generate a new plan')
    planned = plan['assets']
    if asset_ids:
        selected_ids = set(asset_ids)
        if selected_ids - {item['source_asset_id'] for item in planned}:
            raise ValueError('Requested asset is absent from the plan')
        planned = [item for item in planned if item['source_asset_id'] in selected_ids]
    selected = planned[offset:offset + limit]
    # Read before writes; changed source descriptors become explicit per-asset results.
    current = {item['source_asset_id']: item for item in plan_acquisition(database, files.root)['assets']}
    backup = backup_database(str(database))
    if on_result:
        on_result({'event': 'started', 'plan_id': plan['plan_id'], 'backup': backup, 'selected': len(selected)})
    repository = SQLiteLiteratureIdentityRepository(f'sqlite:///{database}')
    repository.ensure_schema()
    service = PdfMaterializationService(repository, files, provider)
    results = []
    for item in selected:
        if current.get(item['source_asset_id']) != item:
            result = {'source_asset_id': item['source_asset_id'], 'status': 'failed', 'error': 'planned_source_changed'}
        else:
            result = asdict(service.acquire_asset(_attachment(item['source_snapshot']), refresh=refresh))
        results.append(result)
        if on_result:
            on_result({'event': 'asset', **result})
    return {'event': 'completed', 'plan_id': plan['plan_id'], 'backup': backup, 'offset': offset, 'selected': len(selected), 'counts': dict(Counter(item['status'] for item in results)), 'results': results, 'orphan_sources': plan['orphan_sources']}


def main():
    from app.core.config import settings
    from app.modules.literature.infrastructure.providers.zotero.provider import ZoteroWebProvider

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', default=settings.database_url.removeprefix('sqlite:///'))
    parser.add_argument('--root', default=settings.literature_vault_root or None)
    parser.add_argument('--zotero-data-dir', default=settings.zotero_data_dir or None)
    parser.add_argument('--plan', help='Existing reviewed plan required for apply')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--report', help='New plan JSON or apply JSONL path; never overwritten')
    parser.add_argument('--offset', type=int, default=0)
    parser.add_argument('--limit', type=int, default=20)
    parser.add_argument('--asset-id', action='append', default=[])
    parser.add_argument('--refresh', action='store_true', help='Re-observe an already owned source explicitly')
    args = parser.parse_args()
    root = args.root or Path(args.database).parent / 'literature-assets'
    logging.getLogger('app.modules.literature.infrastructure.providers.zotero.provider').setLevel(logging.CRITICAL)
    try:
        if not args.apply:
            plan = plan_acquisition(args.database, root, local_zotero=args.zotero_data_dir)
            if args.report:
                report = Path(args.report)
                report.parent.mkdir(parents=True, exist_ok=True)
                with report.open('x', encoding='utf-8') as stream:
                    json.dump(plan, stream, ensure_ascii=False, indent=2)
                print(json.dumps({'plan_id': plan['plan_id'], 'read_only': True, 'eligible_pdfs': len(plan['assets']), 'roles': dict(Counter(item['source_snapshot']['role'] for item in plan['assets'])), 'excluded': dict(Counter(item['reason'] for item in plan['excluded'])), 'orphan_sources': len(plan['orphan_sources']), 'report': str(report.resolve())}, ensure_ascii=False), flush=True)
            else:
                print(json.dumps(plan, ensure_ascii=False, indent=2))
            return
        if not args.plan:
            parser.error('--apply requires --plan from a read-only planning run')
        plan = json.loads(Path(args.plan).read_text(encoding='utf-8'))
        default_name = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S') + '-' + uuid4().hex[:8] + '.jsonl'
        report = Path(args.report) if args.report else Path('data/literature-migration-reports') / default_name
        report.parent.mkdir(parents=True, exist_ok=True)
        provider = ZoteroWebProvider(replace(settings, zotero_data_dir=args.zotero_data_dir or ''))
        try:
            with report.open('x', encoding='utf-8') as output:
                def event(value):
                    line = json.dumps(value, ensure_ascii=False)
                    output.write(line + '\n')
                    output.flush()
                    os.fsync(output.fileno())
                    print(line, flush=True)
                result = apply_acquisition(plan, args.database, root, provider, offset=args.offset, limit=args.limit, asset_ids=args.asset_id, refresh=args.refresh, on_result=event, local_zotero=args.zotero_data_dir)
                event({key: value for key, value in result.items() if key != 'results'})
                print(json.dumps({'report': str(report.resolve())}), flush=True)
        finally:
            provider.close()
        if result['counts'].get('failed'):
            raise SystemExit(1)
    except (ValueError, OSError, sqlite3.Error, KeyError, TypeError):
        parser.error('Plan/apply failed; inspect database/Vault bindings, plan validity and write permissions. Existing data was not deleted.')


if __name__ == '__main__':
    main()
