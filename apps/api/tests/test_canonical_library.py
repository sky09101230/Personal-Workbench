from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import sqlite3

import pytest

from app.modules.literature.domain.canonical import IdentityConflictError, Ingestion, identifiers
from app.modules.literature.domain.models import Attachment, ChangedPaper, Collection, ExternalReference, LibraryChanges, Note, Paper
from app.modules.literature.domain.ai_models import LiteratureAIConversation, LiteratureUserNote
from app.modules.literature.infrastructure.cache.canonical import SQLiteCanonicalRepository
from app.modules.literature.infrastructure.cache.sqlite import SQLiteLiteratureRepository


def paper(key="A", **kwargs):
    return Paper(id=f"zotero:1:{key}", title="An experimental study of diffractive optics", authors=("Alice Smith",), year=2026, doi="10.1234/optics", external_ref=ExternalReference("zotero", "1", key), **kwargs)


def ingest(p, key="one", source="zotero", priority=80):
    return Ingestion(p, "zotero_import" if source == "zotero" else "radar", key, {"reason": "test evidence"}, priority, source)


@pytest.fixture
def repository(tmp_path):
    return SQLiteCanonicalRepository(f"sqlite:///{tmp_path / 'canonical.db'}")


def test_normalization_and_preprint_identity():
    p = replace(paper(), doi="https://doi.org/10.48550/ARXIV.2609.12345", arxiv_id="https://arxiv.org/pdf/2609.12345v2.pdf")
    assert identifiers(p) == {"doi": "10.48550/arxiv.2609.12345", "arxiv": "2609.12345"}
    with pytest.raises(ValueError):
        identifiers(replace(p, doi="https://evil.test/10.1234/a"))


def test_first_import_normalizes_metadata_and_preserves_identity_priority(repository):
    p = replace(paper(), doi="https://doi.org/10.1234/OPTICS")
    result = repository.ingest(ingest(p))
    assert repository.get_paper(result.paper_id).paper.doi == "10.1234/optics"
    assert repository.provenance(result.paper_id)["selected_fields"]["doi"]["priority"] == 80
    repository.ingest(ingest(paper("B"), "second"))
    assert repository.list_papers().total == 1


def test_preprint_formal_merge_and_identifier_correction_gate(repository):
    p = replace(paper(), doi="10.48550/arxiv.2609.12345", arxiv_id="2609.12345")
    first = repository.ingest(ingest(p))
    formal = replace(paper("B"), arxiv_id="2609.12345")
    assert repository.ingest(ingest(formal, "formal")).paper_id == first.paper_id
    assert repository.get_paper(first.paper_id).paper.doi == formal.doi
    with pytest.raises(IdentityConflictError, match="correction requires"):
        repository.ingest(ingest(replace(formal, arxiv_id="2609.99999"), "correction"))


def test_migration_failure_rolls_back_and_backup_recovers(tmp_path, monkeypatch):
    from app.modules.literature.infrastructure.cache.canonical import backup_database
    path = tmp_path / "failure.db"
    old = SQLiteLiteratureRepository(f"sqlite:///{path}")
    old.replace_library(provider="zotero", library_id="1", collections=(), papers=(paper(),), collection_papers={}, notes=(), attachments=(), library_version="1")
    new = SQLiteCanonicalRepository(f"sqlite:///{path}")
    original = new._migrate
    def fail(connection):
        original(connection)
        raise RuntimeError("injected migration failure")
    monkeypatch.setattr(new, "_migrate", fail)
    with pytest.raises(RuntimeError, match="injected"):
        new.run_migration()
    with sqlite3.connect(path) as c:
        assert c.execute("SELECT COUNT(*) FROM literature_papers").fetchone()[0] == 1
        assert c.execute("SELECT COUNT(*) FROM literature_documents").fetchone()[0] == 0
        assert not c.execute("SELECT 1 FROM literature_canonical_migrations WHERE version=1").fetchone()
    backup = next((tmp_path / "backups").glob("*.db"))
    restored = tmp_path / "restored.db"
    backup_database(str(backup), str(restored))
    assert SQLiteLiteratureRepository(f"sqlite:///{restored}").list_papers().total == 1
    monkeypatch.setattr(new, "_migrate", original)
    new.run_migration()
    assert new.list_papers().total == 1


def test_orphan_user_note_recovered(tmp_path):
    path = tmp_path / "orphan.db"
    old = SQLiteLiteratureRepository(f"sqlite:///{path}")
    old.save_user_note(LiteratureUserNote("orphan", "missing-paper", "Keep orphan", "manual", "before", "before"))
    new = SQLiteCanonicalRepository(f"sqlite:///{path}")
    new.run_migration()
    canonical = new.get_paper("missing-paper").paper.id
    assert new.list_user_notes(canonical)[0].content == "Keep orphan"
    assert new.migration_report()["initial"]["conflicts"] == 1


def test_removing_one_source_keeps_other_source_assets(repository):
    p, q = paper(), paper("B")
    repository.replace_library(provider="zotero", library_id="1", collections=(), papers=(p,q), collection_papers={}, notes=(), attachments=(Attachment("file-a", p.id, "a.pdf", "application/pdf", True, external_ref=ExternalReference("zotero","1","FA")), Attachment("file-b", q.id, "b.pdf", "application/pdf", True, external_ref=ExternalReference("zotero","1","FB"))), library_version="1")
    repository.apply_changes(provider="zotero", library_id="1", changes=LibraryChanges(deleted_item_ids=(p.id,), library_version="2"))
    assets = {a.filename:a.active for a in repository.list_attachments(q.id)}
    assert assets == {"a.pdf":False, "b.pdf":True}


