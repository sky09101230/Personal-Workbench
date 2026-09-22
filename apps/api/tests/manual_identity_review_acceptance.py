"""Read/audit real identity conflicts and exercise review only on an online backup."""

from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile

from app.core.config import settings
from app.modules.literature.infrastructure.cache.canonical import backup_database
from app.modules.literature.infrastructure.cache.identity import SQLiteLiteratureIdentityRepository
from manual_identity_acceptance import fingerprints


def main():
    source = Path(settings.database_url.removeprefix('sqlite:///')).resolve()
    before = fingerprints(source)
    dry = SQLiteLiteratureIdentityRepository(f'sqlite:///{source}').run_migration(dry_run=True)
    assert dry['workflow_schema_version'] == 4 and fingerprints(source) == before
    Path('.venv/tmp').mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='identity-review-acceptance-', dir='.venv/tmp') as directory:
        copy = Path(directory).resolve() / 'copy.db'
        backup_database(str(source), str(copy))
        repository = SQLiteLiteratureIdentityRepository(f'sqlite:///{copy}')
        repository.ensure_schema()
        upgraded = fingerprints(copy)
        for table, value in before.items():
            if table not in {'literature_workflow_schema', 'literature_maintenance_actions'}:
                assert upgraded[table] == value, f'Historical values changed during DDL: {table}'
        with closing(sqlite3.connect(copy)) as c:
            upgrade = json.loads(c.execute("SELECT report_json FROM literature_maintenance_actions WHERE name='identity_review_schema'").fetchone()[0])
            if 'literature_conflict_reviews' not in before:
                assert Path(upgrade['backup']).is_file()
        SQLiteLiteratureIdentityRepository(f'sqlite:///{copy}').ensure_schema()
        assert fingerprints(copy) == upgraded
        conflicts = repository.list_identity_conflicts()['items']
        orphaned = [item for item in conflicts if item['reason'] == 'Source asset parent unresolved']
        assert all(not item['paper_ids'] for item in orphaned)
        if orphaned:
            item = orphaned[0]
            reviewed = repository.decide_identity_conflict(item['id'], snapshot=item['snapshot'], decision='quarantine', reason='Disposable acceptance only: retain the original source payload without guessing a parent.')
            assert reviewed['payload'] == item['payload']
            reopened = repository.decide_identity_conflict(item['id'], snapshot=reviewed['snapshot'], decision='reopen', reason='Disposable acceptance only: restore this copied record to an open review state.')
            assert len(reopened['history']) == 2
        paper = next(p for p in repository.list_papers(limit=100).items if p.doi and p.metadata_status != 'conflict')
        context = repository.identity_context(paper.id)
        accepted = repository.review_identity(paper.id, snapshot=context['snapshot'], evidence_ids=[context['evidence'][0]['id']], reason='Disposable workflow acceptance, not a scientific verification of this real paper.')
        assert accepted['identity_status'].endswith('_confirmed')
        after = fingerprints(copy)
        for table, value in upgraded.items():
            if table not in {'literature_metadata_evidence', 'literature_conflict_reviews'}:
                assert after[table] == value, f'Research state changed: {table}'
        with closing(sqlite3.connect(copy)) as c:
            assert c.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
            assert not c.execute('PRAGMA foreign_key_check').fetchall()
        assert fingerprints(source) == before
        print(json.dumps({'source_unchanged': True, 'dry_run_source_unchanged': True, 'historical_tables_checked': len(before), 'copied_workflow_schema': 4, 'orphan_conflicts_observed': len(orphaned), 'orphan_parent_not_guessed': True, 'copied_review_and_reopen': True, 'canonical_and_research_rows_preserved': True, 'integrity': 'ok'}, indent=2))


if __name__ == '__main__':
    main()
