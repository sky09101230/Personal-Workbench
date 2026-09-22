"""Transactional workflow persistence; only Literature tables are accessed."""

from dataclasses import asdict, replace
import json

from app.modules.literature.application.errors import WorkflowConflictError, WorkflowNotFoundError
from app.modules.literature.domain.canonical import Ingestion, IdentityConflictError, compatible, identifiers, formal_doi
from app.modules.literature.domain.models import Attachment, Paper
from app.modules.literature.domain.workflow import UploadBatch, UploadItem, MetadataProposal, METADATA_FIELDS, metadata_patch
from app.modules.literature.infrastructure.cache.canonical import SQLiteCanonicalRepository, _id, _now, _json, _paper, _attachment


def _item(row):
    return UploadItem(row['id'], row['batch_id'], row['filename'], row['staging_key'], row['sha256'], row['status'], json.loads(row['extracted_json']), json.loads(row['candidate_json']), tuple(json.loads(row['warnings_json'])), row['target_paper_id'], row['error'], row['created_at'], row['updated_at'])


def _proposal(row):
    return MetadataProposal(row['id'], row['paper_id'], row['source'], row['status'], json.loads(row['current_json']), json.loads(row['proposed_json']), tuple(json.loads(row['fields_changed_json'])), row['created_at'], row['resolved_at'], row['resolved_by'])


def _metadata(paper):
    data = asdict(paper)
    return {field: list(data[field]) if field == 'authors' else data[field] for field in METADATA_FIELDS}


