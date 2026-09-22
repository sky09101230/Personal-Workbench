from contextlib import closing
from dataclasses import replace
import json
from pathlib import Path
import sqlite3

import pytest

from app.modules.literature.application.errors import WorkflowConflictError
from app.modules.literature.domain.canonical import Ingestion, IdentityConflictError
from app.modules.literature.domain.models import Paper, ExternalReference, ChangedPaper, LibraryChanges
from app.modules.literature.domain.workflow import metadata_snapshot
from app.modules.literature.infrastructure.cache import canonical
from app.modules.literature.infrastructure.cache.workflows import SQLiteLiteratureWorkflowRepository
from .test_literature_workflows import workflow


def test_sources_queue_evidence_without_mutating_canonical_fields(workflow):
    repository, _, _, review, _ = workflow
    p = Paper('source', 'Original accepted title', ('Alice',), year=2026, doi='10.1234/evidence', external_ref=ExternalReference('zotero', '1', 'A'))
    pid = repository.ingest(Ingestion(p, 'zotero_import', 'source', source='zotero')).paper_id
    assert repository.get_paper(pid).paper.metadata_status == 'complete'
    assert repository.get_paper(pid).paper.metadata_review_status == 'unreviewed'
    updated = replace(p, title='Updated source title', journal='Candidate Journal')
    changes = LibraryChanges(papers=(ChangedPaper(updated),), library_version='2')
    repository.apply_changes(provider='zotero', library_id='1', changes=changes)
    assert repository.get_paper(pid).paper.title == p.title
    assert repository.get_paper(pid).paper.journal is None
    proposals = review.list_proposals(pid)
    assert len(proposals) == 1 and proposals[0].evidence_ids
    evidence = {e['id']: e for e in repository.provenance(pid)['metadata_evidence']}
    assert evidence[proposals[0].evidence_ids[0]]['metadata']['title'] == updated.title
    assert repository.get_paper(pid).paper.metadata_review_status == 'needs_review'
    review.reject_proposal(proposals[0].id)
    # Even a newer source sync cursor must not reopen the same snapshot/candidate.
    repository.apply_changes(provider='zotero', library_id='1', changes=replace(changes, library_version='3'))
    assert len(review.list_proposals(pid)) == 1
    assert review.list_proposals(pid)[0].status == 'rejected'
    assert len(review.list_proposals(pid)[0].evidence_ids) == 2
    # Explicit user proposal can be reconsidered independently of source replay.
    proposal = review.create_proposal(pid, 'user', {'title': updated.title})
    review.accept_proposal(proposal.id)
    provenance = repository.provenance(pid)
    chosen = provenance['selected_fields']['title']
    decision = next(e for e in provenance['metadata_evidence'] if e['id'] == chosen['evidence_id'])
    assert chosen['reviewed'] and decision['evidence']['before']['title'] == p.title
    original_choice = decision['evidence']['previous_field_choices']['title']
    assert original_choice['source'] == 'zotero' and original_choice['evidence_id'] in evidence
    assert decision['evidence']['supporting_evidence_ids'] == list(proposal.evidence_ids)
    # Partial title review is not whole-record verification.
    assert repository.get_paper(pid).paper.metadata_review_status == 'unreviewed'


def test_publication_doi_waits_for_review_and_indexes_atomically(workflow):
    repository, _, _, review, _ = workflow
    preprint = Paper('preprint', 'Preprint title', ('Alice',), year=2026, doi='10.48550/arxiv.2609.12345', arxiv_id='2609.12345')
    pid = repository.ingest(Ingestion(preprint, 'manual', 'preprint')).paper_id
    publication = replace(preprint, id='publication', doi='10.1234/published')
    repository.ingest(Ingestion(publication, 'radar', 'published', priority=999, source='radar'))
    assert repository.get_paper(pid).paper.doi == preprint.doi
    assert not any(i['value'] == publication.doi for i in repository.provenance(pid)['identifiers'])
    proposal = review.list_proposals(pid)[0]
    assert proposal.proposed_metadata == {'doi': publication.doi}
    review.accept_proposal(proposal.id)
    assert repository.get_paper(pid).paper.doi == publication.doi
    indexed = {i['value'] for i in repository.provenance(pid)['identifiers']}
    assert preprint.doi in indexed and publication.doi in indexed
    assert repository.ingest(Ingestion(replace(publication, id=''), 'manual', 'repeat')).paper_id == pid


