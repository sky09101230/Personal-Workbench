from collections.abc import Iterable, Mapping
from typing import Protocol

from app.modules.literature.domain.models import Collection, LibraryChanges, LibraryState, Paper, PaperPage


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
    ) -> PaperPage:
        ...

    def replace_library(
        self,
        *,
        provider: str,
        library_id: str,
        collections: Iterable[Collection],
        papers: Iterable[Paper],
        collection_papers: Mapping[str, Iterable[str]],
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
