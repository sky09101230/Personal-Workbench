import json
import sqlite3

from app.modules.literature.application.service import LiteratureService
from app.modules.literature.domain.models import (
    ChangedPaper,
    Collection,
    ExternalReference,
    LibraryChanges,
    Paper,
    PaperPage,
)
from app.modules.literature.infrastructure.cache.sqlite import SQLiteLiteratureRepository


def test_full_sync_paginates_deduplicates_and_commits_snapshot(tmp_path) -> None:
    database_path = tmp_path / "literature-sync.db"
    repository = SQLiteLiteratureRepository(f"sqlite:///{database_path.as_posix()}")
    provider = _PagedProvider()

    result = LiteratureService(provider, repository).full_sync(page_size=2)

    assert result.collections == 2
    assert result.papers == 3
    assert result.library_version == "7"
    assert provider.requests == [
        (None, 0),
        (None, 1),
        ("zotero:123:A", 0),
        ("zotero:123:B", 0),
    ]

    with sqlite3.connect(database_path) as connection:
        paper_count = connection.execute("SELECT COUNT(*) FROM literature_papers").fetchone()[0]
        link_count = connection.execute("SELECT COUNT(*) FROM literature_collection_papers").fetchone()[0]
        tag_count = connection.execute("SELECT COUNT(*) FROM literature_tags").fetchone()[0]
        state = connection.execute(
            "SELECT provider, library_id, library_version, sync_state FROM literature_library_state"
        ).fetchone()
        authors_json = connection.execute(
            "SELECT authors_json FROM literature_papers WHERE id = 'zotero:123:TOP'"
        ).fetchone()[0]

    assert paper_count == 3
    assert link_count == 3
    assert tag_count == 2
    assert state == ("zotero", "123", "7", "succeeded")
    assert json.loads(authors_json) == ["Ada Lovelace"]


def test_sync_uses_stored_version_for_incremental_merge(tmp_path) -> None:
    database_path = tmp_path / "literature-incremental.db"
    repository = SQLiteLiteratureRepository(f"sqlite:///{database_path.as_posix()}")
    provider = _PagedProvider()
    service = LiteratureService(provider, repository)
    service.full_sync(page_size=2)
    provider.changes = LibraryChanges(
        papers=(
            ChangedPaper(
                paper=_paper("TOP", "Updated top-level paper", tags=("updated",)),
                collection_ids=("zotero:123:B",),
            ),
        ),
        deleted_collection_ids=("zotero:123:A",),
        library_version="8",
    )

    result = service.sync()

    assert result.sync_mode == "incremental"
    assert result.library_version == "8"
    assert result.deleted_collections == 1
    assert result.papers == 1
    with sqlite3.connect(database_path) as connection:
        title = connection.execute(
            "SELECT title FROM literature_papers WHERE id = 'zotero:123:TOP'"
        ).fetchone()[0]
        collections = connection.execute(
            "SELECT collection_id FROM literature_collection_papers WHERE paper_id = 'zotero:123:TOP'"
        ).fetchall()
        state = connection.execute(
            "SELECT library_version, sync_state FROM literature_library_state"
        ).fetchone()

    assert title == "Updated top-level paper"
    assert collections == [("zotero:123:B",)]
    assert state == ("8", "succeeded")


def test_reads_synced_library_from_cache_without_calling_provider(tmp_path) -> None:
    database_path = tmp_path / "literature-cache-read.db"
    repository = SQLiteLiteratureRepository(f"sqlite:///{database_path.as_posix()}")
    provider = _PagedProvider()
    service = LiteratureService(provider, repository)

    service.full_sync(page_size=2)
    request_count = len(provider.requests)
    provider.fail_reads = True

    collections = service.list_collections()
    page = service.list_papers(collection_id="zotero:123:A")

    assert [collection.name for collection in collections] == ["First collection", "Second collection"]
    assert page.total == 2
    papers_by_title = {paper.title: paper for paper in page.items}
    assert papers_by_title["Top-level paper"].external_ref == _reference("TOP")
    assert papers_by_title["Collection paper"].tags == ("cache",)
    assert len(provider.requests) == request_count