def test_conflicting_candidates_stale_confirmation_and_openalex_api(workflow):
    repository, _, _, review, client = workflow
    pid = repository.ingest(Ingestion(Paper('', 'Current metadata snapshot', ('Alice',), year=2026), 'manual', 'one')).paper_id
    repository.ingest(Ingestion(Paper('', 'Owned identifier', doi='10.1234/owned'), 'manual', 'other'))
    base = f'/api/literature/papers/{pid}'
    snapshot = metadata_snapshot(repository.get_paper(pid).paper)
    response = client.post(base + '/metadata/proposals', json={'source': 'ai_suggestion', 'proposed_metadata': {'doi': '10.1234/owned'}})
    assert response.status_code == 201
    conflict = response.json()
    assert conflict['identity_conflict'] and conflict['evidence_ids']
    assert client.post('/api/literature/metadata/proposals/' + conflict['id'] + '/accept').status_code == 409
    assert repository.get_paper(pid).paper.doi is None
    assert client.post(base + '/metadata/confirm', json={'snapshot': snapshot}).status_code == 409
    client.post('/api/literature/metadata/proposals/' + conflict['id'] + '/reject')
    prop = client.post(base + '/metadata/proposals', json={'source': 'user', 'proposed_metadata': {'openalex_id': 'https://openalex.org/W12345'}}).json()
    assert client.post('/api/literature/metadata/proposals/' + prop['id'] + '/accept').status_code == 200
    assert client.post(base + '/metadata/confirm', json={'snapshot': snapshot}).status_code == 409
    current = repository.get_paper(pid).paper
    assert current.openalex_id == 'W12345'
    response = client.post(base + '/metadata/confirm', json={'snapshot': metadata_snapshot(current)})
    assert response.status_code == 200 and response.json()['metadata_review_status'] == 'reviewed'
    evidence_id = response.json()['evidence_id']
    confirmation = next(e for e in repository.provenance(pid)['metadata_evidence'] if e['id'] == evidence_id)
    assert confirmation['evidence']['previous_field_choices']['openalex_id']['source'] == 'review:user'
    assert repository.get_paper(pid).paper.metadata_review_status == 'reviewed'
    assert client.post(base + '/metadata/confirm', json={'snapshot': metadata_snapshot(current)}).json()['evidence_id'] == evidence_id
    assert all(choice['reviewed'] for choice in repository.provenance(pid)['selected_fields'].values())


def test_metadata_edits_cannot_clear_unrelated_identity_conflict(workflow):
    repository, _, _, review, _ = workflow
    p = Paper('first', 'Conflicting source identity', ('Alice',), year=2026, doi='10.1234/one')
    repository.ingest(Ingestion(p, 'manual', 'one'))
    other = replace(p, id='other', doi='10.1234/two')
    repository.apply_changes(provider='zotero', library_id='1', changes=LibraryChanges(papers=(ChangedPaper(other),)))
    pid = repository.get_paper('other').paper.id
    assert repository.get_paper(pid).paper.metadata_status == 'conflict'
    prop = review.create_proposal(pid, 'user', {'abstract': 'Reviewed nonidentity field'})
    review.accept_proposal(prop.id)
    current = repository.get_paper(pid).paper
    assert current.metadata_status == 'conflict'
    with pytest.raises(WorkflowConflictError):
        review.confirm_metadata(pid, metadata_snapshot(current))


def test_schema_upgrade_backup_dry_run_replay_and_rollback(tmp_path, monkeypatch):
    path = tmp_path / 'v2.db'
    repository = SQLiteLiteratureWorkflowRepository(f'sqlite:///{path}')
    pid = repository.ingest(Ingestion(Paper('', 'Preserve original metadata'), 'manual', 'one')).paper_id
    with repository._connect() as c:
        c.execute('DROP TABLE literature_proposal_evidence')
        c.execute('DELETE FROM literature_workflow_schema WHERE version=3')
        c.execute("DELETE FROM literature_maintenance_actions WHERE name='metadata_evidence_schema'")
        original = c.execute('SELECT * FROM literature_documents').fetchall()
    before = path.read_bytes()
    upgrade = SQLiteLiteratureWorkflowRepository(f'sqlite:///{path}')
    dry = upgrade.run_migration(dry_run=True)
    assert dry['workflow_schema_version'] == 3 and path.read_bytes() == before
    schema = canonical._SCHEMA
    monkeypatch.setattr(canonical, '_SCHEMA', (*schema, 'INVALID SQL FOR ROLLBACK'))
    with pytest.raises(sqlite3.OperationalError):
        upgrade.ensure_schema()
    with closing(sqlite3.connect(path)) as c:
        assert not c.execute("SELECT 1 FROM sqlite_master WHERE name='literature_proposal_evidence'").fetchone()
        assert not c.execute('SELECT 1 FROM literature_workflow_schema WHERE version=3').fetchone()
    monkeypatch.setattr(canonical, '_SCHEMA', schema)
    upgrade.ensure_schema()
    with upgrade._connect() as c:
        assert list(map(tuple, c.execute('SELECT * FROM literature_documents'))) == list(map(tuple, original))
        report = json.loads(c.execute("SELECT report_json FROM literature_maintenance_actions WHERE name='metadata_evidence_schema'").fetchone()[0])
    backup = Path(report['backup'])
    assert backup.is_file()
    with closing(sqlite3.connect(backup)) as c:
        assert c.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert not c.execute('SELECT 1 FROM literature_workflow_schema WHERE version=3').fetchone()
    counts = len(list((tmp_path / 'backups').glob('*.db')))
    SQLiteLiteratureWorkflowRepository(f'sqlite:///{path}').ensure_schema()
    assert len(list((tmp_path / 'backups').glob('*.db'))) == counts
    assert upgrade.get_paper(pid).paper.title == 'Preserve original metadata'
