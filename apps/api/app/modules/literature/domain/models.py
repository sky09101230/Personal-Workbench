from dataclasses import dataclass


@dataclass(frozen=True)
class ExternalReference:
    provider: str
    library_id: str
    item_key: str


@dataclass(frozen=True)
class Paper:
    id: str
    title: str
    authors: tuple[str, ...] = ()
    abstract: str | None = None
    year: int | None = None
    journal: str | None = None
    doi: str | None = None
    tags: tuple[str, ...] = ()
    external_ref: ExternalReference | None = None


@dataclass(frozen=True)
class Collection:
    id: str
    name: str
    parent_id: str | None = None
    external_ref: ExternalReference | None = None


@dataclass(frozen=True)
class Note:
    id: str
    paper_id: str
    content: str


@dataclass(frozen=True)
class Attachment:
    id: str
    paper_id: str
    filename: str
    content_type: str | None = None
    downloadable: bool = False


@dataclass(frozen=True)
class PaperPage:
    items: tuple[Paper, ...]
    total: int
    library_version: str | None = None


@dataclass(frozen=True)
class ChangedPaper:
    paper: Paper
    collection_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class LibraryChanges:
    collections: tuple[Collection, ...] = ()
    papers: tuple[ChangedPaper, ...] = ()
    deleted_collection_ids: tuple[str, ...] = ()
    deleted_paper_ids: tuple[str, ...] = ()
    library_version: str | None = None


@dataclass(frozen=True)
class LibraryState:
    provider: str
    library_id: str
    library_version: str | None
    sync_state: str
    last_synced_at: str | None = None
