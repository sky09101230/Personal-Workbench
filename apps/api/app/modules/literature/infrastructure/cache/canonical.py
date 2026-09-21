"""Additive canonical Library. Legacy source tables remain a recovery snapshot."""

from contextlib import closing, contextmanager
from dataclasses import asdict, replace
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from uuid import NAMESPACE_URL, uuid4, uuid5

from app.modules.literature.domain.canonical import (
    IdentityConflictError, Ingestion, IngestResult, compatible, corroborated_title,
    formal_doi, identifiers, title_key,
)
from app.modules.literature.domain.models import (
    Attachment, Collection, ExternalReference, FilterOptions, LibraryChanges,
    Note, Paper, PaperDetail, PaperPage,
)
from app.modules.literature.infrastructure.cache.sqlite import SQLiteLiteratureRepository, SchemaVersion


_SCHEMA = (
    "CREATE TABLE literature_canonical_migrations (version INTEGER PRIMARY KEY, report_json TEXT NOT NULL)",
    "CREATE TABLE literature_documents (id TEXT PRIMARY KEY, metadata_json TEXT NOT NULL, field_priority_json TEXT NOT NULL, reading_status TEXT NOT NULL DEFAULT 'inbox', deleted INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)",
    "CREATE TABLE literature_paper_aliases (alias TEXT PRIMARY KEY, paper_id TEXT NOT NULL REFERENCES literature_documents(id), reason TEXT NOT NULL)",
    "CREATE TABLE literature_identifiers (kind TEXT NOT NULL, value TEXT NOT NULL, paper_id TEXT NOT NULL REFERENCES literature_documents(id), PRIMARY KEY(kind,value))",
    "CREATE TABLE literature_source_references (provider TEXT NOT NULL, library_id TEXT NOT NULL, item_key TEXT NOT NULL, paper_id TEXT NOT NULL REFERENCES literature_documents(id), active INTEGER NOT NULL DEFAULT 1, PRIMARY KEY(provider,library_id,item_key))",
    "CREATE TABLE literature_origins (kind TEXT NOT NULL, origin_key TEXT NOT NULL, paper_id TEXT NOT NULL REFERENCES literature_documents(id), evidence_json TEXT NOT NULL, discovered_at TEXT NOT NULL, PRIMARY KEY(kind,origin_key))",
    "CREATE TABLE literature_metadata_evidence (id TEXT PRIMARY KEY, paper_id TEXT NOT NULL REFERENCES literature_documents(id), source TEXT NOT NULL, priority INTEGER NOT NULL, payload_json TEXT NOT NULL, observed_at TEXT NOT NULL)",
    "CREATE TABLE literature_identity_conflicts (id TEXT PRIMARY KEY, legacy_id TEXT, reason TEXT NOT NULL, payload_json TEXT NOT NULL, created_at TEXT NOT NULL)",
    "CREATE TABLE literature_assets (id TEXT PRIMARY KEY, paper_id TEXT NOT NULL REFERENCES literature_documents(id), payload_json TEXT NOT NULL, source_id TEXT UNIQUE, active INTEGER NOT NULL DEFAULT 1)",
    "CREATE TABLE literature_source_notes (id TEXT PRIMARY KEY, paper_id TEXT NOT NULL REFERENCES literature_documents(id), payload_json TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1)",
    "CREATE TABLE literature_native_collections (id TEXT PRIMARY KEY, name TEXT NOT NULL, parent_id TEXT REFERENCES literature_native_collections(id) DEFERRABLE INITIALLY DEFERRED)",
    "CREATE TABLE literature_native_memberships (collection_id TEXT NOT NULL REFERENCES literature_native_collections(id), paper_id TEXT NOT NULL REFERENCES literature_documents(id), PRIMARY KEY(collection_id,paper_id))",
    "CREATE TABLE literature_source_collections (source_id TEXT PRIMARY KEY, collection_id TEXT NOT NULL REFERENCES literature_native_collections(id), payload_json TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1)",
    "CREATE TABLE literature_source_memberships (source_collection_id TEXT NOT NULL, source_paper_id TEXT NOT NULL, PRIMARY KEY(source_collection_id,source_paper_id))",
    "CREATE TABLE literature_legacy_ai_snapshot (table_name TEXT NOT NULL, row_key TEXT NOT NULL, payload_json TEXT NOT NULL, PRIMARY KEY(table_name,row_key))",
    "CREATE INDEX literature_assets_paper_idx ON literature_assets(paper_id)",
    "CREATE INDEX literature_origins_paper_idx ON literature_origins(paper_id)",
    "CREATE INDEX literature_evidence_paper_idx ON literature_metadata_evidence(paper_id)",
)
_AI_TABLES = ("literature_ai_analyses", "literature_ai_conversations", "literature_ai_messages", "literature_ai_paper_text", "literature_user_notes")


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _now():
    return datetime.now(timezone.utc).isoformat()


