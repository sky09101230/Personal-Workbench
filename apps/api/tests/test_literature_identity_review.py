from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.modules.literature.application.identity import IdentityReviewService
from app.modules.literature.application.ingestion import LiteratureIngestionService
from app.modules.literature.application.service import LiteratureService
from app.modules.literature.application.errors import WorkflowConflictError
from app.modules.literature.domain.ai_models import LiteratureUserNote
from app.modules.literature.domain.canonical import Ingestion, IdentityConflictError
from app.modules.literature.domain.models import Paper, ChangedPaper, LibraryChanges
from app.modules.literature.infrastructure.cache.identity import SQLiteLiteratureIdentityRepository
from app.modules.literature.infrastructure.files import LocalLiteratureFiles
from .test_canonical_api import NoZotero, pdf_bytes


@pytest.fixture
def identity(tmp_path, override_service):
    repository = SQLiteLiteratureIdentityRepository(f'sqlite:///{tmp_path / "identity.db"}')
    files = LocalLiteratureFiles(str(tmp_path / 'vault'))
    override_service('identity_review_service', IdentityReviewService(repository))
    override_service('literature_service', LiteratureService(NoZotero(), repository, files))
    return repository, files, TestClient(app)


def proof(context, **extra):
    return {'snapshot': context['snapshot'], 'evidence_ids': [context['evidence'][0]['id']], 'reason': 'User checked the identifiers against the recorded source evidence.', **extra}


def test_identity_confirmation_correction_and_staleness(identity):
    repository, files, client = identity
    pid = repository.ingest(Ingestion(Paper('source', 'Published identity review', doi='10.1234/original'), 'manual', 'one')).paper_id
    repository.save_user_note(LiteratureUserNote('note', pid, 'Preserve my note', 'manual', 'before', 'before'))
    ingestion = LiteratureIngestionService(repository, files, lambda _: None)
    _, asset = ingestion.upload_pdf(pdf_bytes(), 'paper.pdf', paper_id=pid)
    path = f'/api/literature/papers/{pid}/identity'
    context = client.get(path).json()
    confirmed = client.post(path + '/confirm', json=proof(context))
    assert confirmed.status_code == 200 and confirmed.json()['identity_status'] == 'published_confirmed'
    assert client.post(path + '/confirm', json=proof(context)).status_code == 409
    current = confirmed.json()
    corrected = client.post(path + '/correct', json=proof(current, correction={'doi': '10.1234/corrected', 'arxiv_id': None, 'openalex_id': None}))
    assert corrected.status_code == 200, corrected.text
    assert corrected.json()['identity_status'] == 'needs_review'
    assert repository.get_paper('source').paper.id == pid
    assert repository.get_paper(pid).paper.doi == '10.1234/corrected'
    assert repository.list_user_notes(pid)[0].content == 'Preserve my note'
    assert repository.list_attachments(pid)[0].id == asset.id
    assert not any(item['value'] == '10.1234/original' for item in corrected.json()['identifiers'])
    decision = corrected.json()['evidence'][-1]['evidence']
    assert decision['before']['doi'] == '10.1234/original'
    owner = repository.ingest(Ingestion(Paper('', 'Another canonical paper', doi='10.1234/owned'), 'manual', 'owner')).paper_id
    response = client.post(path + '/correct', json=proof(corrected.json(), correction={'doi': '10.1234/owned', 'arxiv_id': None, 'openalex_id': None}))
    assert response.status_code == 409
    assert repository.get_paper(pid).paper.doi == '10.1234/corrected'
    assert repository.get_paper(owner).paper.doi == '10.1234/owned'
    response = client.post(path + '/confirm', json=proof(repository.identity_context(pid), evidence_ids=['unowned-evidence']))
    assert response.status_code == 422


def test_metadata_change_invalidates_identity_confirmation(identity):
    repository, _, _ = identity
    pid = repository.ingest(Ingestion(Paper('', 'Current preprint', arxiv_id='2609.12345'), 'manual', 'one')).paper_id
    assert repository.review_identity(pid, **proof(repository.identity_context(pid)))['identity_status'] == 'preprint_confirmed'
    proposal = repository.create_metadata_proposal(pid, 'user', {'title': 'Corrected preprint title'})
    repository.resolve_metadata_proposal(proposal.id, accept=True)
    assert repository.get_paper(pid).paper.identity_status == 'needs_review'


def test_weak_conflict_is_durable_and_exact_reviewed_retry_stays_separate(identity):
    repository, _, client = identity
    p = Paper('', 'Matching title without scholarly identifiers', ('Alice',), year=2026)
    first = repository.ingest(Ingestion(p, 'manual', 'one')).paper_id
    incoming = Ingestion(p, 'manual', 'two')
    for _ in range(2):
        with pytest.raises(IdentityConflictError):
            repository.ingest(incoming)
    queue = client.get('/api/literature/identity/conflicts').json()
    assert queue['total'] == 1
    conflict = queue['items'][0]
    decision = {'snapshot': conflict['snapshot'], 'decision': 'keep_separate', 'reason': 'I checked both records; these are distinct no-DOI publications.'}
    response = client.post('/api/literature/identity/conflicts/' + conflict['id'] + '/decisions', json=decision)
    assert response.status_code == 200, response.text
    second = repository.ingest(incoming).paper_id
    assert second != first and repository.ingest(incoming).paper_id == second
    assert repository.get_paper(second).paper.identity_status == 'unresolved'
    # A changed input has no license from the previous review.
    with pytest.raises(IdentityConflictError):
        repository.ingest(replace(incoming, origin_key='third'))
    assert repository.list_papers().total == 2


