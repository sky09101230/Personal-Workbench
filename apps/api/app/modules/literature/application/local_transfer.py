"""Short-lived, source-bound browser relay; no client-selected paths or identities."""
from dataclasses import asdict, replace
from hashlib import sha256, md5
import hmac
import json
import secrets
import time
from threading import Lock
from uuid import uuid4

from app.modules.literature.application.ports import CanonicalLibrary, LiteratureFileStore
from app.modules.literature.application.errors import WorkflowConflictError
from app.modules.literature.domain.models import Attachment
from app.modules.literature.domain.workflow import AssetAcquisitionResult

MAX_BYTES = 50 * 1024 * 1024


class LocalTransferError(ValueError):
    pass


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


class LocalTransferService:
    def __init__(self, repository: CanonicalLibrary, files: LiteratureFileStore, clock=time.time):
        self.repository, self.files, self.clock = repository, files, clock
        self.secret = secrets.token_bytes(32)
        # Single-user app: serialize publication, not request-body network reads.
        self.lock = Lock()

    def source(self, paper_id, asset_id):
        paper = self.repository.get_paper(paper_id)
        if not paper or paper.paper.id != paper_id:
            raise LocalTransferError('paper_not_found')
        source = next((a for a in self.repository.list_attachments(paper_id) if a.id == asset_id), None)
        if not source or not source.active or source.storage_kind != 'zotero' or not source.downloadable or source.content_type != 'application/pdf' or not source.external_ref or source.external_ref.provider != 'zotero':
            raise LocalTransferError('source_not_eligible')
        # Resolve stored evidence; never split or construct opaque paper IDs.
        provenance = self.repository.provenance(paper_id)
        parents = set()
        for evidence in provenance['metadata_evidence']:
            metadata = evidence.get('metadata', {})
            ref = metadata.get('external_ref') or {}
            if metadata.get('id') == source.source_paper_id and ref.get('provider') == 'zotero' and ref.get('library_id') == source.external_ref.library_id:
                if any(r['provider'] == 'zotero' and r['library_id'] == ref['library_id'] and r['item_key'] == ref['item_key'] and r['active'] for r in provenance['references']):
                    parents.add(ref['item_key'])
        if len(parents) != 1:
            raise LocalTransferError('source_parent_unresolved')
        binding = {'library_id': source.external_ref.library_id, 'item_key': source.external_ref.item_key, 'parent_key': parents.pop()}
        return source, binding

    def _mac(self, source, binding, expires):
        message = digest({'source': asdict(source), 'binding': binding, 'expires': expires})
        return hmac.new(self.secret, message.encode(), sha256).hexdigest()

    def create(self, paper_id, asset_id):
        source, binding = self.source(paper_id, asset_id)
        expires = int(self.clock()) + 600
        return {'schema_version': 1, 'intent': f'{expires}.{self._mac(source, binding, expires)}', 'expires_at': expires, 'source': binding, 'max_bytes': MAX_BYTES}

    def validate(self, paper_id, asset_id, token):
        try:
            expiry, mac = token.split('.')
            expires = int(expiry)
        except (ValueError, AttributeError):
            raise LocalTransferError('invalid_intent') from None
        if expires <= self.clock() or expires > self.clock() + 601:
            raise LocalTransferError('intent_expired')
        source, binding = self.source(paper_id, asset_id)
        if not hmac.compare_digest(mac, self._mac(source, binding, expires)):
            raise LocalTransferError('source_descriptor_changed')
        return source, binding

    def receive(self, paper_id, asset_id, token, observation, data):
        with self.lock:
            source, binding = self.validate(paper_id, asset_id, token)
            try:
                return self._receive(source, binding, observation, data)
            except (LocalTransferError, ValueError) as error:
                # Connection failures never enter here; keep them out of source state.
                self.repository.record_asset_failure(source, str(error) if isinstance(error, LocalTransferError) else 'invalid_pdf')
                raise

    def _receive(self, source, binding, observation, data):
        if len(data) > MAX_BYTES:
            raise LocalTransferError('size_limit')
        before, after = observation['before'], observation['after']
        if before != after:
            raise LocalTransferError('source_changed')
        if any(before[k] != v for k, v in binding.items()):
            raise LocalTransferError('source_binding_mismatch')
        actual_sha, actual_md5 = sha256(data).hexdigest(), md5(data).hexdigest()
        if before['sha256'] != actual_sha or before['md5'] != actual_md5 or before['size_bytes'] != len(data) or source.source_md5 and source.source_md5.lower() != actual_md5:
            raise LocalTransferError('source_checksum_mismatch')
        existing = self.repository.owned_asset(source)
        if existing:
            inspection = self.files.inspect(existing)
            if inspection.state != 'verified':
                raise LocalTransferError('owned_asset_' + inspection.state)
            if existing.sha256 != actual_sha:
                raise LocalTransferError('owned_content_differs')
            return AssetAcquisitionResult(source.id, source.paper_id, 'already_owned', existing.id, actual_sha, len(data), existing.content_version, filename=source.filename)
        staged = None
        try:
            staged, _ = self.files.stage_pdf(data, source.filename)
            key = self.files.finalize_pdf(staged, actual_sha)
            observed = replace(source, paper_id=source.source_paper_id, content_version=before['version'], source_md5=actual_md5, source_channel='zotero_local_agent_client_reported', source_locator=None)
            asset = Attachment(f'asset:{uuid4()}', source.paper_id, source.filename, 'application/pdf', True, storage_kind=self.files.storage_kind, storage_key=key, sha256=actual_sha, role=source.role, content_version=before['version'])
            if self.files.inspect(asset).state != 'verified':
                raise LocalTransferError('owned_asset_unverified')
            try:
                saved = self.repository.record_owned_asset(source, asset, observed, len(data))
            except WorkflowConflictError:
                raise LocalTransferError('source_descriptor_changed') from None
            return AssetAcquisitionResult(source.id, source.paper_id, 'acquired', saved.id, actual_sha, len(data), before['version'], filename=source.filename)
        finally:
            if staged:
                self.files.discard_staged(staged)
