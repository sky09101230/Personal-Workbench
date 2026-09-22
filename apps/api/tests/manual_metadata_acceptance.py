"""Upgrade and review metadata on a real DB backup, preserving the live source."""

import argparse
from contextlib import closing
from dataclasses import replace
import json
from pathlib import Path
import sqlite3
import tempfile
from uuid import uuid4

from app.core.config import settings
from app.modules.literature.domain.canonical import Ingestion
from app.modules.literature.domain.workflow import metadata_snapshot
from app.modules.literature.infrastructure.cache.canonical import backup_database
from app.modules.literature.infrastructure.cache.workflows import SQLiteLiteratureWorkflowRepository
from manual_identity_acceptance import fingerprints


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', default=settings.database_url.removeprefix('sqlite:///'))
    args = parser.parse_args()
    source = Path(args.database).resolve()
    before = fingerprints(source)
    dry = SQLiteLiteratureWorkflowRepository(f'sqlite:///{source}').run_migration(dry_run=True)
    assert dry['workflow_schema_version'] == 3 and fingerprints(source) == before
    Path('.venv/tmp').mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='metadata-acceptance-', dir='.venv/tmp') as directory:
        copy = Path(directory).resolve() / 'copy.db'
        backup_database(str(source), str(copy))
        assert fingerprints(copy) == before
        repository = SQLiteLiteratureWorkflowRepository(f'sqlite:///{copy}')
        repository.ensure_schema()
        upgraded = fingerprints(copy)
        ledgers = {'literature_workflow_schema', 'literature_maintenance_actions'}
        for table, digest in before.items():
            if table not in ledgers:
                assert upgraded[table] == digest, f'Historical table changed during schema upgrade: {table}'
        with closing(sqlite3.connect(copy)) as c:
            report = json.loads(c.execute("SELECT report_json FROM literature_maintenance_actions WHERE name='metadata_evidence_schema'").fetchone()[0])
            if before.get('literature_proposal_evidence') is None:
                assert Path(report['backup']).is_file()
        SQLiteLiteratureWorkflowRepository(f'sqlite:///{copy}').ensure_schema()
        assert fingerprints(copy) == upgraded
        paper = next(p for p in repository.list_papers(limit=100).items if p.doi and p.metadata_status != 'conflict')
        old_title = paper.title
        incoming = replace(paper, title='Reviewed metadata acceptance ' + str(uuid4()), date_evidence={})
        repository.ingest(Ingestion(incoming, 'acceptance', str(uuid4()), priority=999, source='acceptance'))
        assert repository.get_paper(paper.id).paper.title == old_title
        proposal = next(p for p in repository.list_metadata_proposals(paper.id) if p.proposed_metadata.get('title') == incoming.title)
        assert proposal.evidence_ids
        repository.resolve_metadata_proposal(proposal.id, accept=True)
        current = repository.get_paper(paper.id).paper
        assert current.id == paper.id and current.doi == paper.doi and current.title == incoming.title
        repository.confirm_metadata(paper.id, metadata_snapshot(current))
        assert repository.get_paper(paper.id).paper.metadata_review_status == 'reviewed'
        after = fingerprints(copy)
        mutable = {'literature_documents', 'literature_metadata_evidence', 'literature_metadata_proposals', 'literature_proposal_evidence', 'literature_origins'}
        for table, digest in upgraded.items():
            if table not in mutable:
                assert after[table] == digest, f'Research state changed: {table}'
        with closing(sqlite3.connect(copy)) as c:
            assert c.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
            assert not c.execute('PRAGMA foreign_key_check').fetchall()
        assert fingerprints(source) == before
        print(json.dumps({'real_source_unchanged': True, 'dry_run_source_unchanged': True, 'historical_tables_checked': len(before), 'workflow_schema_version': 3, 'upgrade_replay_unchanged': True, 'source_overwrite_blocked': True, 'proposal_review_and_confirmation': True, 'canonical_and_research_state_preserved': True, 'integrity': 'ok'}, indent=2))


if __name__ == '__main__':
    main()
