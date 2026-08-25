from dataclasses import dataclass
from collections.abc import Callable, Iterable


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
    kind: str = "note"
    page_label: str | None = None
    color: str | None = None
    external_ref: ExternalReference | None = None


@dataclass(frozen=True)
class Attachment:
    id: str
    paper_id: str
    filename: str
    content_type: str | None = None
    downloadable: bool = False
    link_mode: str | None = None
    external_ref: ExternalReference | None = None


@dataclass(frozen=True)
class LiteratureAssets:
    notes: tuple[Note, ...] = ()
    attachments: tuple[Attachment, ...] = ()
    deleted_item_ids: tuple[str, ...] = ()
    library_version: str | None = None


@dataclass(frozen=True)
class PaperDetail:
    paper: Paper
    collections: tuple[Collection, ...] = ()


@dataclass(frozen=True)
class FilterOptions:
    years: tuple[int, ...] = ()
    journals: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProviderFile:
    filename: str
    content_type: str
    chunks: Iterable[bytes]
    status_code: int = 200
    content_length: str | None = None
    content_range: str | None = None
    accept_ranges: str | None = None
    close: Callable[[], None] | None = None


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
    notes: tuple[Note, ...] = ()
    attachments: tuple[Attachment, ...] = ()
    deleted_collection_ids: tuple[str, ...] = ()
    deleted_paper_ids: tuple[str, ...] = ()
    deleted_item_ids: tuple[str, ...] = ()
    library_version: str | None = None


@dataclass(frozen=True)
class LibraryState:
    provider: str
    library_id: str
    library_version: str | None
    sync_state: str
    last_synced_at: str | None = None
