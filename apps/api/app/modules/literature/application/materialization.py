"""Bounded remote file materialization without source identity changes."""
from dataclasses import dataclass
from uuid import uuid4

from app.modules.literature.application.ports import CanonicalLibrary, LiteratureFileStore, LiteratureProvider
from app.modules.literature.application.errors import LiteratureError, MigrationRequiredError
from app.modules.literature.application.service import _pdf_attachment_priority
from app.modules.literature.domain.models import Attachment
from app.modules.literature.domain.workflow import MaterializationResult, BatchMaterializationResult


@dataclass(frozen=True)
class PdfMaterializationService:
    repository: CanonicalLibrary
    files: LiteratureFileStore
    provider: LiteratureProvider

    def materialize_paper(self, paper_id):
        detail = self.repository.get_paper(paper_id)
        if not detail:
            return MaterializationResult(paper_id, "pdf_failed", error="paper_not_found")
        paper_id = detail.paper.id
        attachments = self.repository.list_attachments(paper_id)
        local = [a for a in attachments if a.storage_kind == "local" and a.active and a.role == "primary" and a.content_type == "application/pdf"]
        for asset in local:
            try:
                opened = self.files.open(asset)
                if opened.close:
                    opened.close()
                self.repository.select_primary_asset(paper_id,asset.id)
                return MaterializationResult(paper_id,"already_local",asset.id,asset.sha256)
            except (LiteratureError, OSError):
                continue
        remote = sorted((a for a in attachments if a.storage_kind == "zotero" and a.active and a.downloadable and a.content_type == "application/pdf" and _pdf_attachment_priority(a)[0] < 2), key=_pdf_attachment_priority)
        if not remote:
            return MaterializationResult(paper_id,"pdf_missing")
        source = remote[0]
        try:
            opened = self.provider.open_attachment(source)
            data = bytearray()
            try:
                if opened.content_length and int(opened.content_length) > 50 * 1024 * 1024:
                    raise ValueError("size_limit")
                for chunk in opened.chunks:
                    if len(data) + len(chunk) > 50 * 1024 * 1024:
                        raise ValueError("size_limit")
                    data.extend(chunk)
            finally:
                if opened.close:
                    opened.close()
            key, digest = self.files.store_pdf(bytes(data), source.filename)
            asset = Attachment(f"asset:{uuid4()}",paper_id,source.filename,"application/pdf",True,storage_kind="local",storage_key=key,sha256=digest,role="primary",source_paper_id=source.source_paper_id)
            saved = self.repository.materialize_asset(paper_id,asset,source)
            return MaterializationResult(paper_id,"materialized",saved.id,digest)
        except MigrationRequiredError:
            raise
        except Exception:
            # Per-paper boundary: streaming transports can fail while iterating bytes.
            # Always report a stable error; no provider exception or credentials escape.
            return MaterializationResult(paper_id,"pdf_failed",error="materialization_failed")

    def materialize_batch(self, paper_ids, *, limit=50):
        if not 1 <= limit <= 50 or not 1 <= len(paper_ids) <= limit:
            raise ValueError("Materialization batch must contain 1 to 50 papers")
        results = tuple(self.materialize_paper(pid) for pid in dict.fromkeys(paper_ids))
        counts = {key:sum(r.status == status for r in results) for key,status in (("materialized","materialized"),("already_local","already_local"),("missing","pdf_missing"),("failed","pdf_failed"),("skipped","pdf_skipped"))}
        return BatchMaterializationResult(total=len(results),results=results,**counts)