def test_orphan_quarantine_reopen_retains_payload(identity):
    repository, _, client = identity
    repository.ensure_schema()
    payload = {'id': 'source-file', 'paper_id': 'missing-parent', 'filename': 'orphan.pdf'}
    with repository._connect() as c:
        cid = repository._conflict(c, 'source-file', 'Source asset parent unresolved', payload)
    record = repository.list_identity_conflicts()['items'][0]
    assert record['paper_ids'] == []
    decision = {'snapshot': record['snapshot'], 'decision': 'quarantine', 'reason': 'Parent is unavailable; retain the descriptor for later source recovery.'}
    reviewed = client.post(f'/api/literature/identity/conflicts/{cid}/decisions', json=decision).json()
    assert reviewed['decision'] == 'quarantine' and reviewed['payload'] == payload
    assert client.post(f'/api/literature/identity/conflicts/{cid}/decisions', json=decision).status_code == 409
    reopened = repository.decide_identity_conflict(cid, snapshot=reviewed['snapshot'], decision='reopen', reason='New source information is available for another review.')
    assert reopened['decision'] == 'reopen' and len(reopened['history']) == 2
    assert repository.list_papers().total == 0


def test_strong_conflicts_cannot_be_overridden_by_separate_review(identity):
    repository, _, _ = identity
    a = repository.ingest(Ingestion(Paper('a', 'First source paper', doi='10.1234/a'), 'manual', 'a')).paper_id
    repository.ingest(Ingestion(Paper('b', 'Second source paper', doi='10.1234/b'), 'manual', 'b'))
    with pytest.raises(IdentityConflictError):
        repository.ingest(Ingestion(Paper('a', 'First source paper', doi='10.1234/b'), 'manual', 'a'))
    conflict = repository.list_identity_conflicts()['items'][0]
    with pytest.raises(WorkflowConflictError):
        repository.decide_identity_conflict(conflict['id'], snapshot=conflict['snapshot'], decision='keep_separate', reason='Cannot bypass a strong identifier owner conflict with a weak decision.')
    result = repository.decide_identity_conflict(conflict['id'], snapshot=conflict['snapshot'], decision='keep_current', reason='The new claim was erroneous; keep both currently accepted identities.')
    assert result['decision'] == 'keep_current'
    assert repository.get_paper(a).paper.doi == '10.1234/a'


def test_versions_preserve_independent_ownership_and_retraction_history(identity):
    repository, files, client = identity
    a = repository.ingest(Ingestion(Paper('', 'Preprint version', arxiv_id='2609.12345'), 'manual', 'preprint')).paper_id
    b = repository.ingest(Ingestion(Paper('', 'Published version', doi='10.1234/published'), 'manual', 'published')).paper_id
    repository.save_user_note(LiteratureUserNote('preprint-note', a, 'Preprint note remains here', 'manual', 'before', 'before'))
    repository.save_user_note(LiteratureUserNote('publication-note', b, 'Publication note remains here', 'manual', 'before', 'before'))
    ingestion = LiteratureIngestionService(repository, files, lambda _: None)
    _, first_asset = ingestion.upload_pdf(pdf_bytes(), 'preprint.pdf', paper_id=a)
    _, second_asset = ingestion.upload_pdf(pdf_bytes(), 'published.pdf', paper_id=b)
    left, right = repository.identity_context(a), repository.identity_context(b)
    request = {'published_id': b, 'preprint_snapshot': left['snapshot'], 'published_snapshot': right['snapshot'], 'evidence_ids': [left['evidence'][0]['id'], right['evidence'][0]['id']], 'reason': 'The source publication explicitly identifies this arXiv preprint as its earlier version.'}
    response = client.post(f'/api/literature/papers/{a}/versions', json=request)
    assert response.status_code == 200, response.text
    linked = response.json()
    assert linked['status'] == 'active'
    assert client.post(f'/api/literature/papers/{a}/versions', json=request).json()['id'] == linked['id']
    assert repository.list_papers().total == 2
    assert repository.get_paper(a).paper.doi is None
    assert repository.get_paper(b).paper.arxiv_id is None
    retracted = client.post(f'/api/literature/versions/{linked["id"]}/retract', json={'snapshot': linked['snapshot'], 'reason': 'The relationship needs additional source validation before use.'})
    assert retracted.status_code == 200 and retracted.json()['status'] == 'retracted'
    assert [item['action'] for item in retracted.json()['evidence']['history']] == ['linked', 'retracted']
    assert repository.list_user_notes(a)[0].id == 'preprint-note'
    assert repository.list_user_notes(b)[0].id == 'publication-note'
    assert repository.list_attachments(a)[0].id == first_asset.id != second_asset.id
    assert repository.list_attachments(b)[0].id == second_asset.id
    assert first_asset.sha256 == second_asset.sha256


