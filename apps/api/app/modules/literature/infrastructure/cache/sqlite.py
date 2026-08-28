import sqlite3
from dataclasses import dataclass
import json
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from pathlib import Path

from app.modules.literature.domain.ai_models import (
    LiteratureAIAnalysis,
    LiteratureAIConversation,
    LiteratureAIMessage,
    LiteratureAIPaperTextPage,
    LiteratureUserNote,
    json_object,
)
from app.modules.literature.domain.models import (
    Attachment,
    ChangedPaper,
    Collection,
    ExternalReference,
    FilterOptions,
    LibraryChanges,
    LibraryState,
    Note,
    Paper,
    PaperDetail,
    PaperPage,
)


@dataclass(frozen=True)
class SchemaVersion:
    version: int


@dataclass(frozen=True)
class _Migration:
    version: int
    statements: tuple[str, ...]


_MIGRATIONS = (
    _Migration(
        version=1,
        statements=(
            """
            CREATE TABLE schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE literature_library_state (
                provider TEXT NOT NULL,
                library_id TEXT NOT NULL,
                library_version TEXT,
                last_synced_at TEXT,
                sync_state TEXT NOT NULL DEFAULT 'not_started',
                sync_error TEXT,
                PRIMARY KEY (provider, library_id)
            )
            """,
            """
            CREATE TABLE literature_papers (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                authors_json TEXT NOT NULL DEFAULT '[]',
                abstract TEXT,
                year INTEGER,
                journal TEXT,
                doi TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE literature_collections (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                parent_id TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (parent_id) REFERENCES literature_collections(id)
                    DEFERRABLE INITIALLY DEFERRED
            )
            """,
            """
            CREATE TABLE literature_collection_papers (
                collection_id TEXT NOT NULL,
                paper_id TEXT NOT NULL,
                PRIMARY KEY (collection_id, paper_id),
                FOREIGN KEY (collection_id) REFERENCES literature_collections(id) ON DELETE CASCADE,
                FOREIGN KEY (paper_id) REFERENCES literature_papers(id) ON DELETE CASCADE
            )
            """,
            """
            CREATE TABLE literature_tags (
                paper_id TEXT NOT NULL,
                tag TEXT NOT NULL,
                PRIMARY KEY (paper_id, tag),
                FOREIGN KEY (paper_id) REFERENCES literature_papers(id) ON DELETE CASCADE
            )
            """,
            """
            CREATE TABLE literature_notes (
                id TEXT PRIMARY KEY,
                paper_id TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (paper_id) REFERENCES literature_papers(id) ON DELETE CASCADE
            )
            """,
            """
            CREATE TABLE literature_attachments (
                id TEXT PRIMARY KEY,
                paper_id TEXT NOT NULL,
                filename TEXT NOT NULL,
                content_type TEXT,
                downloadable INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (paper_id) REFERENCES literature_papers(id) ON DELETE CASCADE
            )
            """,
            """
            CREATE TABLE literature_external_references (
                resource_type TEXT NOT NULL,
                resource_id TEXT NOT NULL,
                provider TEXT NOT NULL,
                library_id TEXT NOT NULL,
                item_key TEXT NOT NULL,
                item_version TEXT,
                PRIMARY KEY (resource_type, resource_id, provider),
                UNIQUE (resource_type, provider, library_id, item_key)
            )
            """,
            "CREATE INDEX literature_collections_parent_idx ON literature_collections(parent_id)",
            "CREATE INDEX literature_collection_papers_paper_idx ON literature_collection_papers(paper_id)",
            "CREATE INDEX literature_notes_paper_idx ON literature_notes(paper_id)",
            "CREATE INDEX literature_attachments_paper_idx ON literature_attachments(paper_id)",
            "CREATE INDEX literature_external_references_resource_idx ON literature_external_references(resource_type, resource_id)",
        ),
    ),
    _Migration(
        version=2,
        statements=(
            "SELECT 1",
            "ALTER TABLE literature_notes ADD COLUMN kind TEXT NOT NULL DEFAULT 'note'",
            "ALTER TABLE literature_notes ADD COLUMN page_label TEXT",
            "ALTER TABLE literature_notes ADD COLUMN color TEXT",
            "ALTER TABLE literature_attachments ADD COLUMN link_mode TEXT",
            "UPDATE literature_library_state SET library_version = NULL, sync_state = 'not_started'",
        ),
    ),
    _Migration(
        version=3,
        statements=(
            "SELECT 1",
            """
            CREATE TABLE literature_ai_analyses (
                id TEXT PRIMARY KEY,
                paper_id TEXT NOT NULL,
                analysis_type TEXT NOT NULL,
                model TEXT NOT NULL,
                prompt_version TEXT NOT NULL,
                content_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE literature_ai_conversations (
                id TEXT PRIMARY KEY,
                paper_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE literature_ai_messages (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content_json TEXT NOT NULL,
                model TEXT,
                prompt_version TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (conversation_id)
                    REFERENCES literature_ai_conversations(id) ON DELETE CASCADE
            )
            """,
            """
            CREATE TABLE literature_ai_paper_text (
                paper_id TEXT NOT NULL,
                page_number INTEGER NOT NULL,
                text TEXT NOT NULL,
                extractor_version TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (paper_id, page_number)
            )
            """,
            """
            CREATE TABLE literature_user_notes (
                id TEXT PRIMARY KEY,
                paper_id TEXT NOT NULL,
                content TEXT NOT NULL,
                source TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
            "CREATE INDEX literature_ai_analyses_paper_idx ON literature_ai_analyses(paper_id, analysis_type, created_at)",
            "CREATE INDEX literature_ai_conversations_paper_idx ON literature_ai_conversations(paper_id, updated_at)",
            "CREATE INDEX literature_ai_messages_conversation_idx ON literature_ai_messages(conversation_id, created_at)",
            "CREATE INDEX literature_user_notes_paper_idx ON literature_user_notes(paper_id, updated_at)",
        ),
    ),
)


class SQLiteLiteratureRepository:
    """Owns versioned SQLite schema setup for the local Literature metadata cache."""

    def __init__(self, database_url: str) -> None:
        self._database_path = _sqlite_path(database_url)

    def ensure_schema(self) -> SchemaVersion:
        if self._database_path != ":memory:":
            Path(self._database_path).parent.mkdir(parents=True, exist_ok=True)

        with sqlite3.connect(self._database_path) as connection:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS schema_migrations (
                        version INTEGER PRIMARY KEY,
                        applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                applied_versions = {
                    row[0] for row in connection.execute("SELECT version FROM schema_migrations")
                }
                for migration in _MIGRATIONS:
                    if migration.version in applied_versions:
                        continue
                    for statement in migration.statements[1:]:
                        connection.execute(statement)
                    connection.execute(
                        "INSERT INTO schema_migrations (version) VALUES (?)",
                        (migration.version,),
                    )
                connection.commit()
            except Exception:
                connection.rollback()
                raise

        return SchemaVersion(version=max(migration.version for migration in _MIGRATIONS))

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
        self.ensure_schema()
        collection_items = tuple(collections)
        paper_items = tuple(papers)
        note_items = tuple(notes)
        attachment_items = tuple(attachments)
        synced_at = _utc_now()

        with sqlite3.connect(self._database_path) as connection:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute("DELETE FROM literature_collection_papers")
                connection.execute("DELETE FROM literature_tags")
                connection.execute("DELETE FROM literature_notes")
                connection.execute("DELETE FROM literature_attachments")
                connection.execute("DELETE FROM literature_external_references")
                connection.execute("DELETE FROM literature_papers")
                connection.execute("DELETE FROM literature_collections")
                connection.execute("DELETE FROM literature_library_state")

                connection.executemany(
                    "INSERT INTO literature_collections (id, name, parent_id, updated_at) VALUES (?, ?, ?, ?)",
                    ((collection.id, collection.name, collection.parent_id, synced_at) for collection in collection_items),
                )
                connection.executemany(
                    """
                    INSERT INTO literature_papers
                        (id, title, authors_json, abstract, year, journal, doi, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        (
                            paper.id,
                            paper.title,
                            json.dumps(paper.authors, ensure_ascii=False),
                            paper.abstract,
                            paper.year,
                            paper.journal,
                            paper.doi,
                            synced_at,
                        )
                        for paper in paper_items
                    ),
                )
                connection.executemany(
                    "INSERT INTO literature_collection_papers (collection_id, paper_id) VALUES (?, ?)",
                    (
                        (collection_id, paper_id)
                        for collection_id, paper_ids in collection_papers.items()
                        for paper_id in paper_ids
                    ),
                )
                connection.executemany(
                    "INSERT INTO literature_tags (paper_id, tag) VALUES (?, ?)",
                    ((paper.id, tag) for paper in paper_items for tag in paper.tags),
                )
                connection.executemany(
                    """
                    INSERT INTO literature_notes
                        (id, paper_id, content, kind, page_label, color, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        (
                            note.id,
                            note.paper_id,
                            note.content,
                            note.kind,
                            note.page_label,
                            note.color,
                            synced_at,
                        )
                        for note in note_items
                    ),
                )
                connection.executemany(
                    """
                    INSERT INTO literature_attachments
                        (id, paper_id, filename, content_type, downloadable, link_mode, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        (
                            attachment.id,
                            attachment.paper_id,
                            attachment.filename,
                            attachment.content_type,
                            int(attachment.downloadable),
                            attachment.link_mode,
                            synced_at,
                        )
                        for attachment in attachment_items
                    ),
                )
                connection.executemany(
                    """
                    INSERT INTO literature_external_references
                        (resource_type, resource_id, provider, library_id, item_key)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        (resource_type, resource.id, reference.provider, reference.library_id, reference.item_key)
                        for resource_type, resources in (
                            ("collection", collection_items),
                            ("paper", paper_items),
                            ("note", note_items),
                            ("attachment", attachment_items),
                        )
                        for resource in resources
                        for reference in (resource.external_ref,)
                        if reference is not None
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO literature_library_state
                        (provider, library_id, library_version, last_synced_at, sync_state, sync_error)
                    VALUES (?, ?, ?, ?, 'succeeded', NULL)
                    """,
                    (provider, library_id, library_version, synced_at),
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def get_library_state(self, *, provider: str, library_id: str) -> LibraryState | None:
        if self._database_path != ":memory:" and not Path(self._database_path).exists():
            return None
        self.ensure_schema()
        with sqlite3.connect(self._database_path) as connection:
            row = connection.execute(
                """
                SELECT provider, library_id, library_version, sync_state, last_synced_at
                FROM literature_library_state
                WHERE provider = ? AND library_id = ?
                """,
                (provider, library_id),
            ).fetchone()
        if row is None:
            return None
        return LibraryState(
            provider=row[0],
            library_id=row[1],
            library_version=row[2],
            sync_state=row[3],
            last_synced_at=row[4],
        )

    def list_collections(self) -> tuple[Collection, ...]:
        """Read cached collections, including their provider identity when available."""
        if self._database_path != ":memory:" and not Path(self._database_path).exists():
            return ()
        self.ensure_schema()
        with sqlite3.connect(self._database_path) as connection:
            rows = connection.execute(
                """
                SELECT
                    c.id,
                    c.name,
                    c.parent_id,
                    er.provider,
                    er.library_id,
                    er.item_key
                FROM literature_collections AS c
                LEFT JOIN literature_external_references AS er
                    ON er.resource_type = 'collection' AND er.resource_id = c.id
                ORDER BY c.name COLLATE NOCASE, c.id
                """
            ).fetchall()
        return tuple(_collection_from_row(row) for row in rows)

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
        """Read a paginated paper view from the metadata cache."""
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        if offset < 0:
            raise ValueError("offset must be non-negative")
        if self._database_path != ":memory:" and not Path(self._database_path).exists():
            return PaperPage(items=(), total=0)

        self.ensure_schema()
        with sqlite3.connect(self._database_path) as connection:
            connection.row_factory = sqlite3.Row
            joins: list[str] = []
            conditions: list[str] = []
            parameters: list[object] = []
            if collection_id is not None:
                joins.append(
                    "INNER JOIN literature_collection_papers AS cp ON cp.paper_id = p.id"
                )
                conditions.append("cp.collection_id = ?")
                parameters.append(collection_id)
            if query:
                conditions.append(
                    "(instr(lower(p.title), lower(?)) > 0 OR instr(lower(p.authors_json), lower(?)) > 0)"
                )
                parameters.extend((query, query))
            if author:
                conditions.append("instr(lower(p.authors_json), lower(?)) > 0")
                parameters.append(author)
            if year is not None:
                conditions.append("p.year = ?")
                parameters.append(year)
            if journal:
                conditions.append("p.journal = ? COLLATE NOCASE")
                parameters.append(journal)
            if tag:
                conditions.append(
                    "EXISTS (SELECT 1 FROM literature_tags AS filter_tag WHERE filter_tag.paper_id = p.id AND filter_tag.tag = ? COLLATE NOCASE)"
                )
                parameters.append(tag)

            from_clause = "FROM literature_papers AS p " + " ".join(joins)
            where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
            total = connection.execute(
                f"SELECT COUNT(DISTINCT p.id) {from_clause} {where_clause}",
                parameters,
            ).fetchone()[0]
            rows = connection.execute(
                f"""
                SELECT DISTINCT
                    p.id,
                    p.title,
                    p.authors_json,
                    p.abstract,
                    p.year,
                    p.journal,
                    p.doi,
                    er.provider,
                    er.library_id,
                    er.item_key
                {from_clause}
                LEFT JOIN literature_external_references AS er
                    ON er.resource_type = 'paper' AND er.resource_id = p.id
                {where_clause}
                ORDER BY p.updated_at DESC, p.id
                LIMIT ? OFFSET ?
                """,
                (*parameters, limit, offset),
            ).fetchall()

            papers = tuple(_paper_from_row(row, connection) for row in rows)
            library_version = _library_version(connection)
        return PaperPage(items=papers, total=total, library_version=library_version)

    def get_paper(self, paper_id: str) -> PaperDetail | None:
        self.ensure_schema()
        with sqlite3.connect(self._database_path) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                """
                SELECT
                    p.id, p.title, p.authors_json, p.abstract, p.year, p.journal, p.doi,
                    er.provider, er.library_id, er.item_key
                FROM literature_papers AS p
                LEFT JOIN literature_external_references AS er
                    ON er.resource_type = 'paper' AND er.resource_id = p.id
                WHERE p.id = ?
                """,
                (paper_id,),
            ).fetchone()
            if row is None:
                return None
            paper = _paper_from_row(row, connection)
            collection_rows = connection.execute(
                """
                SELECT c.id, c.name, c.parent_id, er.provider, er.library_id, er.item_key
                FROM literature_collections AS c
                INNER JOIN literature_collection_papers AS cp ON cp.collection_id = c.id
                LEFT JOIN literature_external_references AS er
                    ON er.resource_type = 'collection' AND er.resource_id = c.id
                WHERE cp.paper_id = ?
                ORDER BY c.name COLLATE NOCASE, c.id
                """,
                (paper_id,),
            ).fetchall()
        return PaperDetail(
            paper=paper,
            collections=tuple(_collection_from_row(row) for row in collection_rows),
        )

    def list_notes(self, paper_id: str) -> tuple[Note, ...]:
        self.ensure_schema()
        with sqlite3.connect(self._database_path) as connection:
            rows = connection.execute(
                """
                SELECT n.id, n.paper_id, n.content, n.kind, n.page_label, n.color,
                       er.provider, er.library_id, er.item_key
                FROM literature_notes AS n
                LEFT JOIN literature_external_references AS er
                    ON er.resource_type = 'note' AND er.resource_id = n.id
                WHERE n.paper_id = ?
                ORDER BY n.kind, n.updated_at DESC, n.id
                """,
                (paper_id,),
            ).fetchall()
        return tuple(_note_from_row(row) for row in rows)

    def list_attachments(self, paper_id: str) -> tuple[Attachment, ...]:
        self.ensure_schema()
        with sqlite3.connect(self._database_path) as connection:
            rows = connection.execute(
                """
                SELECT a.id, a.paper_id, a.filename, a.content_type, a.downloadable, a.link_mode,
                       er.provider, er.library_id, er.item_key
                FROM literature_attachments AS a
                LEFT JOIN literature_external_references AS er
                    ON er.resource_type = 'attachment' AND er.resource_id = a.id
                WHERE a.paper_id = ?
                ORDER BY a.downloadable DESC, a.filename COLLATE NOCASE, a.id
                """,
                (paper_id,),
            ).fetchall()
        return tuple(_attachment_from_row(row) for row in rows)

    def list_filter_options(self) -> FilterOptions:
        self.ensure_schema()
        with sqlite3.connect(self._database_path) as connection:
            years = tuple(
                int(row[0])
                for row in connection.execute(
                    "SELECT DISTINCT year FROM literature_papers WHERE year IS NOT NULL ORDER BY year DESC"
                )
            )
            journals = tuple(
                str(row[0])
                for row in connection.execute(
                    "SELECT DISTINCT journal FROM literature_papers WHERE journal IS NOT NULL AND journal <> '' ORDER BY journal COLLATE NOCASE"
                )
            )
            tags = tuple(
                str(row[0])
                for row in connection.execute(
                    "SELECT DISTINCT tag FROM literature_tags ORDER BY tag COLLATE NOCASE"
                )
            )
        return FilterOptions(years=years, journals=journals, tags=tags)

    def apply_changes(
        self,
        *,
        provider: str,
        library_id: str,
        changes: LibraryChanges,
    ) -> None:
        self.ensure_schema()
        synced_at = _utc_now()
        with sqlite3.connect(self._database_path) as connection:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("BEGIN IMMEDIATE")
            try:
                for collection in changes.collections:
                    connection.execute(
                        """
                        INSERT INTO literature_collections (id, name, parent_id, updated_at)
                        VALUES (?, ?, ?, ?)
                        ON CONFLICT(id) DO UPDATE SET
                            name = excluded.name,
                            parent_id = excluded.parent_id,
                            updated_at = excluded.updated_at
                        """,
                        (collection.id, collection.name, collection.parent_id, synced_at),
                    )
                    _upsert_external_reference(connection, "collection", collection)

                for changed_paper in changes.papers:
                    _upsert_paper(connection, changed_paper.paper, synced_at)
                    _upsert_external_reference(connection, "paper", changed_paper.paper)
                    connection.execute(
                        "DELETE FROM literature_tags WHERE paper_id = ?",
                        (changed_paper.paper.id,),
                    )
                    connection.executemany(
                        "INSERT INTO literature_tags (paper_id, tag) VALUES (?, ?)",
                        ((changed_paper.paper.id, tag) for tag in changed_paper.paper.tags),
                    )
                    connection.execute(
                        "DELETE FROM literature_collection_papers WHERE paper_id = ?",
                        (changed_paper.paper.id,),
                    )
                    for collection_id in changed_paper.collection_ids:
                        connection.execute(
                            """
                            INSERT INTO literature_collection_papers (collection_id, paper_id)
                            SELECT ?, ?
                            WHERE EXISTS (SELECT 1 FROM literature_collections WHERE id = ?)
                            """,
                            (collection_id, changed_paper.paper.id, collection_id),
                        )

                for note in changes.notes:
                    _upsert_note(connection, note, synced_at)
                    _upsert_external_reference(connection, "note", note)

                for attachment in changes.attachments:
                    _upsert_attachment(connection, attachment, synced_at)
                    _upsert_external_reference(connection, "attachment", attachment)

                for collection_id in changes.deleted_collection_ids:
                    connection.execute(
                        "DELETE FROM literature_collections WHERE id = ?",
                        (collection_id,),
                    )
                    connection.execute(
                        "DELETE FROM literature_external_references WHERE resource_type = 'collection' AND resource_id = ?",
                        (collection_id,),
                    )
                for paper_id in changes.deleted_paper_ids:
                    connection.execute("DELETE FROM literature_papers WHERE id = ?", (paper_id,))
                    connection.execute(
                        "DELETE FROM literature_external_references WHERE resource_id = ?",
                        (paper_id,),
                    )
                for item_id in changes.deleted_item_ids:
                    connection.execute("DELETE FROM literature_notes WHERE id = ?", (item_id,))
                    connection.execute("DELETE FROM literature_attachments WHERE id = ?", (item_id,))
                    connection.execute("DELETE FROM literature_papers WHERE id = ?", (item_id,))
                    connection.execute(
                        "DELETE FROM literature_external_references WHERE resource_id = ?",
                        (item_id,),
                    )

                connection.execute(
                    """
                    DELETE FROM literature_external_references
                    WHERE resource_type = 'note'
                      AND NOT EXISTS (
                          SELECT 1 FROM literature_notes
                          WHERE literature_notes.id = literature_external_references.resource_id
                      )
                    """
                )
                connection.execute(
                    """
                    DELETE FROM literature_external_references
                    WHERE resource_type = 'attachment'
                      AND NOT EXISTS (
                          SELECT 1 FROM literature_attachments
                          WHERE literature_attachments.id = literature_external_references.resource_id
                      )
                    """
                )

                connection.execute(
                    """
                    INSERT INTO literature_library_state
                        (provider, library_id, library_version, last_synced_at, sync_state, sync_error)
                    VALUES (?, ?, ?, ?, 'succeeded', NULL)
                    ON CONFLICT(provider, library_id) DO UPDATE SET
                        library_version = COALESCE(excluded.library_version, literature_library_state.library_version),
                        last_synced_at = excluded.last_synced_at,
                        sync_state = excluded.sync_state,
                        sync_error = NULL
                    """,
                    (provider, library_id, changes.library_version, synced_at),
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def list_analyses(
        self,
        paper_id: str,
        *,
        analysis_type: str | None = None,
    ) -> tuple[LiteratureAIAnalysis, ...]:
        self.ensure_schema()
        query = """
            SELECT id, paper_id, analysis_type, model, prompt_version, content_json, created_at
            FROM literature_ai_analyses
            WHERE paper_id = ?
        """
        parameters: tuple[object, ...] = (paper_id,)
        if analysis_type is not None:
            query += " AND analysis_type = ?"
            parameters = (paper_id, analysis_type)
        query += " ORDER BY created_at DESC, id DESC"
        with sqlite3.connect(self._database_path) as connection:
            rows = connection.execute(query, parameters).fetchall()
        return tuple(_analysis_from_row(row) for row in rows)

    def get_analysis(self, analysis_id: str) -> LiteratureAIAnalysis | None:
        self.ensure_schema()
        with sqlite3.connect(self._database_path) as connection:
            row = connection.execute(
                """
                SELECT id, paper_id, analysis_type, model, prompt_version, content_json, created_at
                FROM literature_ai_analyses
                WHERE id = ?
                """,
                (analysis_id,),
            ).fetchone()
        return _analysis_from_row(row) if row is not None else None

    def save_analysis(self, analysis: LiteratureAIAnalysis) -> None:
        self.ensure_schema()
        with sqlite3.connect(self._database_path) as connection:
            connection.execute(
                """
                INSERT INTO literature_ai_analyses
                    (id, paper_id, analysis_type, model, prompt_version, content_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    analysis.id,
                    analysis.paper_id,
                    analysis.analysis_type,
                    analysis.model,
                    analysis.prompt_version,
                    json.dumps(analysis.content, ensure_ascii=False),
                    analysis.created_at,
                ),
            )
            connection.commit()

    def create_conversation(self, conversation: LiteratureAIConversation) -> None:
        self.ensure_schema()
        with sqlite3.connect(self._database_path) as connection:
            connection.execute(
                """
                INSERT INTO literature_ai_conversations (id, paper_id, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    conversation.id,
                    conversation.paper_id,
                    conversation.created_at,
                    conversation.updated_at,
                ),
            )
            connection.commit()

    def get_conversation(self, conversation_id: str) -> LiteratureAIConversation | None:
        self.ensure_schema()
        with sqlite3.connect(self._database_path) as connection:
            row = connection.execute(
                """
                SELECT id, paper_id, created_at, updated_at
                FROM literature_ai_conversations
                WHERE id = ?
                """,
                (conversation_id,),
            ).fetchone()
        return _conversation_from_row(row) if row is not None else None

    def list_conversations(self, paper_id: str) -> tuple[LiteratureAIConversation, ...]:
        self.ensure_schema()
        with sqlite3.connect(self._database_path) as connection:
            rows = connection.execute(
                """
                SELECT id, paper_id, created_at, updated_at
                FROM literature_ai_conversations
                WHERE paper_id = ?
                ORDER BY updated_at DESC, id DESC
                """,
                (paper_id,),
            ).fetchall()
        return tuple(_conversation_from_row(row) for row in rows)

    def list_messages(self, conversation_id: str) -> tuple[LiteratureAIMessage, ...]:
        self.ensure_schema()
        with sqlite3.connect(self._database_path) as connection:
            rows = connection.execute(
                """
                SELECT id, conversation_id, role, content_json, model, prompt_version, created_at
                FROM literature_ai_messages
                WHERE conversation_id = ?
                ORDER BY created_at, rowid
                """,
                (conversation_id,),
            ).fetchall()
        return tuple(_message_from_row(row) for row in rows)

    def get_message(self, message_id: str) -> LiteratureAIMessage | None:
        self.ensure_schema()
        with sqlite3.connect(self._database_path) as connection:
            row = connection.execute(
                """
                SELECT id, conversation_id, role, content_json, model, prompt_version, created_at
                FROM literature_ai_messages
                WHERE id = ?
                """,
                (message_id,),
            ).fetchone()
        return _message_from_row(row) if row is not None else None

    def save_message(self, message: LiteratureAIMessage) -> None:
        self.save_messages((message,))

    def save_messages(self, messages: tuple[LiteratureAIMessage, ...]) -> None:
        if not messages:
            return
        conversation_id = messages[0].conversation_id
        if any(message.conversation_id != conversation_id for message in messages):
            raise ValueError("All messages must belong to the same conversation")
        self.ensure_schema()
        with sqlite3.connect(self._database_path) as connection:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.executemany(
                    """
                    INSERT INTO literature_ai_messages
                        (id, conversation_id, role, content_json, model, prompt_version, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        (
                            message.id,
                            message.conversation_id,
                            message.role,
                            json.dumps(message.content, ensure_ascii=False),
                            message.model,
                            message.prompt_version,
                            message.created_at,
                        )
                        for message in messages
                    ),
                )
                connection.execute(
                    "UPDATE literature_ai_conversations SET updated_at = ? WHERE id = ?",
                    (messages[-1].created_at, conversation_id),
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def list_paper_text(self, paper_id: str) -> tuple[LiteratureAIPaperTextPage, ...]:
        self.ensure_schema()
        with sqlite3.connect(self._database_path) as connection:
            rows = connection.execute(
                """
                SELECT paper_id, page_number, text, extractor_version, created_at, updated_at
                FROM literature_ai_paper_text
                WHERE paper_id = ?
                ORDER BY page_number
                """,
                (paper_id,),
            ).fetchall()
        return tuple(_paper_text_from_row(row) for row in rows)

    def replace_paper_text(
        self,
        paper_id: str,
        pages: tuple[LiteratureAIPaperTextPage, ...],
    ) -> None:
        self.ensure_schema()
        with sqlite3.connect(self._database_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    "DELETE FROM literature_ai_paper_text WHERE paper_id = ?",
                    (paper_id,),
                )
                connection.executemany(
                    """
                    INSERT INTO literature_ai_paper_text
                        (paper_id, page_number, text, extractor_version, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        (
                            page.paper_id,
                            page.page_number,
                            page.text,
                            page.extractor_version,
                            page.created_at,
                            page.updated_at,
                        )
                        for page in pages
                    ),
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def list_user_notes(self, paper_id: str) -> tuple[LiteratureUserNote, ...]:
        self.ensure_schema()
        with sqlite3.connect(self._database_path) as connection:
            rows = connection.execute(
                """
                SELECT id, paper_id, content, source, created_at, updated_at
                FROM literature_user_notes
                WHERE paper_id = ?
                ORDER BY updated_at DESC, id DESC
                """,
                (paper_id,),
            ).fetchall()
        return tuple(_user_note_from_row(row) for row in rows)

    def save_user_note(self, note: LiteratureUserNote) -> None:
        self.ensure_schema()
        with sqlite3.connect(self._database_path) as connection:
            connection.execute(
                """
                INSERT INTO literature_user_notes
                    (id, paper_id, content, source, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    note.id,
                    note.paper_id,
                    note.content,
                    note.source,
                    note.created_at,
                    note.updated_at,
                ),
            )
            connection.commit()

    def mark_sync_failed(self, *, provider: str, library_id: str, error: str) -> None:
        self.ensure_schema()
        with sqlite3.connect(self._database_path) as connection:
            connection.execute(
                """
                INSERT INTO literature_library_state
                    (provider, library_id, sync_state, sync_error)
                VALUES (?, ?, 'failed', ?)
                ON CONFLICT(provider, library_id) DO UPDATE SET
                    sync_state = 'failed',
                    sync_error = excluded.sync_error
                """,
                (provider, library_id, error),
            )
            connection.commit()


def _sqlite_path(database_url: str) -> str:
    prefix = "sqlite:///"
    if not database_url.startswith(prefix):
        raise ValueError("Literature metadata cache requires a sqlite:/// database URL")
    return database_url.removeprefix(prefix)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _library_version(connection: sqlite3.Connection) -> str | None:
    row = connection.execute(
        """
        SELECT library_version
        FROM literature_library_state
        ORDER BY last_synced_at DESC
        LIMIT 1
        """
    ).fetchone()
    return row[0] if row else None


def _collection_from_row(row: tuple[object, ...]) -> Collection:
    provider, library_id, item_key = row[3:6]
    reference = None
    if provider is not None and library_id is not None and item_key is not None:
        reference = ExternalReference(
            provider=str(provider),
            library_id=str(library_id),
            item_key=str(item_key),
        )
    return Collection(
        id=str(row[0]),
        name=str(row[1]),
        parent_id=str(row[2]) if row[2] is not None else None,
        external_ref=reference,
    )


def _paper_from_row(row: sqlite3.Row, connection: sqlite3.Connection) -> Paper:
    provider, library_id, item_key = row[7:10]
    reference = None
    if provider is not None and library_id is not None and item_key is not None:
        reference = ExternalReference(
            provider=str(provider),
            library_id=str(library_id),
            item_key=str(item_key),
        )
    try:
        authors = tuple(str(author) for author in json.loads(row[2]))
    except (TypeError, json.JSONDecodeError):
        authors = ()
    tags = tuple(
        str(tag)
        for tag, in connection.execute(
            "SELECT tag FROM literature_tags WHERE paper_id = ? ORDER BY tag COLLATE NOCASE, tag",
            (row[0],),
        )
    )
    return Paper(
        id=str(row[0]),
        title=str(row[1]),
        authors=authors,
        abstract=str(row[3]) if row[3] is not None else None,
        year=int(row[4]) if row[4] is not None else None,
        journal=str(row[5]) if row[5] is not None else None,
        doi=str(row[6]) if row[6] is not None else None,
        tags=tags,
        external_ref=reference,
    )


def _external_reference_from_values(values: tuple[object, object, object]) -> ExternalReference | None:
    provider, library_id, item_key = values
    if provider is None or library_id is None or item_key is None:
        return None
    return ExternalReference(
        provider=str(provider),
        library_id=str(library_id),
        item_key=str(item_key),
    )


def _note_from_row(row: tuple[object, ...]) -> Note:
    return Note(
        id=str(row[0]),
        paper_id=str(row[1]),
        content=str(row[2]),
        kind=str(row[3]),
        page_label=str(row[4]) if row[4] is not None else None,
        color=str(row[5]) if row[5] is not None else None,
        external_ref=_external_reference_from_values(row[6:9]),
    )


def _attachment_from_row(row: tuple[object, ...]) -> Attachment:
    return Attachment(
        id=str(row[0]),
        paper_id=str(row[1]),
        filename=str(row[2]),
        content_type=str(row[3]) if row[3] is not None else None,
        downloadable=bool(row[4]),
        link_mode=str(row[5]) if row[5] is not None else None,
        external_ref=_external_reference_from_values(row[6:9]),
    )


def _analysis_from_row(row: tuple[object, ...]) -> LiteratureAIAnalysis:
    return LiteratureAIAnalysis(
        id=str(row[0]),
        paper_id=str(row[1]),
        analysis_type=str(row[2]),
        model=str(row[3]),
        prompt_version=str(row[4]),
        content=json_object(json.loads(str(row[5]))),
        created_at=str(row[6]),
    )


def _conversation_from_row(row: tuple[object, ...]) -> LiteratureAIConversation:
    return LiteratureAIConversation(
        id=str(row[0]),
        paper_id=str(row[1]),
        created_at=str(row[2]),
        updated_at=str(row[3]),
    )


def _message_from_row(row: tuple[object, ...]) -> LiteratureAIMessage:
    return LiteratureAIMessage(
        id=str(row[0]),
        conversation_id=str(row[1]),
        role=str(row[2]),
        content=json_object(json.loads(str(row[3]))),
        model=str(row[4]) if row[4] is not None else None,
        prompt_version=str(row[5]) if row[5] is not None else None,
        created_at=str(row[6]),
    )


def _paper_text_from_row(row: tuple[object, ...]) -> LiteratureAIPaperTextPage:
    return LiteratureAIPaperTextPage(
        paper_id=str(row[0]),
        page_number=int(row[1]),
        text=str(row[2]),
        extractor_version=str(row[3]),
        created_at=str(row[4]),
        updated_at=str(row[5]),
    )


def _user_note_from_row(row: tuple[object, ...]) -> LiteratureUserNote:
    return LiteratureUserNote(
        id=str(row[0]),
        paper_id=str(row[1]),
        content=str(row[2]),
        source=str(row[3]),
        created_at=str(row[4]),
        updated_at=str(row[5]),
    )


def _upsert_paper(connection: sqlite3.Connection, paper: Paper, updated_at: str) -> None:
    connection.execute(
        """
        INSERT INTO literature_papers
            (id, title, authors_json, abstract, year, journal, doi, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            title = excluded.title,
            authors_json = excluded.authors_json,
            abstract = excluded.abstract,
            year = excluded.year,
            journal = excluded.journal,
            doi = excluded.doi,
            updated_at = excluded.updated_at
        """,
        (
            paper.id,
            paper.title,
            json.dumps(paper.authors, ensure_ascii=False),
            paper.abstract,
            paper.year,
            paper.journal,
            paper.doi,
            updated_at,
        ),
    )


def _upsert_note(connection: sqlite3.Connection, note: Note, updated_at: str) -> None:
    connection.execute(
        """
        INSERT INTO literature_notes
            (id, paper_id, content, kind, page_label, color, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            paper_id = excluded.paper_id,
            content = excluded.content,
            kind = excluded.kind,
            page_label = excluded.page_label,
            color = excluded.color,
            updated_at = excluded.updated_at
        """,
        (
            note.id,
            note.paper_id,
            note.content,
            note.kind,
            note.page_label,
            note.color,
            updated_at,
        ),
    )


def _upsert_attachment(
    connection: sqlite3.Connection,
    attachment: Attachment,
    updated_at: str,
) -> None:
    connection.execute(
        """
        INSERT INTO literature_attachments
            (id, paper_id, filename, content_type, downloadable, link_mode, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            paper_id = excluded.paper_id,
            filename = excluded.filename,
            content_type = excluded.content_type,
            downloadable = excluded.downloadable,
            link_mode = excluded.link_mode,
            updated_at = excluded.updated_at
        """,
        (
            attachment.id,
            attachment.paper_id,
            attachment.filename,
            attachment.content_type,
            int(attachment.downloadable),
            attachment.link_mode,
            updated_at,
        ),
    )


def _upsert_external_reference(
    connection: sqlite3.Connection,
    resource_type: str,
    resource: Collection | Paper | Note | Attachment | ChangedPaper,
) -> None:
    reference = resource.paper.external_ref if isinstance(resource, ChangedPaper) else resource.external_ref
    if reference is None:
        return
    resource_id = resource.paper.id if isinstance(resource, ChangedPaper) else resource.id
    connection.execute(
        """
        INSERT INTO literature_external_references
            (resource_type, resource_id, provider, library_id, item_key)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(resource_type, resource_id, provider) DO UPDATE SET
            library_id = excluded.library_id,
            item_key = excluded.item_key
        """,
        (resource_type, resource_id, reference.provider, reference.library_id, reference.item_key),
    )