def _id(kind, source=None):
    return f"{kind}:{uuid5(NAMESPACE_URL, source) if source else uuid4()}"


def _paper(payload):
    values = dict(payload)
    for key in ("authors", "tags", "sources"):
        values[key] = tuple(values.get(key, ()))
    ref = values.get("external_ref")
    values["external_ref"] = ExternalReference(**ref) if ref else None
    return Paper(**values)


def _attachment(payload):
    values = dict(payload)
    ref = values.get("external_ref")
    values["external_ref"] = ExternalReference(**ref) if ref else None
    return Attachment(**values)


def backup_database(path: str, destination: str | None = None) -> str:
    source = Path(path).resolve()
    target = Path(destination) if destination else source.parent / "backups" / f"literature-v2-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:8]}.db"
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise ValueError("Backup destination already exists")
    with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as src, closing(sqlite3.connect(target)) as dst:
        src.backup(dst)
        if dst.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("Backup integrity check failed")
    return str(target.resolve())


class SQLiteCanonicalRepository(SQLiteLiteratureRepository):
    def __init__(self, database_url: str) -> None:
        super().__init__(database_url)
        self._canonical_ready = False

    @contextmanager
    def _connect(self):
        with closing(sqlite3.connect(self._database_path, timeout=30)) as connection, connection:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            yield connection

    def ensure_schema(self) -> SchemaVersion:
        if self._canonical_ready:
            return SchemaVersion(1)
        backup = None
        path = Path(self._database_path)
        if path.exists():
            with self._connect() as c:
                exists = c.execute("SELECT 1 FROM sqlite_master WHERE name='literature_canonical_migrations'").fetchone()
                if exists and c.execute("SELECT 1 FROM literature_canonical_migrations WHERE version=1").fetchone():
                    self._canonical_ready = True
                    return SchemaVersion(1)
            backup = backup_database(self._database_path)
        super().ensure_schema()
        with self._connect() as c:
            c.execute("BEGIN IMMEDIATE")
            # Another repository instance may have completed migration while backup ran.
            if c.execute("SELECT 1 FROM sqlite_master WHERE name='literature_canonical_migrations'").fetchone():
                if not c.execute("SELECT 1 FROM literature_canonical_migrations WHERE version=1").fetchone():
                    raise RuntimeError("Incomplete canonical migration ledger; restore backup before retry")
                self._canonical_ready = True
                return SchemaVersion(1)
            for statement in _SCHEMA:
                c.execute(statement)
            self._migrate(c)
            report = self._report(c)
            report["backup"] = backup
            c.execute("INSERT INTO literature_canonical_migrations VALUES (1, ?)", (_json(report),))
        self._canonical_ready = True
        return SchemaVersion(1)

    def _migrate(self, c):
        for row in c.execute("SELECT * FROM literature_papers ORDER BY id").fetchall():
            ref = c.execute("SELECT provider,library_id,item_key FROM literature_external_references WHERE resource_type='paper' AND resource_id=? ORDER BY provider LIMIT 1", (row["id"],)).fetchone()
            paper = Paper(id=row["id"], title=row["title"], authors=tuple(json.loads(row["authors_json"])), abstract=row["abstract"], year=row["year"], journal=row["journal"], doi=row["doi"], tags=tuple(r[0] for r in c.execute("SELECT tag FROM literature_tags WHERE paper_id=?", (row["id"],))), external_ref=ExternalReference(*ref) if ref else None)
            self._preserved_ingest(c, Ingestion(paper, "zotero_import", paper.id, {"legacy_id": paper.id}, 80, "zotero"))
        self._sync_collections(c, tuple(Collection(r["id"], r["name"], r["parent_id"], self._legacy_ref(c, "collection", r["id"])) for r in c.execute("SELECT * FROM literature_collections")))
        for row in c.execute("SELECT * FROM literature_collection_papers"):
            self._membership(c, row["collection_id"], row["paper_id"], initial=True)
        for row in c.execute("SELECT * FROM literature_notes").fetchall():
            ref = self._legacy_ref(c, "note", row["id"])
            self._note(c, Note(row["id"], row["paper_id"], row["content"], row["kind"], row["page_label"], row["color"], ref))
        for row in c.execute("SELECT * FROM literature_attachments").fetchall():
            ref = self._legacy_ref(c, "attachment", row["id"])
            self._asset(c, Attachment(row["id"], row["paper_id"], row["filename"], row["content_type"], bool(row["downloadable"]), row["link_mode"], ref))
        for table in _AI_TABLES:
            for row in c.execute(f"SELECT rowid AS snapshot_rowid,* FROM {table}").fetchall():
                data = dict(row)
                key = str(data.pop("snapshot_rowid"))
                c.execute("INSERT INTO literature_legacy_ai_snapshot VALUES (?,?,?)", (table, key, _json(data)))
                old = data.get("paper_id")
                if old is None:
                    continue
                canonical = self._resolve(c, old)
                if canonical is None:
                    canonical = self._preserved_ingest(c, Ingestion(Paper(old, "Recovered paper"), "legacy_recovery", old, {"reason": "AI record without source paper"}, 0, "legacy")).paper_id
                    self._conflict(c, old, "Recovered orphan AI paper; metadata unresolved", data)
                if table == "literature_ai_paper_text" and c.execute("SELECT 1 FROM literature_ai_paper_text WHERE paper_id=? AND page_number=?", (canonical, data["page_number"])).fetchone():
                    # Keep the original row under its legacy alias; snapshot and report make collision auditable.
                    self._conflict(c, old, "Page cache collision retained under legacy ID", data)
                    continue
                c.execute(f"UPDATE {table} SET paper_id=? WHERE rowid=?", (canonical, int(key)))

    @staticmethod
    def _legacy_ref(c, kind, resource_id):
        row = c.execute("SELECT provider,library_id,item_key FROM literature_external_references WHERE resource_type=? AND resource_id=? LIMIT 1", (kind, resource_id)).fetchone()
        return ExternalReference(*row) if row else None

    def _conflict(self, c, legacy, reason, payload):
        key = _id("conflict", _json([legacy, reason, payload]))
        c.execute("INSERT OR IGNORE INTO literature_identity_conflicts VALUES (?,?,?,?,?)", (key, legacy, reason, _json(payload), _now()))

    def _preserved_ingest(self, c, incoming):
        try:
            return self._ingest(c, incoming)
        except (IdentityConflictError, ValueError) as error:
            self._conflict(c, incoming.paper.id, str(error), asdict(incoming))
            # Preserve ambiguous source rows independently; never claim a conflicting identifier.
            return self._ingest(c, incoming, preserve=True)

    @staticmethod
    def _resolve(c, paper_id):
        row = c.execute("SELECT id FROM literature_documents WHERE id=? UNION ALL SELECT paper_id FROM literature_paper_aliases WHERE alias=? LIMIT 1", (paper_id, paper_id)).fetchone()
        return row[0] if row else None

    def _ingest(self, c, incoming: Ingestion, *, preserve=False):
        paper = incoming.paper
        now = _now()
        known = self._resolve(c, paper.id) if paper.id else None
        ids = {} if preserve else identifiers(paper)
        strong = {known} if known else set()
        if paper.external_ref:
            ref = paper.external_ref
            row = c.execute("SELECT paper_id FROM literature_source_references WHERE provider=? AND library_id=? AND item_key=?", (ref.provider, ref.library_id, ref.item_key)).fetchone()
            if row:
                strong.add(row[0])
        origin = c.execute("SELECT paper_id FROM literature_origins WHERE kind=? AND origin_key=?", (incoming.origin, incoming.origin_key)).fetchone()
        if origin:
            strong.add(origin[0])
        if not preserve:
            for kind, value in ids.items():
                row = c.execute("SELECT paper_id FROM literature_identifiers WHERE kind=? AND value=?", (kind, value)).fetchone()
                if row:
                    strong.add(row[0])
        if len(strong) > 1:
            raise IdentityConflictError("Identifiers resolve to different canonical papers", tuple(sorted(strong)))
        reason = "stable_identifier" if strong else "new"
        if not strong and not preserve:
            matches = []
            for row in c.execute("SELECT metadata_json FROM literature_documents"):
                existing = _paper(json.loads(row[0]))
                if title_key(existing.title) == title_key(paper.title) and len(title_key(paper.title)) >= 12:
                    # A conflicting formal DOI is not licensed by a title match.
                    if formal_doi(existing.doi) and formal_doi(ids.get("doi")) and existing.doi != ids["doi"]:
                        raise IdentityConflictError("Same title has conflicting formal DOI", (existing.id,))
                    if corroborated_title(existing, paper):
                        compatible(existing, paper)
                        matches.append(existing.id)
            if len(matches) > 1:
                raise IdentityConflictError("Ambiguous title/year/author match", tuple(matches))
            strong.update(matches)
            if matches:
                reason = "corroborated_title_year_author"
        canonical = next(iter(strong)) if strong else _id("paper", "legacy:" + paper.id) if paper.id else _id("paper")
        row = c.execute("SELECT * FROM literature_documents WHERE id=?", (canonical,)).fetchone()
        created = row is None
        if row and not preserve:
            compatible(_paper(json.loads(row["metadata_json"])), paper)
        metadata = json.loads(row["metadata_json"]) if row else asdict(replace(paper, id=canonical, external_ref=None))
        if not row:
            metadata["date_evidence"] = {}
            # Store normalized identity, not the raw spelling copied from the source.
            metadata.update({"doi": ids.get("doi", paper.doi), "arxiv_id": ids.get("arxiv", paper.arxiv_id), "openalex_id": ids.get("openalex", paper.openalex_id)})
        priorities = json.loads(row["field_priority_json"]) if row else {}
        incoming_values = asdict(paper)
        incoming_values.update({"doi": ids.get("doi", paper.doi), "arxiv_id": ids.get("arxiv", paper.arxiv_id), "openalex_id": ids.get("openalex", paper.openalex_id)})
        for field in ("title", "authors", "abstract", "year", "journal", "doi", "arxiv_id", "openalex_id"):
            value = incoming_values[field]
            if value in (None, "", [], ()):
                continue
            prior = priorities.get(field, {"priority": -1, "source": ""})
            identity_field = field in {"doi", "arxiv_id", "openalex_id"}
            stronger = incoming.priority > prior["priority"] or (incoming.priority == prior["priority"] and incoming.source == prior["source"])
            if not row or not metadata.get(field) or (stronger and not identity_field and not preserve) or (not preserve and field == "doi" and formal_doi(value) and not formal_doi(metadata.get(field))):
                metadata[field] = value
                priorities[field] = {"priority": incoming.priority, "source": incoming.source}
        metadata["id"] = canonical
        if priorities.get("tags", {}).get("priority", 0) < 100:
            metadata["tags"] = sorted(set(metadata.get("tags", [])) | set(paper.tags))
        metadata["date_evidence"] = {**metadata.get("date_evidence", {}), **{incoming.source: paper.date_evidence}} if paper.date_evidence else metadata.get("date_evidence", {})
        metadata["metadata_status"] = "conflict" if preserve or metadata.get("metadata_status") == "conflict" else "complete" if metadata.get("title") and metadata.get("authors") and metadata.get("year") else "incomplete"
        c.execute("INSERT INTO literature_documents VALUES (?,?,?,'inbox',0,?,?) ON CONFLICT(id) DO UPDATE SET metadata_json=excluded.metadata_json,field_priority_json=excluded.field_priority_json,updated_at=excluded.updated_at", (canonical, _json(metadata), _json(priorities), now, now))
        if incoming.restore:
            c.execute("UPDATE literature_documents SET deleted=0 WHERE id=?", (canonical,))
        if paper.id and paper.id != canonical:
            c.execute("INSERT OR IGNORE INTO literature_paper_aliases VALUES (?,?,?)", (paper.id, canonical, reason))
        for kind, value in ids.items():
            c.execute("INSERT OR IGNORE INTO literature_identifiers VALUES (?,?,?)", (kind, value, canonical))
        if paper.external_ref:
            ref = paper.external_ref
            c.execute("INSERT INTO literature_source_references VALUES (?,?,?,?,1) ON CONFLICT(provider,library_id,item_key) DO UPDATE SET active=1", (ref.provider, ref.library_id, ref.item_key, canonical))
        c.execute("INSERT OR IGNORE INTO literature_origins VALUES (?,?,?,?,?)", (incoming.origin, incoming.origin_key, canonical, _json(incoming.evidence), str(incoming.evidence.get("generated_at") or now)))
        payload = {"metadata": asdict(paper), "evidence": incoming.evidence, "origin": incoming.origin, "origin_key": incoming.origin_key}
        evidence_id = _id("evidence", _json([canonical, incoming.source, incoming.priority, payload]))
        c.execute("INSERT OR IGNORE INTO literature_metadata_evidence VALUES (?,?,?,?,?,?)", (evidence_id, canonical, incoming.source, incoming.priority, _json(payload), now))
        return IngestResult(canonical, created, reason)

    def ingest(self, incoming: Ingestion) -> IngestResult:
        self.ensure_schema()
        with self._connect() as c:
            c.execute("BEGIN IMMEDIATE")
            return self._ingest(c, incoming)

    def ingest_appearances(self, incoming, appearances):
        self.ensure_schema()
        with self._connect() as c:
            c.execute("BEGIN IMMEDIATE")
            result = self._ingest(c, incoming)
            for appearance in appearances:
                self._ingest(c, replace(incoming, paper=replace(incoming.paper, id=result.paper_id), origin_key=appearance["recommendation_id"], evidence=appearance, restore=False))
            return result

    def ingest_asset(self, incoming, asset):
        self.ensure_schema()
        with self._connect() as c:
            c.execute("BEGIN IMMEDIATE")
            result = self._ingest(c, incoming)
            for row in c.execute("SELECT payload_json FROM literature_assets WHERE paper_id=? AND active=1", (result.paper_id,)):
                existing = _attachment(json.loads(row[0]))
                if existing.sha256 == asset.sha256 and existing.role == asset.role:
                    return result, existing
            asset = self._asset(c, replace(asset, paper_id=result.paper_id))
            if asset.role == "primary":
                row = c.execute("SELECT metadata_json FROM literature_documents WHERE id=?", (result.paper_id,)).fetchone()
                metadata = json.loads(row[0])
                metadata["primary_asset_id"] = asset.id
                c.execute("UPDATE literature_documents SET metadata_json=? WHERE id=?", (_json(metadata), result.paper_id))
            return result, asset

    def _sync_collections(self, c, collections):
        fresh = set()
        for item in collections:
            native = _id("collection", item.id)
            existing = c.execute("SELECT collection_id FROM literature_source_collections WHERE source_id=?", (item.id,)).fetchone()
            if not existing:
                fresh.add(item.id)
                c.execute("INSERT INTO literature_native_collections VALUES (?,?,?)", (native, item.name, _id("collection", item.parent_id) if item.parent_id else None))
            c.execute("INSERT INTO literature_source_collections VALUES (?,?,?,1) ON CONFLICT(source_id) DO UPDATE SET payload_json=excluded.payload_json,active=1", (item.id, native, _json(asdict(item))))
        return fresh

    def _membership(self, c, collection_id, paper_id, *, initial=False):
        native = c.execute("SELECT collection_id FROM literature_source_collections WHERE source_id=?", (collection_id,)).fetchone()
        canonical = self._resolve(c, paper_id)
        if native and canonical:
            c.execute("INSERT OR IGNORE INTO literature_source_memberships VALUES (?,?)", (collection_id, paper_id))
            if initial:
                c.execute("INSERT OR IGNORE INTO literature_native_memberships VALUES (?,?)", (native[0], canonical))

    def _note(self, c, note):
        canonical = self._resolve(c, note.paper_id)
        if not canonical:
            self._conflict(c, note.id, "Source note parent unresolved", asdict(note))
            return
        note = replace(note, paper_id=canonical, source_paper_id=note.source_paper_id or note.paper_id)
        c.execute("INSERT INTO literature_source_notes VALUES (?,?,?,1) ON CONFLICT(id) DO UPDATE SET paper_id=excluded.paper_id,payload_json=excluded.payload_json,active=1", (note.id, canonical, _json(asdict(note))))

    def _asset(self, c, asset):
        canonical = self._resolve(c, asset.paper_id)
        if not canonical:
            self._conflict(c, asset.id, "Source asset parent unresolved", asdict(asset))
            return
        source_id = asset.id if asset.storage_kind == "zotero" else None
        asset_id = _id("asset", asset.id) if source_id else asset.id
        role = "supplementary" if source_id and any(x in asset.filename.casefold() for x in ("supplement", "supporting", "moesm")) else asset.role
        asset = replace(asset, id=asset_id, paper_id=canonical, role=role, source_paper_id=asset.source_paper_id or (asset.paper_id if source_id else None))
        c.execute("INSERT INTO literature_assets VALUES (?,?,?,?,1) ON CONFLICT(id) DO UPDATE SET paper_id=excluded.paper_id,payload_json=excluded.payload_json,active=1", (asset.id, canonical, _json(asdict(asset)), source_id))
        return asset

    def add_asset(self, asset: Attachment) -> Attachment:
        self.ensure_schema()
        with self._connect() as c:
            c.execute("BEGIN IMMEDIATE")
            canonical = self._resolve(c, asset.paper_id)
            for row in c.execute("SELECT payload_json FROM literature_assets WHERE paper_id=? AND active=1", (canonical,)):
                existing = _attachment(json.loads(row[0]))
                if asset.sha256 and existing.sha256 == asset.sha256 and existing.role == asset.role:
                    return existing
            return self._asset(c, asset)

    def replace_library(self, *, provider, library_id, collections, papers, collection_papers, notes, attachments, library_version):
        from app.modules.literature.domain.models import ChangedPaper
        collections, papers, notes, attachments = tuple(collections), tuple(papers), tuple(notes), tuple(attachments)
        changes = LibraryChanges(collections=collections, papers=tuple(ChangedPaper(p, tuple(cid for cid, pids in collection_papers.items() if p.id in pids)) for p in papers), notes=notes, attachments=attachments, library_version=library_version)
        self._sync(provider, library_id, changes, full=True)

    def apply_changes(self, *, provider, library_id, changes):
        self._sync(provider, library_id, changes, full=False)

    def _sync(self, provider, library_id, changes, *, full):
        self.ensure_schema()
        with self._connect() as c:
            c.execute("BEGIN IMMEDIATE")
            if full:
                c.execute("UPDATE literature_source_references SET active=0 WHERE provider=? AND library_id=?", (provider, library_id))
                for table in ("literature_assets", "literature_source_notes", "literature_source_collections"):
                    for row in c.execute(f"SELECT rowid,payload_json FROM {table}").fetchall():
                        ref = json.loads(row["payload_json"]).get("external_ref")
                        if ref and ref["provider"] == provider and ref["library_id"] == library_id:
                            c.execute(f"UPDATE {table} SET active=0 WHERE rowid=?", (row["rowid"],))
                            if table == "literature_source_collections":
                                source = c.execute("SELECT source_id FROM literature_source_collections WHERE rowid=?", (row["rowid"],)).fetchone()[0]
                                c.execute("DELETE FROM literature_source_memberships WHERE source_collection_id=?", (source,))
            fresh_collections = self._sync_collections(c, changes.collections)
            for changed in changes.papers:
                is_new_source = self._resolve(c, changed.paper.id) is None
                self._preserved_ingest(c, Ingestion(changed.paper, "zotero_import", changed.paper.id, {"library_version": changes.library_version}, 80, provider))
                c.execute("DELETE FROM literature_source_memberships WHERE source_paper_id=?", (changed.paper.id,))
                for collection_id in changed.collection_ids:
                    self._membership(c, collection_id, changed.paper.id, initial=is_new_source or collection_id in fresh_collections)
            for note in changes.notes:
                self._note(c, note)
            for asset in changes.attachments:
                self._asset(c, asset)
            for collection_id in changes.deleted_collection_ids:
                c.execute("UPDATE literature_source_collections SET active=0 WHERE source_id=?", (collection_id,))
                c.execute("DELETE FROM literature_source_memberships WHERE source_collection_id=?", (collection_id,))
            for old in set(changes.deleted_paper_ids) | set(changes.deleted_item_ids):
                canonical = self._resolve(c, old)
                if canonical:
                    # Scope deletion by actual source tuple, never by canonical ownership.
                    legacy_ref = c.execute("SELECT payload_json FROM literature_metadata_evidence WHERE paper_id=? AND source=?", (canonical, provider)).fetchall()
                    for record in legacy_ref:
                        metadata = json.loads(record[0])["metadata"]
                        ref = metadata.get("external_ref")
                        if metadata["id"] == old and ref and ref["library_id"] == library_id:
                            c.execute("UPDATE literature_source_references SET active=0 WHERE provider=? AND library_id=? AND item_key=?", (provider, library_id, ref["item_key"]))
                    for table in ("literature_assets", "literature_source_notes"):
                        for child in c.execute(f"SELECT rowid,payload_json FROM {table} WHERE paper_id=?", (canonical,)).fetchall():
                            child_payload = json.loads(child["payload_json"])
                            child_ref = child_payload.get("external_ref")
                            if child_payload.get("source_paper_id") == old and child_ref and child_ref["provider"] == provider and child_ref["library_id"] == library_id:
                                # Keep independently imported local assets and other connectors.
                                c.execute(f"UPDATE {table} SET active=0 WHERE rowid=?", (child["rowid"],))
                    c.execute("DELETE FROM literature_source_memberships WHERE source_paper_id=?", (old,))
                c.execute("UPDATE literature_assets SET active=0 WHERE source_id=?", (old,))
                c.execute("UPDATE literature_source_notes SET active=0 WHERE id=?", (old,))
            c.execute("INSERT INTO literature_library_state (provider,library_id,library_version,last_synced_at,sync_state,sync_error) VALUES (?,?,?,?,'succeeded',NULL) ON CONFLICT(provider,library_id) DO UPDATE SET library_version=COALESCE(excluded.library_version,literature_library_state.library_version),last_synced_at=excluded.last_synced_at,sync_state='succeeded',sync_error=NULL", (provider, library_id, changes.library_version, _now()))

    def _read_paper(self, c, row):
        paper = _paper(json.loads(row["metadata_json"]))
        sources = {r[0] for r in c.execute("SELECT provider FROM literature_source_references WHERE paper_id=? AND active=1", (paper.id,))}
        origins = {r[0] for r in c.execute("SELECT kind FROM literature_origins WHERE paper_id=?", (paper.id,))}
        sources.update(x for x in ("radar", "manual_pdf") if x in origins)
        pdf = any(json.loads(r[0]).get("downloadable") and json.loads(r[0]).get("content_type") == "application/pdf" for r in c.execute("SELECT payload_json FROM literature_assets WHERE paper_id=? AND active=1", (paper.id,)))
        return replace(paper, reading_status=row["reading_status"], sources=tuple(sorted(sources)), pdf_available=pdf)

    def get_paper(self, paper_id):
        self.ensure_schema()
        with self._connect() as c:
            canonical = self._resolve(c, paper_id)
            row = c.execute("SELECT * FROM literature_documents WHERE id=? AND deleted=0", (canonical,)).fetchone()
            if not row:
                return None
            collections = tuple(Collection(*r) for r in c.execute("SELECT n.id,n.name,n.parent_id FROM literature_native_collections n JOIN literature_native_memberships m ON m.collection_id=n.id WHERE m.paper_id=? ORDER BY n.name", (canonical,)))
            return PaperDetail(self._read_paper(c, row), collections)

    def list_papers(self, *, collection_id=None, limit=50, offset=0, query=None, author=None, year=None, journal=None, tag=None, reading_status=None):
        if not 1 <= limit <= 100 or offset < 0:
            raise ValueError("Invalid pagination")
        self.ensure_schema()
        with self._connect() as c:
            collection = c.execute("SELECT collection_id FROM literature_source_collections WHERE source_id=?", (collection_id,)).fetchone()
            if collection:
                collection_id = collection[0]
            members = {r[0] for r in c.execute("SELECT paper_id FROM literature_native_memberships WHERE collection_id=?", (collection_id,))} if collection_id else None
            papers = []
            for row in c.execute("SELECT * FROM literature_documents WHERE deleted=0 ORDER BY updated_at DESC,id"):
                p = _paper(json.loads(row["metadata_json"]))
                if members is not None and p.id not in members:
                    continue
                if query and query.casefold() not in (p.title + " " + " ".join(p.authors)).casefold():
                    continue
                if author and author.casefold() not in " ".join(p.authors).casefold():
                    continue
                if year is not None and p.year != year or journal and (p.journal or "").casefold() != journal.casefold() or tag and tag.casefold() not in {t.casefold() for t in p.tags}:
                    continue
                if reading_status and row["reading_status"] != reading_status:
                    continue
                papers.append(row)
            version = c.execute("SELECT library_version FROM literature_library_state ORDER BY last_synced_at DESC LIMIT 1").fetchone()
            return PaperPage(tuple(self._read_paper(c, r) for r in papers[offset:offset + limit]), len(papers), version[0] if version else None)

    def list_collections(self):
        self.ensure_schema()
        with self._connect() as c:
            return tuple(Collection(*r) for r in c.execute("SELECT id,name,parent_id FROM literature_native_collections ORDER BY name,id"))

    def list_filter_options(self):
        self.ensure_schema()
        with self._connect() as c:
            papers = [_paper(json.loads(r[0])) for r in c.execute("SELECT metadata_json FROM literature_documents WHERE deleted=0")]
        return FilterOptions(tuple(sorted({p.year for p in papers if p.year}, reverse=True)), tuple(sorted({p.journal for p in papers if p.journal})), tuple(sorted({t for p in papers for t in p.tags})))

    def list_notes(self, paper_id):
        self.ensure_schema()
        with self._connect() as c:
            result = []
            for row in c.execute("SELECT payload_json,active FROM literature_source_notes WHERE paper_id=?", (self._resolve(c, paper_id),)):
                data = json.loads(row[0])
                data["active"] = bool(row[1])
                data["external_ref"] = ExternalReference(**data["external_ref"]) if data.get("external_ref") else None
                result.append(Note(**data))
            return tuple(result)

    def list_attachments(self, paper_id):
        self.ensure_schema()
        with self._connect() as c:
            return tuple(replace(_attachment(json.loads(r[0])), active=bool(r[1]), downloadable=bool(r[1]) and bool(json.loads(r[0])["downloadable"])) for r in c.execute("SELECT payload_json,active FROM literature_assets WHERE paper_id=? ORDER BY id", (self._resolve(c, paper_id),)))

    def provenance(self, paper_id):
        self.ensure_schema()
        with self._connect() as c:
            canonical = self._resolve(c, paper_id)
            return {
                "references": [dict(r) for r in c.execute("SELECT * FROM literature_source_references WHERE paper_id=?", (canonical,))],
                "identifiers": [dict(r) for r in c.execute("SELECT kind,value FROM literature_identifiers WHERE paper_id=?", (canonical,))],
                "origins": [{**dict(r), "evidence": json.loads(r["evidence_json"])} for r in c.execute("SELECT * FROM literature_origins WHERE paper_id=? ORDER BY discovered_at", (canonical,))],
                "metadata_evidence": [{"source": r["source"], "priority": r["priority"], "observed_at": r["observed_at"], **json.loads(r["payload_json"])} for r in c.execute("SELECT * FROM literature_metadata_evidence WHERE paper_id=? ORDER BY observed_at", (canonical,))],
                "selected_fields": json.loads(c.execute("SELECT field_priority_json FROM literature_documents WHERE id=?", (canonical,)).fetchone()[0]),
                "conflicts": [dict(r) for r in c.execute("SELECT legacy_id,reason,payload_json FROM literature_identity_conflicts WHERE legacy_id IN (SELECT alias FROM literature_paper_aliases WHERE paper_id=?)", (canonical,))],
                "source_collections": [{"active": bool(r[0]), **json.loads(r[1])} for r in c.execute("SELECT s.active,s.payload_json FROM literature_source_collections s JOIN literature_source_memberships m ON m.source_collection_id=s.source_id JOIN literature_paper_aliases a ON a.alias=m.source_paper_id WHERE a.paper_id=?", (canonical,))],
            }

    def set_state(self, paper_id, *, reading_status=None, deleted=None, tags=None):
        self.ensure_schema()
        with self._connect() as c:
            c.execute("BEGIN IMMEDIATE")
            canonical = self._resolve(c, paper_id)
            if reading_status is not None:
                if reading_status not in {"inbox", "saved", "reading", "read", "archived"}:
                    raise ValueError("Invalid reading status")
                c.execute("UPDATE literature_documents SET reading_status=? WHERE id=?", (reading_status, canonical))
            if deleted is not None:
                c.execute("UPDATE literature_documents SET deleted=? WHERE id=?", (int(deleted), canonical))
            if tags is not None:
                row = c.execute("SELECT metadata_json,field_priority_json FROM literature_documents WHERE id=?", (canonical,)).fetchone()
                data = json.loads(row[0])
                priorities = json.loads(row[1])
                priorities["tags"] = {"priority": 100, "source": "user"}
                data["tags"] = sorted(set(tags))
                c.execute("UPDATE literature_documents SET metadata_json=?,field_priority_json=? WHERE id=?", (_json(data), _json(priorities), canonical))

    def create_collection(self, name, parent_id=None):
        self.ensure_schema()
        collection = Collection(_id("collection"), name.strip(), parent_id)
        with self._connect() as c:
            c.execute("INSERT INTO literature_native_collections VALUES (?,?,?)", (collection.id, collection.name, parent_id))
        return collection

    def set_membership(self, paper_id, collection_id, present):
        self.ensure_schema()
        with self._connect() as c:
            canonical = self._resolve(c, paper_id)
            if not c.execute("SELECT 1 FROM literature_native_collections WHERE id=?", (collection_id,)).fetchone():
                raise ValueError("Unknown collection")
            if present:
                c.execute("INSERT OR IGNORE INTO literature_native_memberships VALUES (?,?)", (collection_id, canonical))
            else:
                c.execute("DELETE FROM literature_native_memberships WHERE collection_id=? AND paper_id=?", (collection_id, canonical))

    def saved_origins(self, keys):
        self.ensure_schema()
        with self._connect() as c:
            return {key: row[0] for key in keys if (row := c.execute("SELECT o.paper_id FROM literature_origins o JOIN literature_documents d ON d.id=o.paper_id WHERE o.kind='radar' AND o.origin_key=? AND d.deleted=0", (key,)).fetchone())}

    def migration_report(self):
        self.ensure_schema()
        with self._connect() as c:
            initial = json.loads(c.execute("SELECT report_json FROM literature_canonical_migrations WHERE version=1").fetchone()[0])
            return {"initial": initial, "current": self._report(c)}

    @staticmethod
    def _report(c):
        tables = {"legacy_zotero_papers": "literature_papers", "canonical_documents": "literature_documents", "external_references": "literature_source_references", "identifiers": "literature_identifiers", "assets": "literature_assets", "notes": "literature_source_notes", "collections": "literature_native_collections", "aliases": "literature_paper_aliases", "conflicts": "literature_identity_conflicts", "ai_snapshots": "literature_legacy_ai_snapshot"}
        result = {key: c.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for key, table in tables.items()}
        result["unresolved_records"] = [dict(r) for r in c.execute("SELECT legacy_id,reason FROM literature_identity_conflicts")]
        result["foreign_key_errors"] = [tuple(r) for r in c.execute("PRAGMA foreign_key_check")]
        return result
