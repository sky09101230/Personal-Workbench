"""Audit configured real data read-only and exercise identity on an online backup.

Run from repo root: $env:PYTHONPATH='apps/api'; python apps/api/tests/manual_identity_acceptance.py
No provider requests, schema writes to the source, or application restart.
"""

import argparse
from contextlib import closing
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import tempfile
from uuid import uuid4

from app.core.config import settings
from app.modules.literature.domain.canonical import IdentityConflictError, Ingestion
from app.modules.literature.infrastructure.cache.audit_identity import audit_identity
from app.modules.literature.infrastructure.cache.canonical import backup_database
from app.modules.literature.infrastructure.cache.workflows import SQLiteLiteratureWorkflowRepository


def fingerprints(path):
    with closing(sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)) as c:
        c.execute('BEGIN')
        result = {}
        for (name,) in c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
            quoted = '"' + name.replace('"', '""') + '"'
            rows = sorted(repr(tuple(row)) for row in c.execute('SELECT * FROM ' + quoted))
            result[name] = {'count': len(rows), 'sha256': sha256('\n'.join(rows).encode()).hexdigest()}
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', default=settings.database_url.removeprefix('sqlite:///'))
    args = parser.parse_args()
    source = Path(args.database).resolve()
    before = fingerprints(source)
    real_report = audit_identity(source)
    assert audit_identity(source) == real_report
    Path('.venv/tmp').mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='identity-acceptance-', dir='.venv/tmp') as directory:
        copy = Path(directory) / 'acceptance.db'
        backup_database(str(source), str(copy))
        snapshot = fingerprints(copy)
        assert snapshot == before, 'Source changed during backup; rerun against a stable snapshot'
        repository = SQLiteLiteratureWorkflowRepository(f'sqlite:///{copy.resolve()}')
        repository.ensure_schema()
        upgraded = fingerprints(copy)
        for name, original in snapshot.items():
            if name not in {'literature_workflow_schema', 'literature_maintenance_actions'}:
                assert upgraded[name] == original, f'Schema upgrade changed historical rows in {name}'
        snapshot = upgraded
        copied_report = audit_identity(copy)
        page = repository.list_papers(limit=100)
        assert audit_identity(copy) == copied_report
        assert fingerprints(copy) == snapshot, 'Audit or repository read mutated existing rows'
        eligible = next((p for p in page.items if p.doi and p.year and p.authors and len(p.title) >= 12), None)
        assert eligible is not None, 'No eligible real paper for weak/strong replay acceptance'
        candidate = replace(eligible, id='', external_ref=None, doi=None, arxiv_id=None, openalex_id=None)
        try:
            repository.ingest(Ingestion(candidate, 'acceptance', str(uuid4())))
        except IdentityConflictError as error:
            assert eligible.id in error.candidates
        else:
            raise AssertionError('Weak bibliographic import was not rejected')
        assert fingerprints(copy) == snapshot, 'Rejected import changed existing rows'
        strong = Ingestion(replace(eligible, id='', external_ref=None), 'acceptance', str(uuid4()))
        replay = repository.ingest(strong)
        assert replay.paper_id == eligible.id and not replay.created
        assert repository.ingest(strong).paper_id == eligible.id
        after = fingerprints(copy)
        permitted = {'literature_documents', 'literature_origins', 'literature_metadata_evidence'}
        for name, original in snapshot.items():
            if name not in permitted:
                assert after[name] == original, f'Unexpected change to {name}'
        with closing(sqlite3.connect(copy)) as c:
            assert c.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
            assert not c.execute('PRAGMA foreign_key_check').fetchall()
        assert fingerprints(source) == before, 'Source changed during acceptance; investigate concurrent writes'
        print(json.dumps({
            'source_unchanged': True,
            'copied_tables_compared': len(snapshot),
            'literature_tables_compared': sum(name.startswith('literature_') for name in snapshot),
            'canonical_documents': real_report['counts']['literature_documents'],
            'audit_issues': len(real_report['issues']),
            'weak_aliases': len(real_report['weak_aliases']),
            'historical_unresolved_records': len(real_report['unresolved_records']),
            'weak_import_rejected_without_writes': True,
            'strong_replay_preserved_canonical_id': True,
            'protected_rows_preserved': True,
            'integrity': 'ok',
        }, indent=2))


if __name__ == '__main__':
    main()