def test_radar_group_members_are_not_automatically_saved(identity):
    repository, files, _ = identity
    exported = {'paper': {'title': 'Discovery grouping', 'doi': '10.1234/selected'}, 'appearances': [{'recommendation_id': 'old-weak-match', 'recommendation_reason': 'Earlier weak grouping'}, {'recommendation_id': 'selected', 'recommendation_reason': 'Explicitly selected'}]}
    service = LiteratureIngestionService(repository, files, lambda _: exported)
    pid = service.save_radar('selected').paper_id
    assert repository.saved_origins(['selected', 'old-weak-match']) == {'selected': pid}
    origin = repository.provenance(pid)['origins'][0]
    assert origin['evidence']['metadata_scope'] == 'current_discovery_snapshot'
    assert origin['evidence']['unverified_related_appearances'][0]['recommendation_id'] == 'old-weak-match'
    assert service.save_radar('old-weak-match').paper_id == pid
    assert len(repository.saved_origins(['selected', 'old-weak-match'])) == 2


def test_rejected_source_replay_does_not_reopen_reviewed_conflict(identity):
    repository, _, _ = identity
    p = Paper('source', 'Stable source identity', doi='10.1234/one')
    pid = repository.ingest(Ingestion(p, 'manual', 'original')).paper_id
    changes = LibraryChanges(papers=(ChangedPaper(replace(p, doi='10.1234/wrong')),), library_version='5')
    repository.apply_changes(provider='zotero', library_id='1', changes=changes)
    assert repository.get_paper(pid).paper.identity_status == 'conflict'
    conflict = repository.identity_context(pid)['conflicts'][0]
    repository.decide_identity_conflict(conflict['id'], snapshot=conflict['snapshot'], decision='keep_current', reason='Checked source correction: retain the accepted DOI, reject this incoming claim.')
    proposal = repository.list_metadata_proposals(pid)[0]
    repository.resolve_metadata_proposal(proposal.id, accept=False)
    repository.apply_changes(provider='zotero', library_id='1', changes=changes)
    assert repository.get_paper(pid).paper.identity_status == 'needs_review'
    assert repository.identity_context(pid)['conflicts'][0]['decision'] == 'keep_current'
    assert repository.list_metadata_proposals(pid)[0].status == 'rejected'


def test_concurrent_correction_and_stale_version_evidence(identity):
    repository, _, _ = identity
    pid = repository.ingest(Ingestion(Paper('', 'Concurrent correction', doi='10.1234/before'), 'manual', 'one')).paper_id
    context = repository.identity_context(pid)
    def correct(suffix):
        try:
            repository.review_identity(pid, **proof(context, correction={'doi': '10.1234/' + suffix, 'arxiv_id': None, 'openalex_id': None}))
            return 'corrected'
        except WorkflowConflictError:
            return 'stale'
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(correct, ['after-a', 'after-b'])) == ['corrected', 'stale']
    preprint = repository.ingest(Ingestion(Paper('', 'Version evidence preprint', arxiv_id='2609.12345'), 'manual', 'preprint')).paper_id
    a, b = repository.identity_context(preprint), repository.identity_context(pid)
    linked = repository.link_paper_versions(preprint, pid, preprint_snapshot=a['snapshot'], published_snapshot=b['snapshot'], evidence_ids=[a['evidence'][0]['id'], b['evidence'][0]['id']], reason='Reviewed evidence connecting these independently maintained versions.')
    proposal = repository.create_metadata_proposal(pid, 'user', {'title': 'Updated publication identity context'})
    repository.resolve_metadata_proposal(proposal.id, accept=True)
    changed = repository.identity_context(preprint)['versions'][0]
    assert changed['needs_review'] and changed['snapshot'] != linked['snapshot']
    with pytest.raises(WorkflowConflictError):
        repository.retract_paper_version(linked['id'], snapshot=linked['snapshot'], reason='This old relationship snapshot must be reloaded before another decision.')


def test_separate_review_does_not_restore_removed_weak_candidate(identity):
    repository, _, _ = identity
    p = Paper('', 'A shared no-DOI bibliographic title', ('Alice',), year=2026)
    old = repository.ingest(Ingestion(p, 'manual', 'old')).paper_id
    repository.set_state(old, deleted=True)
    incoming = Ingestion(p, 'manual', 'new', restore=True)
    with pytest.raises(IdentityConflictError):
        repository.ingest(incoming)
    conflict = repository.list_identity_conflicts()['items'][0]
    assert conflict['papers'][0]['deleted']
    repository.decide_identity_conflict(conflict['id'], snapshot=conflict['snapshot'], decision='keep_separate', reason='The removed record is a different paper and must remain removed.')
    new = repository.ingest(incoming).paper_id
    assert new != old and repository.get_paper(old) is None
