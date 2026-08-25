from collections.abc import Iterable, Mapping
from typing import Protocol

from app.modules.literature.domain.models import (
    Attachment,
    Collection,
    FilterOptions,
    LibraryChanges,
    LiteratureAssets,
    LibraryState,
    Note,
    Paper,
    PaperDetail,
    PaperPage,
    ProviderFile,
)


class LiteratureProvider(Protocol):
    name: str

    @property
    def configured(self) -> bool:
        """Whether the provider has enough configuration to be used."""
        ...

    def list_collections(self) -> tuple[Collection, ...]:
        ...

    def list_papers(
        self,
        *,
        collection_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> PaperPage:
        ...

    def list_changes(self, *, since: str) -> LibraryChanges:
        ...

    def list_assets(self) -> LiteratureAssets:
        ...

    def open_attachment(self, attachment: Attachment, *, range_header: str | None = None) -> ProviderFile:
        ...


class LiteratureCache(Protocol):
    def get_library_state(self, *, provider: str, library_id: str) -> LibraryState | None:
        ...

    def list_collections(self) -> tuple[Collection, ...]:
        ...

    def list_papers(
        self,
        *,
        collection_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
        query: str | None = None,
        author: str | None = None,
        year: int | None = None,
        journal: str | None = None,
        tag: str | None = None,
    ) -> PaperPage:
        ...

    def get_paper(self, paper_id: str) -> PaperDetail | None:
        ...

    def list_notes(self, paper_id: str) -> tuple[Note, ...]:
        ...

    def list_attachments(self, paper_id: str) -> tuple[Attachment, ...]:
        ...

    def list_filter_options(self) -> FilterOptions:
        ...

    def replace_library(
        self,
        *,
        provider: str,
        library_id: str,
        collections: Iterable[Collection],
        papers: Iterable[Paper],
        collection_papers: Mapping[str, Iterable[str]],
        notes: Iterable[Note],
        attachments: Iterable[Attachment],
        library_version: str | None,
    ) -> None:
        ...

    def apply_changes(
        self,
        *,
        provider: str,
        library_id: str,
        changes: LibraryChanges,
    ) -> None:
        ...

    def mark_sync_failed(self, *, provider: str, library_id: str, error: str) -> None:
        ...