def test_empty_cache_falls_back_to_provider(tmp_path) -> None:
    database_path = tmp_path / "literature-empty-cache.db"
    repository = SQLiteLiteratureRepository(f"sqlite:///{database_path.as_posix()}")
    provider = _PagedProvider()
    service = LiteratureService(provider, repository)

    assert service.list_collections()[0].name == "First collection"
    assert service.list_papers().items[0].title == "Top-level paper"
    assert provider.requests == [(None, 0)]


def test_failed_sync_keeps_previous_cache_readable(tmp_path) -> None:
    database_path = tmp_path / "literature-failed-sync.db"
    repository = SQLiteLiteratureRepository(f"sqlite:///{database_path.as_posix()}")
    provider = _PagedProvider()
    service = LiteratureService(provider, repository)
    service.full_sync(page_size=2)
    provider.fail_changes = True

    try:
        service.sync()
    except RuntimeError as error:
        assert str(error) == "provider unavailable"
    else:
        raise AssertionError("sync should fail")

    provider.fail_reads = True
    page = service.list_papers()
    state = repository.get_library_state(provider="zotero", library_id="123")

    assert {paper.title for paper in page.items} == {
        "Top-level paper",
        "Second paper",
        "Collection paper",
    }
    assert state is not None and state.sync_state == "failed"


def test_incremental_merge_is_visible_through_cache_reads(tmp_path) -> None:
    database_path = tmp_path / "literature-incremental-read.db"
    repository = SQLiteLiteratureRepository(f"sqlite:///{database_path.as_posix()}")
    provider = _PagedProvider()
    service = LiteratureService(provider, repository)
    service.full_sync(page_size=2)
    provider.changes = LibraryChanges(
        papers=(
            ChangedPaper(
                paper=_paper("TOP", "Updated top-level paper", tags=("updated",)),
                collection_ids=("zotero:123:B",),
            ),
        ),
        library_version="8",
    )
    service.sync()
    provider.fail_reads = True

    page = service.list_papers(collection_id="zotero:123:B")

    assert page.library_version == "8"
    assert {paper.title for paper in page.items} == {"Updated top-level paper", "Collection paper"}


class _PagedProvider:
    name = "zotero"
    configured = True
    library_id = "123"

    def __init__(self) -> None:
        self.requests: list[tuple[str | None, int]] = []
        self.changes = LibraryChanges()
        self.fail_reads = False
        self.fail_changes = False
        self._top = _paper("TOP", "Top-level paper", tags=("optics",))
        self._second = _paper("SECOND", "Second paper")
        self._collection_paper = _paper("COLLECTION", "Collection paper", tags=("cache",))

    def list_collections(self) -> tuple[Collection, ...]:
        if self.fail_reads:
            raise RuntimeError("provider unavailable")
        return (
            _collection("A", "First collection"),
            _collection("B", "Second collection"),
        )

    def list_papers(
        self,
        *,
        collection_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> PaperPage:
        if self.fail_reads:
            raise RuntimeError("provider unavailable")
        del limit
        self.requests.append((collection_id, offset))
        if collection_id is None:
            page = (self._top,) if offset == 0 else (self._second,)
            return PaperPage(items=page, total=2, library_version="7")
        if collection_id.endswith(":A"):
            return PaperPage(items=(self._top, self._collection_paper), total=2, library_version="7")
        return PaperPage(items=(self._collection_paper,), total=1, library_version="7")

    def list_changes(self, *, since: str) -> LibraryChanges:
        assert since == "7"
        if self.fail_changes:
            raise RuntimeError("provider unavailable")
        return self.changes


def _reference(key: str) -> ExternalReference:
    return ExternalReference(provider="zotero", library_id="123", item_key=key)


def _paper(key: str, title: str, *, tags: tuple[str, ...] = ()) -> Paper:
    return Paper(
        id=f"zotero:123:{key}",
        title=title,
        authors=("Ada Lovelace",),
        tags=tags,
        external_ref=_reference(key),
    )


def _collection(key: str, name: str) -> Collection:
    return Collection(id=f"zotero:123:{key}", name=name, external_ref=_reference(key))
