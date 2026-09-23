"""Reconcile saved acquisition reports into current, descriptor-scoped recovery state."""

import argparse
from hashlib import sha256
import json
from pathlib import Path

from app.modules.literature.infrastructure.acquire_assets import plan_acquisition
from app.modules.literature.infrastructure.cache.canonical import _attachment, _json, backup_database
from app.modules.literature.infrastructure.cache.identity import SQLiteLiteratureIdentityRepository


def reconcile_asset_state(database, plan, reports, *, apply=False):
    database = Path(database).resolve()
    if Path(plan.get('database', '')).resolve() != database or plan.get('format_version') != 1:
        raise ValueError('Plan does not match the configured database')
    if sha256(_json({key: value for key, value in plan.items() if key != 'plan_id'}).encode()).hexdigest() != plan.get('plan_id'):
        raise ValueError('Invalid plan digest')
    current = {item['source_asset_id']: item for item in plan_acquisition(database, plan['vault'], local_zotero=plan.get('local_zotero'))['assets']}
    originals = {item['source_asset_id']: item for item in plan['assets']}
    latest = {}
    for report in reports:
        if not report or report[0].get('event') != 'started' or report[0].get('plan_id') != plan['plan_id'] or report[-1].get('event') != 'completed' or report[-1].get('plan_id') != plan['plan_id']:
            raise ValueError('Only complete reports for this plan can be reconciled')
        for item in report:
            if item.get('event') == 'asset':
                if item.get('source_asset_id') not in originals:
                    raise ValueError('Report source is absent from the plan')
                if item.get('status') == 'failed' and (not isinstance(item.get('error'), str) or not 1 <= len(item['error']) <= 100):
                    raise ValueError('Failure report has no valid error code')
                latest[item['source_asset_id']] = item
    candidates = [key for key, value in latest.items() if value.get('status') == 'failed' and current.get(key) == originals[key]]
    result = {'dry_run': not apply, 'failed_observations': len(candidates), 'recorded': 0, 'skipped_owned_or_unchanged': 0, 'backup': None}
    if not apply:
        return result
    result['backup'] = backup_database(str(database))
    repository = SQLiteLiteratureIdentityRepository(f'sqlite:///{database}')
    repository.ensure_schema()
    for key in candidates:
        source = _attachment(originals[key]['source_snapshot'])
        if repository.owned_asset(source) is not None:
            result['skipped_owned_or_unchanged'] += 1
        elif repository.record_asset_failure(source, latest[key]['error']):
            result['recorded'] += 1
        else:
            result['skipped_owned_or_unchanged'] += 1
    return result


def main():
    from app.core.config import settings
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', default=settings.database_url.removeprefix('sqlite:///'))
    parser.add_argument('--plan', required=True)
    parser.add_argument('--reports', nargs='+', required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    plan = json.loads(Path(args.plan).read_text(encoding='utf-8'))
    reports = [[json.loads(line) for line in Path(path).read_text(encoding='utf-8').splitlines()] for path in args.reports]
    print(json.dumps(reconcile_asset_state(args.database, plan, reports, apply=args.apply), ensure_ascii=True, indent=2))


if __name__ == '__main__':
    main()
