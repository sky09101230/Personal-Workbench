"""Transactional identity decisions; canonical IDs and research ownership never move."""

from dataclasses import asdict, replace
from hashlib import sha256
import json

from app.modules.literature.application.errors import WorkflowConflictError, WorkflowNotFoundError
from app.modules.literature.domain.canonical import IdentityConflictError, identifiers, formal_doi, normalize_identifier
from app.modules.literature.domain.workflow import metadata_snapshot
from app.modules.literature.infrastructure.cache.canonical import _id, _json, _now, _paper
from app.modules.literature.infrastructure.cache.workflows import SQLiteLiteratureWorkflowRepository


def _token(value):
    return sha256(_json(value).encode()).hexdigest()


def _reason(reason):
    if not isinstance(reason, str) or not 10 <= len(reason.strip()) <= 4000:
        raise ValueError('A review rationale of 10 to 4000 characters is required')
    return reason.strip()


class SQLiteLiteratureIdentityRepository(SQLiteLiteratureWorkflowRepository):
    def _conflict_view(self, c, row):
        payload = json.loads(row['payload_json'])
        possible = [row['legacy_id'], payload.get('paper_id'), (payload.get('paper') or {}).get('id'), *payload.get('candidates', [])]
        origin = c.execute('SELECT paper_id FROM literature_origins WHERE kind=? AND origin_key=?', (payload.get('origin'), payload.get('origin_key'))).fetchone()
        if origin:
            possible.append(origin[0])
        targets = sorted({resolved for value in possible if isinstance(value, str) and (resolved := self._resolve(c, value))})
        history = [dict(r) for r in c.execute('SELECT id,decision,reason,created_at FROM literature_conflict_reviews WHERE conflict_id=? ORDER BY rowid', (row['id'],))]
        current = [dict(r) for target in targets for r in c.execute('SELECT id,metadata_json,deleted FROM literature_documents WHERE id=?', (target,))]
        owned = [tuple(r) for target in targets for r in c.execute('SELECT kind,value,paper_id FROM literature_identifiers WHERE paper_id=? ORDER BY kind,value', (target,))]
        papers = [{'id': item['id'], 'title': json.loads(item['metadata_json']).get('title', ''), 'doi': json.loads(item['metadata_json']).get('doi'), 'deleted': bool(item['deleted'])} for item in current]
        return {'id': row['id'], 'legacy_id': row['legacy_id'], 'reason': row['reason'], 'payload': payload, 'paper_ids': targets, 'papers': papers, 'decision': history[-1]['decision'] if history else 'open', 'history': history, 'snapshot': _token([dict(row), current, owned, history])}

    def _conflicts(self, c, paper_id=None):
        records = [self._conflict_view(c, row) for row in c.execute('SELECT * FROM literature_identity_conflicts ORDER BY created_at,id')]
        return [item for item in records if paper_id is None or paper_id in item['paper_ids']]

    def list_identity_conflicts(self, *, limit=100, offset=0):
        if not 1 <= limit <= 100 or offset < 0:
            raise ValueError('Invalid pagination')
        self._require_canonical()
        with self._connect() as c:
            records = self._conflicts(c)
            return {'items': records[offset:offset + limit], 'total': len(records)}

    def _identity_context(self, c, paper_id):
        paper = self._editable_paper(c, paper_id)
        conflicts = self._conflicts(c, paper.id)
        owned = [dict(r) for r in c.execute('SELECT kind,value FROM literature_identifiers WHERE paper_id=? ORDER BY kind,value', (paper.id,))]
        pending = [r[0] for r in c.execute("SELECT id FROM literature_metadata_proposals WHERE paper_id=? AND status='pending' ORDER BY id", (paper.id,))]
        metadata = metadata_snapshot(paper)
        state = self._identity_status(c, paper)
        evidence = [{'id': r['id'], 'source': r['source'], 'observed_at': r['observed_at'], **json.loads(r['payload_json'])} for r in c.execute('SELECT * FROM literature_metadata_evidence WHERE paper_id=? ORDER BY rowid', (paper.id,))]
        versions = [self._version_view(c, row) for row in c.execute('SELECT * FROM literature_paper_versions WHERE preprint_id=? OR published_id=? ORDER BY id', (paper.id, paper.id))]
        snapshot = _token([metadata, paper.metadata_status, owned, pending, [(item['id'], item['snapshot']) for item in conflicts], state])
        return {'paper_id': paper.id, 'metadata': metadata, 'identifiers': owned, 'identity_status': state, 'evidence': evidence, 'conflicts': conflicts, 'pending_proposals': pending, 'versions': versions, 'snapshot': snapshot}

    def identity_context(self, paper_id):
        self._require_canonical()
        with self._connect() as c:
            c.execute('BEGIN')
            return self._identity_context(c, paper_id)

    @staticmethod
    def _owned_evidence(c, paper_ids, evidence_ids):
        if not isinstance(evidence_ids, (tuple, list)) or not 1 <= len(evidence_ids) <= 50 or any(not isinstance(value, str) for value in evidence_ids):
            raise ValueError('Select 1 to 50 supporting evidence records')
        owners = set()
        for evidence_id in set(evidence_ids):
            row = c.execute('SELECT paper_id FROM literature_metadata_evidence WHERE id=?', (evidence_id,)).fetchone()
            if not row or row[0] not in paper_ids:
                raise ValueError('Evidence must belong to the reviewed paper(s)')
            owners.add(row[0])
        if owners != set(paper_ids):
            raise ValueError('Select evidence from each reviewed paper')

    @staticmethod
    def _check_owners(c, paper, *, require_index=True):
        claimed = identifiers(paper)
        for kind, value in claimed.items():
            row = c.execute('SELECT paper_id FROM literature_identifiers WHERE kind=? AND value=?', (kind, value)).fetchone()
            if row and row[0] != paper.id:
                raise IdentityConflictError('Identifier belongs to another canonical paper', (row[0],))
            if require_index and not row:
                raise WorkflowConflictError('Current identifier is not accepted; explicitly correct identity first')
        return claimed

    def review_identity(self, paper_id, *, snapshot, evidence_ids, reason, correction=None):
        reason = _reason(reason)
        self._require_canonical()
        with self._connect() as c:
            c.execute('BEGIN IMMEDIATE')
            context = self._identity_context(c, paper_id)
            if snapshot != context['snapshot']:
                raise WorkflowConflictError('Identity review is stale; reload the current context')
            paper = self._editable_paper(c, context['paper_id'])
            self._owned_evidence(c, {paper.id}, evidence_ids)
            before = metadata_snapshot(paper)
            evidence_id = _id('evidence')
            if correction is None:
                claimed = self._check_owners(c, paper)
                if not claimed:
                    raise WorkflowConflictError('No scholarly identifier to confirm; retain unresolved identity')
                if paper.metadata_status == 'conflict' or any(item['decision'] in {'open', 'reopen'} for item in context['conflicts']) or context['pending_proposals']:
                    raise WorkflowConflictError('Resolve pending conflicts and proposals before identity confirmation')
                source, candidate = 'identity_confirmation', paper
            else:
                if not isinstance(correction, dict) or set(correction) != {'doi', 'arxiv_id', 'openalex_id'}:
                    raise ValueError('A complete DOI/arXiv/OpenAlex correction is required')
                clean = {}
                for field, kind in (('doi', 'doi'), ('arxiv_id', 'arxiv'), ('openalex_id', 'openalex')):
                    value = correction[field]
                    if value is not None and (not isinstance(value, str) or len(value) > 1000):
                        raise ValueError('Invalid scholarly identifier')
                    clean[field] = normalize_identifier(value, kind)
                candidate = replace(paper, **clean)
                new = self._check_owners(c, candidate, require_index=False)
                # Release only superseded current claims; observations remain in evidence.
                for field, kind in (('doi', 'doi'), ('arxiv_id', 'arxiv'), ('openalex_id', 'openalex')):
                    try:
                        old = normalize_identifier(getattr(paper, field), kind)
                    except ValueError:
                        old = getattr(paper, field)
                    if old and new.get(kind) != old:
                        c.execute('DELETE FROM literature_identifiers WHERE kind=? AND value=? AND paper_id=?', (kind, old, paper.id))
                        if kind == 'arxiv':
                            c.execute("DELETE FROM literature_identifiers WHERE kind='doi' AND value=? AND paper_id=?", ('10.48550/arxiv.' + old, paper.id))
                for kind, value in new.items():
                    c.execute('INSERT OR IGNORE INTO literature_identifiers VALUES (?,?,?)', (kind, value, paper.id))
                priorities = json.loads(c.execute('SELECT field_priority_json FROM literature_documents WHERE id=?', (paper.id,)).fetchone()[0])
                previous = dict(priorities)
                for field in clean:
                    if getattr(candidate, field) != getattr(paper, field):
                        priorities[field] = {'priority': 100, 'source': 'identity_correction', 'evidence_id': evidence_id, 'reviewed': True}
                c.execute('UPDATE literature_documents SET metadata_json=?,field_priority_json=?,updated_at=? WHERE id=?', (_json(asdict(candidate)), _json(priorities), _now(), paper.id))
                source = 'identity_correction'
            proof = {'snapshot': metadata_snapshot(candidate), 'before': before, 'after': metadata_snapshot(candidate), 'reason': reason, 'supporting_evidence_ids': sorted(set(evidence_ids)), 'previous_accepted_identifiers': context['identifiers'], 'reviewed_by': 'user'}
            if correction is not None:
                proof['previous_field_choices'] = previous
            c.execute('INSERT INTO literature_metadata_evidence VALUES (?,?,?,?,?,?)', (evidence_id, paper.id, source, 100, _json({'metadata': asdict(candidate), 'evidence': proof}), _now()))
            return self._identity_context(c, paper.id)

    def decide_identity_conflict(self, conflict_id, *, snapshot, decision, reason):
        reason = _reason(reason)
        if decision not in {'keep_current', 'keep_separate', 'quarantine', 'reopen'}:
            raise ValueError('Invalid identity conflict decision')
        self._require_canonical()
        with self._connect() as c:
            c.execute('BEGIN IMMEDIATE')
            row = c.execute('SELECT * FROM literature_identity_conflicts WHERE id=?', (conflict_id,)).fetchone()
            if not row:
                raise WorkflowNotFoundError('Conflict not found')
            context = self._conflict_view(c, row)
            if snapshot != context['snapshot']:
                raise WorkflowConflictError('Conflict changed; reload before reviewing')
            if decision == 'quarantine' and context['paper_ids']:
                raise WorkflowConflictError('Quarantine is only for unassociated source evidence')
            if decision == 'keep_current' and not context['paper_ids']:
                raise WorkflowConflictError('No canonical identity to keep; quarantine the source evidence')
            if decision == 'keep_separate' and row['reason'] not in {'Weak title/year/author evidence requires review', 'Same title has conflicting formal DOI'}:
                raise WorkflowConflictError('Separate import cannot override strong identity conflicts')
            if decision == 'keep_current':
                for paper_id in context['paper_ids']:
                    stored = c.execute('SELECT metadata_json FROM literature_documents WHERE id=?', (paper_id,)).fetchone()
                    self._check_owners(c, _paper(json.loads(stored[0])))
            c.execute('INSERT INTO literature_conflict_reviews VALUES (?,?,?,?,?,?)', (_id('identity-review'), conflict_id, decision, reason, _json({'snapshot': snapshot, 'paper_ids': context['paper_ids']}), _now()))
            for paper_id in context['paper_ids']:
                if c.execute('SELECT deleted FROM literature_documents WHERE id=?', (paper_id,)).fetchone()[0]:
                    continue  # Reviewing evidence never restores a removed Library entry.
                paper = self._editable_paper(c, paper_id)
                open_conflicts = any(item['decision'] in {'open', 'reopen'} for item in self._conflicts(c, paper_id))
                if decision == 'reopen':
                    # Reopening evidence requires review; it does not edit claimed identifiers.
                    paper = replace(paper, metadata_status='conflict')
                elif paper.metadata_status == 'conflict' and not open_conflicts:
                    try:
                        self._check_owners(c, paper)
                    except (IdentityConflictError, WorkflowConflictError, ValueError):
                        continue  # Separate-import review cannot validate an old inconsistent claim.
                    paper = replace(paper, metadata_status='complete' if paper.title and paper.authors and paper.year else 'incomplete')
                else:
                    continue
                c.execute('UPDATE literature_documents SET metadata_json=? WHERE id=?', (_json(asdict(paper)), paper.id))
            return self._conflict_view(c, row)

    @staticmethod
    def _version_view(c, row):
        result = dict(row)
        result['evidence'] = json.loads(result.pop('evidence_json'))
        linked = next(item for item in reversed(result['evidence']['history']) if item['action'] == 'linked')
        current = {}
        for side in ('preprint', 'published'):
            paper = c.execute('SELECT metadata_json,deleted FROM literature_documents WHERE id=?', (row[side + '_id'],)).fetchone()
            current[side] = metadata_snapshot(_paper(json.loads(paper[0]))) if paper and not paper[1] else None
        result['needs_review'] = row['status'] == 'active' and any(current[side] != linked[side + '_snapshot'] for side in current)
        result['current_metadata'] = current
        return {**result, 'snapshot': _token(result)}

    def link_paper_versions(self, preprint_id, published_id, *, preprint_snapshot, published_snapshot, evidence_ids, reason):
        reason = _reason(reason)
        self._require_canonical()
        with self._connect() as c:
            c.execute('BEGIN IMMEDIATE')
            left, right = self._identity_context(c, preprint_id), self._identity_context(c, published_id)
            if left['snapshot'] != preprint_snapshot or right['snapshot'] != published_snapshot:
                raise WorkflowConflictError('Version evidence is stale; reload both papers')
            a, b = self._editable_paper(c, left['paper_id']), self._editable_paper(c, right['paper_id'])
            if a.id == b.id or not a.arxiv_id or formal_doi(a.doi) or not formal_doi(b.doi):
                raise ValueError('Choose a distinct preprint with arXiv identity and a published paper with a formal DOI')
            self._check_owners(c, a)
            self._check_owners(c, b)
            if a.metadata_status == 'conflict' or b.metadata_status == 'conflict':
                raise WorkflowConflictError('Resolve canonical conflicts before linking versions')
            self._owned_evidence(c, {a.id, b.id}, evidence_ids)
            row = c.execute('SELECT * FROM literature_paper_versions WHERE preprint_id=? AND published_id=?', (a.id, b.id)).fetchone()
            if row and row['status'] == 'active':
                return self._version_view(c, row)
            evidence = json.loads(row['evidence_json']) if row else {'history': []}
            evidence['history'].append({'action': 'linked', 'reason': reason, 'supporting_evidence_ids': sorted(set(evidence_ids)), 'preprint_snapshot': metadata_snapshot(a), 'published_snapshot': metadata_snapshot(b), 'reviewed_at': _now()})
            version_id = row['id'] if row else _id('version')
            c.execute("INSERT INTO literature_paper_versions VALUES (?,?,?,'active',?,?) ON CONFLICT(id) DO UPDATE SET status='active',evidence_json=excluded.evidence_json,updated_at=excluded.updated_at", (version_id, a.id, b.id, _json(evidence), _now()))
            return self._version_view(c, c.execute('SELECT * FROM literature_paper_versions WHERE id=?', (version_id,)).fetchone())

    def retract_paper_version(self, version_id, *, snapshot, reason):
        reason = _reason(reason)
        self._require_canonical()
        with self._connect() as c:
            c.execute('BEGIN IMMEDIATE')
            row = c.execute('SELECT * FROM literature_paper_versions WHERE id=?', (version_id,)).fetchone()
            if not row:
                raise WorkflowNotFoundError('Version relationship not found')
            current = self._version_view(c, row)
            if snapshot != current['snapshot']:
                raise WorkflowConflictError('Version relationship changed; reload before retracting')
            if row['status'] == 'active':
                evidence = current['evidence']
                evidence['history'].append({'action': 'retracted', 'reason': reason, 'reviewed_at': _now()})
                c.execute("UPDATE literature_paper_versions SET status='retracted',evidence_json=?,updated_at=? WHERE id=?", (_json(evidence), _now(), version_id))
            return self._version_view(c, c.execute('SELECT * FROM literature_paper_versions WHERE id=?', (version_id,)).fetchone())
