"""Application orchestration; transactions and file access are provided by ports."""
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from uuid import uuid4

from app.modules.literature.application.ports import LiteratureWorkflowRepository, LiteratureFileStore
from app.modules.literature.application.errors import WorkflowNotFoundError, WorkflowConflictError
from app.modules.literature.domain.workflow import ExtractedMetadata, UploadItem


@dataclass(frozen=True)
class UploadWorkflowService:
    repository: LiteratureWorkflowRepository
    files: LiteratureFileStore
    extract: Callable[[bytes], ExtractedMetadata]

    def create_batch(self):
        return self.repository.create_upload_batch()

    def get_batch(self, batch_id):
        return self.repository.get_upload_batch(batch_id)

    def stage_file(self, batch_id, filename, data):
        filename = filename.replace("\\", "/").rsplit("/", 1)[-1][:240] or "paper.pdf"
        staged = None
        def create():
            nonlocal staged
            staged, digest = self.files.stage_pdf(data, filename)
            extraction = self.extract(data)
            evidence = {key: asdict(value) for key in ("title", "authors", "year", "doi", "arxiv_id", "journal", "abstract") if (value := getattr(extraction, key, None))}
            candidate = {key: value["value"] for key,value in evidence.items()}
            now = datetime.now(timezone.utc).isoformat()
            return UploadItem(f"item:{uuid4()}", batch_id, filename, staged, digest, "needs_review" if not candidate.get("title") else "ready", evidence, candidate, extraction.warnings, created_at=now, updated_at=now)
        try:
            return self.repository.stage_upload(batch_id, create)
        except Exception:
            if staged:
                self.files.discard_staged(staged)
            raise

    def update_item_metadata(self, batch_id, item_id, metadata):
        return self.repository.update_upload(batch_id, item_id, metadata)

    def confirm_batch(self, batch_id):
        batch = self.get_batch(batch_id)
        if not batch:
            raise WorkflowNotFoundError("Batch not found")
        if batch.status == "cancelled":
            raise WorkflowConflictError("Batch is cancelled")
        if not batch.items:
            raise WorkflowConflictError("Batch is empty")
        results = []
        for item in batch.items:
            result = self.repository.confirm_upload(batch_id, item.id, lambda key,digest: self.files.finalize_pdf(key,digest,keep_staging=True), storage_kind=self.files.storage_kind)
            results.append(result)
            if result["status"] in {"confirmed", "already_confirmed"}:
                try:
                    self.files.discard_staged(item.staging_key)
                except OSError:
                    pass  # Confirmed originals are durable; explicit cleanup retries staging removal.
        return results

    def cancel_batch(self, batch_id):
        batch = self.repository.cancel_upload(batch_id)
        self._discard_cancelled(batch)
        return batch

    def cancel_item(self, batch_id, item_id):
        batch = self.repository.cancel_upload(batch_id, item_id)
        self._discard_cancelled(batch)
        return next(item for item in batch.items if item.id == item_id)

    def _discard_cancelled(self, batch):
        for item in batch.items:
            if item.status == "cancelled":
                try:
                    self.files.discard_staged(item.staging_key)
                except OSError:
                    pass

    def cleanup(self, max_age_seconds=3600):
        return {"removed": self.repository.cleanup_uploads(lambda protected: self.files.cleanup_staging(max_age_seconds, protected=protected))}
