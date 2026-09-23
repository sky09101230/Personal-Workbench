"""Selective source import through public provider/repository ports."""
from dataclasses import asdict, dataclass
from collections.abc import Callable

from app.modules.literature.application.ports import CanonicalLibrary, LiteratureProvider
from app.modules.literature.application.errors import LiteratureError, MigrationRequiredError
from app.modules.literature.domain.canonical import IdentityConflictError, Ingestion
from app.modules.literature.domain.models import Attachment
from app.modules.literature.domain.workflow import AssetAcquisitionResult


@dataclass(frozen=True)
class ImportItemResult:
    item_key: str
    paper_id: str | None = None
    status: str = "imported"
    created: bool = False
    error: str | None = None
    reason: str | None = None
    candidates: tuple[str, ...] = ()
    asset_results: tuple[AssetAcquisitionResult, ...] = ()


@dataclass(frozen=True)
class ZoteroImportService:
    repository: CanonicalLibrary
    provider: LiteratureProvider
    acquire_asset: Callable[[Attachment], AssetAcquisitionResult] | None = None

    def list_collections(self):
        return [asdict(c) for c in self.provider.list_collections()]

    def list_importable_items(self, *, collection_id=None, limit=50, offset=0):
        page = self.provider.list_papers(collection_id=collection_id,limit=limit,offset=offset)
        items = []
        for paper in page.items:
            existing = self.repository.get_paper(paper.id)
            items.append({**asdict(paper), "import_status": "imported" if existing else "available", "canonical_id": existing.paper.id if existing else None})
        return {"items": items, "total": page.total}

    def import_selected(self, item_keys):
        if not 1 <= len(item_keys) <= 100:
            raise ValueError("Select between 1 and 100 items")
        results = []
        for identifier in dict.fromkeys(item_keys):
            changes = None
            try:
                changes = self.provider.get_import_item(identifier)
                result = self.repository.import_selected_item(changes)
                assets = []
                if self.acquire_asset:
                    source_paper_id = changes.papers[0].paper.id
                    for source in self.repository.list_attachments(result.paper_id):
                        if source.storage_kind != 'zotero' or source.source_paper_id != source_paper_id or not source.active or not source.downloadable or source.content_type != 'application/pdf':
                            continue
                        try:
                            assets.append(self.acquire_asset(source))
                        except Exception:
                            assets.append(AssetAcquisitionResult(source.id, result.paper_id, 'failed', error='acquisition_failed', filename=source.filename))
                results.append(ImportItemResult(identifier,result.paper_id,"imported" if result.created else "already_exists",result.created,asset_results=tuple(assets)))
            except MigrationRequiredError:
                raise
            except IdentityConflictError as error:
                if changes and changes.papers:
                    paper = changes.papers[0].paper
                    self.repository.record_ingestion_conflict(Ingestion(paper, 'zotero_selective', paper.id, {'method': 'selective'}, 80, 'zotero', True), error)
                results.append(ImportItemResult(identifier,status="conflict",error="identity_conflict",reason=str(error),candidates=error.candidates))
            except (LiteratureError, ValueError):
                results.append(ImportItemResult(identifier,status="failed",error="source_item_unavailable"))
        return results
