from collections import defaultdict
from dataclasses import dataclass

from app.modules.literature.application.ports import LiteratureCache, LiteratureProvider
from app.modules.literature.domain.models import Collection, LibraryChanges, LibraryState, Paper, PaperPage


@dataclass(frozen=True)
class SyncResult:
    collections: int
    papers: int
    library_version: str | None
    sync_mode: str
    deleted_collections: int = 0
    deleted_papers: int = 0


@dataclass(frozen=True)
class LiteratureService:
    provider: LiteratureProvider
    cache: LiteratureCache | None = None

    def status(self) -> dict[str, str | bool]:
        state = self._library_state()
        return {
            "module": "literature",
            "provider": self.provider.name,
            "provider_configured": self.provider.configured,
            "sync_state": state.sync_state if state else "not_started",
        }

    def list_collections(self) -> tuple[Collection, ...]:
        if self.cache and self._library_state():
            return self.cache.list_collections()
        return self.provider.list_collections()

    def list_papers(
        self,
        *,
        collection_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> PaperPage:
        if self.cache and self._library_state():
            return self.cache.list_papers(collection_id=collection_id, limit=limit, offset=offset)
        return self.provider.list_papers(
            collection_id=collection_id,
            limit=limit,
            offset=offset,
        )

    def sync(self, *, page_size: int = 100) -> SyncResult:
        state = self._library_state()
        if state and state.library_version:
            return self.incremental_sync(since=state.library_version)
        return self.full_sync(page_size=page_size)

    def full_sync(self, *, page_size: int = 100) -> SyncResult:
        if self.cache is None:
            raise RuntimeError("Literature cache is not configured")
        if not 1 <= page_size <= 100:
            raise ValueError("page_size must be between 1 and 100")

        provider_name = self.provider.name
        provider_library_id = str(getattr(self.provider, "library_id", ""))
        try:
            collections = self.provider.list_collections()
            papers_by_id: dict[str, Paper] = {}
            collection_papers: dict[str, set[str]] = defaultdict(set)
            library_version: str | None = None

            top_level_papers, library_version = self._read_all_pages(
                collection_id=None,
                page_size=page_size,
            )
            for paper in top_level_papers:
                papers_by_id[paper.id] = paper

            for collection in collections:
                collection_items, collection_version = self._read_all_pages(
                    collection_id=collection.id,
                    page_size=page_size,
                )
                library_version = collection_version or library_version
                for paper in collection_items:
                    papers_by_id[paper.id] = paper
                    collection_papers[collection.id].add(paper.id)

            library_id = self._library_id(collections, tuple(papers_by_id.values()))
            self.cache.replace_library(
                provider=provider_name,
                library_id=library_id,
                collections=collections,
                papers=tuple(papers_by_id.values()),
                collection_papers=collection_papers,
                library_version=library_version,
            )
            return SyncResult(
                collections=len(collections),
                papers=len(papers_by_id),
                library_version=library_version,
                sync_mode="full",
            )
        except Exception as error:
            self.cache.mark_sync_failed(
                provider=provider_name,
                library_id=provider_library_id,
                error=str(error),
            )
            raise

    def incremental_sync(self, *, since: str) -> SyncResult:
        if self.cache is None:
            raise RuntimeError("Literature cache is not configured")
        state = self._library_state()
        if state is None or not state.library_version:
            return self.full_sync()

        try:
            changes = self.provider.list_changes(since=since)
            self.cache.apply_changes(
                provider=self.provider.name,
                library_id=state.library_id,
                changes=changes,
            )
            return SyncResult(
                collections=len(changes.collections),
                papers=len(changes.papers),
                library_version=changes.library_version,
                sync_mode="incremental",
                deleted_collections=len(changes.deleted_collection_ids),
                deleted_papers=len(changes.deleted_paper_ids),
            )
        except Exception as error:
            self.cache.mark_sync_failed(
                provider=self.provider.name,
                library_id=state.library_id,
                error=str(error),
            )
            raise

    def _read_all_pages(
        self,
        *,
        collection_id: str | None,
        page_size: int,
    ) -> tuple[tuple[Paper, ...], str | None]:
        items: list[Paper] = []
        offset = 0
        library_version: str | None = None
        while True:
            page = self.list_papers(collection_id=collection_id, limit=page_size, offset=offset)
            items.extend(page.items)
            library_version = page.library_version or library_version
            offset += len(page.items)
            if not page.items or offset >= page.total:
                return tuple(items), library_version

    def _library_state(self) -> LibraryState | None:
        if self.cache is None:
            return None
        return self.cache.get_library_state(
            provider=self.provider.name,
            library_id=str(getattr(self.provider, "library_id", "")),
        )

    def _library_id(self, collections: tuple[Collection, ...], papers: tuple[Paper, ...]) -> str:
        configured_library_id = str(getattr(self.provider, "library_id", ""))
        if configured_library_id:
            return configured_library_id
        references = [
            resource.external_ref
            for resource in (*collections, *papers)
            if resource.external_ref is not None
        ]
        return references[0].library_id if references else ""