class SQLiteLiteratureWorkflowRepository(SQLiteCanonicalRepository):
    def create_upload_batch(self):
        self._require_canonical()
        batch = UploadBatch(_id('batch'), created_at=_now())
        with self._connect() as c:
            c.execute("INSERT INTO literature_upload_batches VALUES (?, 'staging', ?, NULL, NULL)", (batch.id, batch.created_at))
        return batch

    @staticmethod
    def _batch(c, batch_id):
        row = c.execute("SELECT * FROM literature_upload_batches WHERE id=?", (batch_id,)).fetchone()
        if not row:
            return None
        items = tuple(_item(r) for r in c.execute("SELECT * FROM literature_upload_items WHERE batch_id=? ORDER BY created_at,id", (batch_id,)))
        return UploadBatch(row['id'], row['status'], items, row['created_at'], row['confirmed_at'], row['cancelled_at'])

    def get_upload_batch(self, batch_id):
        self._require_canonical()
        with self._connect() as c:
            return self._batch(c, batch_id)

    def _editable(self, c, batch_id, item_id=None):
        batch = self._batch(c, batch_id)
        if not batch:
            raise WorkflowNotFoundError('Batch not found')
        if batch.status in {'confirmed', 'cancelled'}:
            raise WorkflowConflictError('Batch is already closed')
        item = next((i for i in batch.items if i.id == item_id), None) if item_id else None
        if item_id and not item:
            raise WorkflowNotFoundError('Item not found')
        if item and item.status in {'confirmed', 'cancelled'}:
            raise WorkflowConflictError('Item is already closed')
        return batch, item

    def stage_upload(self, batch_id, create):
        self._require_canonical()
        with self._connect() as c:
            c.execute('BEGIN IMMEDIATE')
            batch, _ = self._editable(c, batch_id)
            if len(batch.items) >= 50:
                raise WorkflowConflictError('Batch limit is 50 files')
            item = create()
            c.execute('INSERT INTO literature_upload_items VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)', (item.id, batch_id, item.filename, item.staging_key, item.sha256, item.status, _json(item.extracted_metadata), _json(item.candidate_metadata), _json(item.warnings), None, None, item.created_at, item.updated_at))
        return item

    def update_upload(self, batch_id, item_id, metadata):
        clean = metadata_patch(metadata)
        if not clean:
            raise ValueError('Empty metadata update')
        self._require_canonical()
        with self._connect() as c:
            c.execute('BEGIN IMMEDIATE')
            _, item = self._editable(c, batch_id, item_id)
            candidate = {**item.candidate_metadata, **clean}
            c.execute("UPDATE literature_upload_items SET candidate_json=?,status='ready',error=NULL,updated_at=? WHERE id=?", (_json(candidate), _now(), item_id))
            c.execute("UPDATE literature_upload_batches SET status='reviewing' WHERE id=?", (batch_id,))
            return _item(c.execute('SELECT * FROM literature_upload_items WHERE id=?', (item_id,)).fetchone())

    def confirm_upload(self, batch_id, item_id, finalize):
        self._require_canonical()
        with self._connect() as c:
            c.execute('BEGIN IMMEDIATE')
            batch = self._batch(c, batch_id)
            if not batch:
                raise WorkflowNotFoundError('Batch not found')
            item = next((i for i in batch.items if i.id == item_id), None)
            if not item:
                raise WorkflowNotFoundError('Item not found')
            if item.status == 'confirmed':
                return {'item_id': item.id, 'status': 'already_confirmed', 'paper_id': item.target_paper_id}
            if item.status == 'cancelled' or batch.status == 'cancelled':
                return {'item_id': item.id, 'status': 'cancelled', 'paper_id': None}
            c.execute('SAVEPOINT confirm_item')
            try:
                metadata = metadata_patch(item.candidate_metadata)
                if not metadata.get('title'):
                    raise ValueError('Review and supply a title before confirmation')
                paper = Paper('', **metadata)
                storage_key = finalize(item.staging_key, item.sha256)
                asset = Attachment(_id('asset'), '', item.filename, 'application/pdf', True, storage_kind='local', storage_key=storage_key, sha256=item.sha256)
                incoming = Ingestion(paper, 'manual_pdf', 'new:primary:' + item.sha256, {'batch_id': batch_id, 'item_id':item.id, 'extracted': item.extracted_metadata, 'reviewed': metadata, 'sha256': item.sha256}, 90, 'upload_review', True)
                result, saved_asset = self._ingest_asset(c, incoming, asset)
                if result.created:
                    c.execute("UPDATE literature_documents SET reading_status='saved' WHERE id=?", (result.paper_id,))
                c.execute("UPDATE literature_upload_items SET status='confirmed',target_paper_id=?,error=NULL,updated_at=? WHERE id=?", (result.paper_id, _now(), item.id))
                response = {'item_id': item.id, 'status': 'confirmed', 'paper_id': result.paper_id, 'asset_id': saved_asset.id, 'created': result.created}
                c.execute('RELEASE confirm_item')
            except (IdentityConflictError, ValueError, OSError) as error:
                c.execute('ROLLBACK TO confirm_item')
                c.execute('RELEASE confirm_item')
                status = 'conflict' if isinstance(error, IdentityConflictError) else 'needs_review' if isinstance(error, ValueError) else 'failed'
                reason = str(error) if isinstance(error, (ValueError, IdentityConflictError)) else 'File operation failed; retry is safe'
                c.execute('UPDATE literature_upload_items SET status=?,error=?,updated_at=? WHERE id=?', (status, reason, _now(), item.id))
                response = {'item_id': item.id, 'status': status, 'error': reason}
                if isinstance(error, IdentityConflictError):
                    response['candidates'] = list(error.candidates)
                    self._conflict(c, item.id, reason, {'batch_id': batch_id, 'item_id': item.id, 'candidates': list(error.candidates), 'metadata': item.candidate_metadata})
            pending = c.execute("SELECT 1 FROM literature_upload_items WHERE batch_id=? AND status NOT IN ('confirmed','cancelled')", (batch_id,)).fetchone()
            c.execute('UPDATE literature_upload_batches SET status=?,confirmed_at=? WHERE id=?', ('reviewing' if pending else 'confirmed', None if pending else _now(), batch_id))
            return response

    def cancel_upload(self, batch_id, item_id=None):
        self._require_canonical()
        with self._connect() as c:
            c.execute('BEGIN IMMEDIATE')
            batch = self._batch(c, batch_id)
            if not batch:
                raise WorkflowNotFoundError('Batch not found')
            if batch.status == 'cancelled':
                return batch
            self._editable(c, batch_id, item_id)
            if item_id:
                c.execute("UPDATE literature_upload_items SET status='cancelled',updated_at=? WHERE id=?", (_now(), item_id))
            else:
                c.execute("UPDATE literature_upload_batches SET status='cancelled',cancelled_at=? WHERE id=?", (_now(), batch_id))
                c.execute("UPDATE literature_upload_items SET status='cancelled',updated_at=? WHERE batch_id=? AND status!='confirmed'", (_now(), batch_id))
            return self._batch(c, batch_id)

    def cleanup_uploads(self, cleanup):
        self._require_canonical()
        with self._connect() as c:
            c.execute('BEGIN IMMEDIATE')
            protected = {r[0] for r in c.execute("SELECT staging_key FROM literature_upload_items WHERE status NOT IN ('confirmed','cancelled')")}
            return cleanup(protected)

    def create_metadata_proposal(self, paper_id, source, metadata):
        clean = metadata_patch(metadata)
        if not isinstance(source, str) or not source.strip() or len(source) > 100:
            raise ValueError('Invalid proposal source')
        self._require_canonical()
        with self._connect() as c:
            c.execute('BEGIN IMMEDIATE')
            paper = self._editable_paper(c, paper_id)
            candidate = replace(paper, **clean)
            self._validate_identity(c, paper, candidate)
            current = _metadata(paper)
            changed = tuple(k for k,v in clean.items() if current[k] != v)
            if not changed:
                raise ValueError('No metadata changes proposed')
            proposal = MetadataProposal(_id('proposal'), paper.id, source.strip(), current_metadata=current, proposed_metadata=clean, fields_changed=changed, created_at=_now())
            c.execute('INSERT INTO literature_metadata_proposals VALUES (?,?,?,?,?,?,?,?,?,?)', (proposal.id, paper.id, proposal.source, 'pending', _json(current), _json(clean), _json(changed), proposal.created_at, None, None))
            return proposal

    def _editable_paper(self, c, paper_id):
        canonical = self._resolve(c, paper_id)
        row = c.execute('SELECT metadata_json FROM literature_documents WHERE id=? AND deleted=0', (canonical,)).fetchone()
        if not row:
            raise WorkflowNotFoundError('Paper not found')
        return _paper(json.loads(row[0]))

    @staticmethod
    def _validate_identity(c, paper, candidate):
        compatible(paper, candidate)
        old, new = identifiers(paper), identifiers(candidate)
        if formal_doi(old.get('doi')) and formal_doi(old.get('doi')) != formal_doi(new.get('doi')):
            raise IdentityConflictError('A formal DOI cannot be downgraded to a preprint identifier', (paper.id,))
        if set(old) - set(new):
            raise IdentityConflictError('Identifier removal requires a dedicated correction workflow', (paper.id,))
        for kind, value in new.items():
            owner = c.execute('SELECT paper_id FROM literature_identifiers WHERE kind=? AND value=?', (kind, value)).fetchone()
            if owner and owner[0] != paper.id:
                raise IdentityConflictError('Identifier belongs to another canonical paper', (owner[0],))

    def get_metadata_proposal(self, proposal_id):
        self._require_canonical()
        with self._connect() as c:
            row = c.execute('SELECT * FROM literature_metadata_proposals WHERE id=?', (proposal_id,)).fetchone()
            return _proposal(row) if row else None

    def list_metadata_proposals(self, paper_id):
        self._require_canonical()
        with self._connect() as c:
            paper = self._editable_paper(c, paper_id)
            return tuple(_proposal(r) for r in c.execute('SELECT * FROM literature_metadata_proposals WHERE paper_id=? ORDER BY created_at DESC,id', (paper.id,)))

    def resolve_metadata_proposal(self, proposal_id, *, accept, edits=None):
        clean_edits = metadata_patch(edits) if edits is not None else {}
        self._require_canonical()
        with self._connect() as c:
            c.execute('BEGIN IMMEDIATE')
            row = c.execute('SELECT * FROM literature_metadata_proposals WHERE id=?', (proposal_id,)).fetchone()
            if not row:
                raise WorkflowNotFoundError('Proposal not found')
            proposal = _proposal(row)
            if proposal.status != 'pending':
                raise WorkflowConflictError('Proposal already resolved')
            paper = self._editable_paper(c, proposal.paper_id)
            proposed = {**proposal.proposed_metadata, **clean_edits}
            changed = tuple(k for k,v in proposed.items() if _metadata(paper)[k] != v)
            if accept:
                if _metadata(paper) != proposal.current_metadata:
                    raise WorkflowConflictError('Proposal is stale; create a new proposal')
                candidate = replace(paper, **metadata_patch(proposed))
                self._validate_identity(c, paper, candidate)
                priority = 100 if edits is not None else 95
                priorities = json.loads(c.execute('SELECT field_priority_json FROM literature_documents WHERE id=?', (paper.id,)).fetchone()[0])
                for key in changed:
                    priorities[key] = {'priority': priority, 'source': 'review:' + proposal.source}
                for kind,value in identifiers(candidate).items():
                    c.execute('INSERT OR IGNORE INTO literature_identifiers VALUES (?,?,?)', (kind,value,paper.id))
                candidate = replace(candidate, metadata_status='complete' if candidate.title and candidate.authors and candidate.year else 'incomplete')
                c.execute('UPDATE literature_documents SET metadata_json=?,field_priority_json=?,updated_at=? WHERE id=?', (_json(asdict(candidate)), _json(priorities), _now(), paper.id))
                evidence = {'metadata': asdict(candidate), 'evidence': {'proposal_id': proposal_id, 'before': proposal.current_metadata, 'after': _metadata(candidate), 'edits': clean_edits}}
                c.execute('INSERT INTO literature_metadata_evidence VALUES (?,?,?,?,?,?)', (_id('evidence'),paper.id,'review:'+proposal.source,priority,_json(evidence),_now()))
            c.execute('UPDATE literature_metadata_proposals SET status=?,proposed_json=?,fields_changed_json=?,resolved_at=?,resolved_by=? WHERE id=?', ('accepted' if accept else 'rejected', _json(proposed), _json(changed), _now(), 'user', proposal_id))
            return _proposal(c.execute('SELECT * FROM literature_metadata_proposals WHERE id=?', (proposal_id,)).fetchone())

    def import_selected_item(self, changes):
        self._require_canonical()
        if len(changes.papers) != 1:
            raise ValueError('One selected paper is required')
        changed = changes.papers[0]
        with self._connect() as c:
            c.execute('BEGIN IMMEDIATE')
            is_new_source = self._resolve(c, changed.paper.id) is None
            result = self._ingest(c, Ingestion(changed.paper, 'zotero_selective', changed.paper.id, {'method': 'selective'}, 80, 'zotero', True))
            fresh_collections = self._sync_collections(c, changes.collections)
            for collection_id in changed.collection_ids:
                self._membership(c, collection_id, changed.paper.id, initial=is_new_source or collection_id in fresh_collections)
            for note in changes.notes:
                self._note(c, note)
            for asset in changes.attachments:
                self._asset(c, asset)
            if result.created:
                c.execute("UPDATE literature_documents SET reading_status='saved' WHERE id=?", (result.paper_id,))
            return result

    def materialize_asset(self, paper_id, asset, source_asset):
        self._require_canonical()
        with self._connect() as c:
            c.execute('BEGIN IMMEDIATE')
            paper = self._editable_paper(c, paper_id)
            current = c.execute('SELECT payload_json FROM literature_assets WHERE id=? AND paper_id=? AND active=1', (source_asset.id,paper.id)).fetchone()
            if not current or _attachment(json.loads(current[0])).content_version != source_asset.content_version:
                raise WorkflowConflictError('Source attachment changed; retry materialization')
            result, saved = self._ingest_asset(c, Ingestion(paper,'zotero_materialization',source_asset.id+':'+str(source_asset.content_version or ''),{'source_asset':source_asset.id,'version':source_asset.content_version},0,'zotero_file'), asset)
            return saved

    def select_primary_asset(self, paper_id, asset_id):
        self._require_canonical()
        with self._connect() as c:
            c.execute('BEGIN IMMEDIATE')
            paper = self._editable_paper(c, paper_id)
            row = c.execute('SELECT payload_json FROM literature_assets WHERE id=? AND paper_id=? AND active=1', (asset_id,paper.id)).fetchone()
            if not row:
                raise WorkflowConflictError('Asset is no longer available')
            asset = _attachment(json.loads(row[0]))
            if not asset.downloadable or asset.content_type != 'application/pdf' or asset.role != 'primary':
                raise WorkflowConflictError('Asset cannot be selected as primary')
            c.execute('UPDATE literature_documents SET metadata_json=? WHERE id=?', (_json(asdict(replace(paper,primary_asset_id=asset_id))),paper.id))
