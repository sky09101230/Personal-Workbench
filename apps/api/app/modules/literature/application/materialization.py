"""Bounded remote file materialization without source identity changes."""
from dataclasses import dataclass
from uuid import uuid4

from app.modules.literature.application.ports import CanonicalLibrary, LiteratureFileStore, LiteratureProvider
from app.modules.literature.application.errors import LiteratureError, MigrationRequiredError, WorkflowConflictError, ProviderAuthenticationError, ProviderNotConfiguredError, PdfSizeLimitError
from app.modules.literature.application.service import _pdf_attachment_priority
from app.modules.literature.domain.models import Attachment, MAX_SOURCE_PDF_BYTES
from app.modules.literature.domain.workflow import MaterializationResult, BatchMaterializationResult, AssetAcquisitionResult


@dataclass(frozen=True)
class PdfMaterializationService:
    repository: CanonicalLibrary
    files: LiteratureFileStore
    provider: LiteratureProvider

    def acquire_asset(self, source: Attachment, *, refresh=False):
        def failed(reason):
            return AssetAcquisitionResult(source.id, source.paper_id, 'failed', error=reason)
        if source.storage_kind != 'zotero' or source.content_type != 'application/pdf' or not source.active or not source.downloadable:
            return AssetAcquisitionResult(source.id, source.paper_id, 'skipped', error='source_not_eligible')
        staged = None
        try:
            existing = self.repository.owned_asset(source)
            if existing and not refresh:
                inspection = self.files.inspect(existing)
                if inspection.state != 'verified':
                    return failed('owned_asset_' + inspection.state)
                return AssetAcquisitionResult(source.id, source.paper_id, 'already_owned', existing.id, inspection.sha256, inspection.size_bytes, existing.content_version)
            before = self.provider.describe_attachment(source)
            if before.external_ref != source.external_ref or before.paper_id != (source.source_paper_id or source.paper_id):
                return failed('source_parent_changed')
            if not before.downloadable or before.content_type != 'application/pdf':
                return failed('source_not_eligible')
            if not before.content_version and not before.source_md5:
                return failed('source_version_unavailable')
            opened = self.provider.open_attachment(before)
            try:
                if opened.status_code != 200:
                    return failed('partial_source_response')
                if opened.content_length and int(opened.content_length) > MAX_SOURCE_PDF_BYTES:
                    return failed('size_limit')
                staged = self.files.stage_source_pdf(opened.chunks, source.filename)
                if opened.content_length and staged.size_bytes != int(opened.content_length):
                    return failed('source_length_mismatch')
            finally:
                if opened.close:
                    opened.close()
            after = self.provider.describe_attachment(source)
            if before != after:
                return failed('source_changed_during_download')
            if before.source_md5 and staged.md5 != before.source_md5.casefold():
                return failed('source_checksum_mismatch')
            key = self.files.finalize_pdf(staged.staging_key, staged.sha256)
            asset = Attachment(f'asset:{uuid4()}', source.paper_id, source.filename, 'application/pdf', True, storage_kind=staged.storage_kind, storage_key=key, sha256=staged.sha256, role=source.role, source_paper_id=source.source_paper_id, content_version=before.content_version)
            inspection = self.files.inspect(asset)
            if inspection.state != 'verified':
                return failed('owned_asset_' + inspection.state)
            saved = self.repository.record_owned_asset(source, asset, before, staged.size_bytes)
            return AssetAcquisitionResult(source.id, source.paper_id, 'acquired', saved.id, staged.sha256, staged.size_bytes, before.content_version)
        except MigrationRequiredError:
            raise
        except ProviderAuthenticationError:
            return failed('source_authentication_failed')
        except ProviderNotConfiguredError:
            return failed('source_not_configured')
        except WorkflowConflictError:
            return failed('source_descriptor_changed')
        except PdfSizeLimitError:
            return failed('size_limit')
        except ValueError:
            return failed('invalid_pdf_or_source_metadata')
        except LiteratureError:
            return failed('source_unavailable')
        except Exception:
            return failed('storage_or_transport_failure')
        finally:
            if staged:
                try:
                    self.files.discard_staged(staged.staging_key)
                except (OSError, ValueError):
                    pass

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
        result = self.acquire_asset(source)
        if result.status in {'acquired', 'already_owned'}:
            try:
                self.repository.select_primary_asset(paper_id, result.asset_id)
            except (LiteratureError, ValueError, OSError):
                return MaterializationResult(paper_id, 'pdf_failed', error='materialization_failed')
            return MaterializationResult(paper_id, 'materialized' if result.status == 'acquired' else 'already_local', result.asset_id, result.sha256)
        return MaterializationResult(paper_id, 'pdf_failed', error='materialization_failed')

    def materialize_batch(self, paper_ids, *, limit=50):
        if not 1 <= limit <= 50 or not 1 <= len(paper_ids) <= limit:
            raise ValueError("Materialization batch must contain 1 to 50 papers")
        results = tuple(self.materialize_paper(pid) for pid in dict.fromkeys(paper_ids))
        counts = {key:sum(r.status == status for r in results) for key,status in (("materialized","materialized"),("already_local","already_local"),("missing","pdf_missing"),("failed","pdf_failed"),("skipped","pdf_skipped"))}
        return BatchMaterializationResult(total=len(results),results=results,**counts)