def test_identity_idempotent_and_formal_conflict(repository):
    first = repository.ingest(ingest(paper()))
    duplicate = repository.ingest(ingest(replace(paper("B"), doi="doi:10.1234/OPTICS"), "two"))
    assert first.paper_id == duplicate.paper_id
    assert first.created and not duplicate.created
    assert repository.get_paper("zotero:1:A").paper.id == first.paper_id
    with pytest.raises(IdentityConflictError, match="formal DOI"):
        repository.ingest(ingest(replace(paper("C"), doi="10.1234/different"), "three"))
    assert repository.list_papers().total == 1


def test_title_year_author_only_requires_review(repository):
    p = replace(paper(), doi=None, external_ref=None)
    a = repository.ingest(ingest(p))
    with pytest.raises(IdentityConflictError, match="requires review") as error:
        repository.ingest(ingest(replace(p, id="other"), "two"))
    assert error.value.candidates == (a.paper_id,)
    assert repository.get_paper("other") is None
    assert repository.list_papers().total == 1
    c = repository.ingest(ingest(replace(p, id="third", year=None), "three"))
    assert c.paper_id != a.paper_id


def test_metadata_priority_and_typed_dates(repository):
    first = repository.ingest(ingest(paper(date_evidence={"issue": "2026-09"})))
    weak = replace(paper("B"), title="Weak alternate title", date_evidence={"preprint": "2026-08-05"})
    repository.ingest(ingest(weak, "radar-1", "radar", 50))
    saved = repository.get_paper(first.paper_id).paper
    assert saved.title == paper().title
    assert saved.date_evidence == {"zotero": {"issue": "2026-09"}, "radar": {"preprint": "2026-08-05"}}
    assert len(repository.provenance(first.paper_id)["metadata_evidence"]) == 2


def test_concurrent_ingest(repository):
    repository.ensure_schema()
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: repository.ingest(ingest(paper())), range(8)))
    assert len({r.paper_id for r in results}) == 1
    assert sum(r.created for r in results) == 1


def test_legacy_migration_preserves_sources_ai_and_aliases(tmp_path):
    path = tmp_path / "legacy.db"
    old = SQLiteLiteratureRepository(f"sqlite:///{path}")
    p = paper()
    collection = Collection("zotero:1:C", "Optics", external_ref=ExternalReference("zotero", "1", "C"))
    old.replace_library(provider="zotero", library_id="1", collections=(collection,), papers=(p,), collection_papers={collection.id: (p.id,)}, notes=(Note("N", p.id, "source note"),), attachments=(Attachment("F", p.id, "paper.pdf", "application/pdf", True),), library_version="7")
    old.create_conversation(LiteratureAIConversation("conversation", p.id, "before", "before"))
    old.save_user_note(LiteratureUserNote("note", p.id, "Keep this text", "manual", "before", "before"))
    new = SQLiteCanonicalRepository(f"sqlite:///{path}")
    new.run_migration()
    canonical = new.get_paper(p.id).paper.id
    assert canonical != p.id
    assert new.list_user_notes(canonical)[0].content == "Keep this text"
    assert new.get_conversation("conversation").paper_id == canonical
    assert new.list_notes(canonical)[0].content == "source note"
    assert new.list_attachments(canonical)[0].paper_id == canonical
    assert new.list_collections()[0].id != collection.id
    assert new.list_papers(collection_id=collection.id).total == 1
    report = new.migration_report()["initial"]
    assert report["backup"] and report["canonical_documents"] == 1
    assert report["foreign_key_errors"] == []
    with sqlite3.connect(path) as c:
        assert c.execute("SELECT id FROM literature_papers").fetchone()[0] == p.id
    again = SQLiteCanonicalRepository(f"sqlite:///{path}")
    assert again.migration_report()["initial"] == report


def test_sync_detaches_papers_preserves_native_state(repository):
    p = paper()
    collection = Collection("zotero:1:C", "Optics", external_ref=ExternalReference("zotero", "1", "C"))
    repository.replace_library(provider="zotero", library_id="1", collections=(collection,), papers=(p,), collection_papers={collection.id: (p.id,)}, notes=(), attachments=(), library_version="1")
    canonical = repository.get_paper(p.id).paper.id
    repository.set_state(canonical, reading_status="reading")
    repository.apply_changes(provider="zotero", library_id="1", changes=LibraryChanges(deleted_item_ids=(p.id,), deleted_collection_ids=(collection.id,), library_version="2"))
    assert repository.get_paper(canonical).paper.reading_status == "reading"
    assert repository.provenance(canonical)["references"][0]["active"] == 0
    assert len(repository.get_paper(canonical).collections) == 1
    repository.replace_library(provider="zotero", library_id="1", collections=(), papers=(), collection_papers={}, notes=(), attachments=(), library_version="3")
    assert repository.list_papers().total == 1
    repository.set_state(canonical, deleted=True)
    repository.apply_changes(provider="zotero", library_id="1", changes=LibraryChanges(papers=(ChangedPaper(p),), library_version="4"))
    assert repository.get_paper(canonical) is None


def test_conflicting_legacy_papers_preserved_and_reported(tmp_path):
    path = tmp_path / "legacy.db"
    old = SQLiteLiteratureRepository(f"sqlite:///{path}")
    p, q = paper(), replace(paper("B"), doi="10.1234/conflict")
    old.replace_library(provider="zotero", library_id="1", collections=(), papers=(p, q), collection_papers={}, notes=(), attachments=(), library_version="1")
    new = SQLiteCanonicalRepository(f"sqlite:///{path}")
    new.run_migration()
    assert new.list_papers().total == 2
    assert new.migration_report()["initial"]["conflicts"] == 1
