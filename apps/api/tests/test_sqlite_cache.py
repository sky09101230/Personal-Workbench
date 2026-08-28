import sqlite3

import pytest

from app.modules.literature.domain.ai_models import (
    LiteratureAIAnalysis,
    LiteratureAIConversation,
    LiteratureAIMessage,
    LiteratureAIPaperTextPage,
    LiteratureUserNote,
)
from app.modules.literature.domain.models import Paper
from app.modules.literature.infrastructure.cache.sqlite import SQLiteLiteratureRepository


def test_schema_migration_creates_metadata_cache_idempotently(tmp_path) -> None:
    database_path = tmp_path / "literature.db"
    repository = SQLiteLiteratureRepository(f"sqlite:///{database_path.as_posix()}")

    assert repository.ensure_schema().version == 3
    assert repository.ensure_schema().version == 3

    with sqlite3.connect(database_path) as connection:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        migration_count = connection.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0]

    assert {
        "literature_library_state",
        "literature_papers",
        "literature_collections",
        "literature_collection_papers",
        "literature_tags",
        "literature_notes",
        "literature_attachments",
        "literature_external_references",
        "literature_ai_analyses",
        "literature_ai_conversations",
        "literature_ai_messages",
        "literature_ai_paper_text",
        "literature_user_notes",
    }.issubset(tables)
    assert migration_count == 3


def test_schema_migration_rejects_non_sqlite_database_urls() -> None:
    with pytest.raises(ValueError, match="sqlite"):
        SQLiteLiteratureRepository("postgresql://localhost/workbench")


def test_v2_migration_preserves_cache_and_requires_one_full_asset_sync(tmp_path) -> None:
    database_path = tmp_path / "v1.db"
    with sqlite3.connect(database_path) as connection:
        connection.execute("CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY)")
        connection.execute("INSERT INTO schema_migrations (version) VALUES (1)")
        connection.execute(
            """
            CREATE TABLE literature_library_state (
                provider TEXT NOT NULL,
                library_id TEXT NOT NULL,
                library_version TEXT,
                last_synced_at TEXT,
                sync_state TEXT NOT NULL,
                sync_error TEXT,
                PRIMARY KEY (provider, library_id)
            )
            """
        )
        connection.execute(
            "INSERT INTO literature_library_state VALUES ('zotero', '123', '5013', 'now', 'succeeded', NULL)"
        )
        connection.execute(
            "CREATE TABLE literature_notes (id TEXT PRIMARY KEY, paper_id TEXT, content TEXT, created_at TEXT, updated_at TEXT)"
        )
        connection.execute(
            "CREATE TABLE literature_attachments (id TEXT PRIMARY KEY, paper_id TEXT, filename TEXT, content_type TEXT, downloadable INTEGER, created_at TEXT, updated_at TEXT)"
        )
        connection.commit()

    repository = SQLiteLiteratureRepository(f"sqlite:///{database_path.as_posix()}")
    assert repository.ensure_schema().version == 3

    with sqlite3.connect(database_path) as connection:
        state = connection.execute(
            "SELECT library_version, last_synced_at, sync_state FROM literature_library_state"
        ).fetchone()
        note_columns = {row[1] for row in connection.execute("PRAGMA table_info(literature_notes)")}
        attachment_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(literature_attachments)")
        }

    assert state == (None, "now", "not_started")
    assert {"kind", "page_label", "color"}.issubset(note_columns)
    assert "link_mode" in attachment_columns


def test_ai_state_and_user_notes_survive_full_zotero_replacement(tmp_path) -> None:
    repository = SQLiteLiteratureRepository(
        f"sqlite:///{(tmp_path / 'literature-ai.db').as_posix()}"
    )
    paper = Paper(id="paper-1", title="Optical paper")
    repository.replace_library(
        provider="zotero",
        library_id="123",
        collections=(),
        papers=(paper,),
        collection_papers={},
        notes=(),
        attachments=(),
        library_version="1",
    )
    timestamp = "2026-08-28T00:00:00+00:00"
    analysis = LiteratureAIAnalysis(
        id="analysis-1",
        paper_id=paper.id,
        analysis_type="overview",
        model="deepseek-test",
        prompt_version="overview_v1",
        content={"research_question": "Why?"},
        created_at=timestamp,
    )
    conversation = LiteratureAIConversation(
        id="conversation-1",
        paper_id=paper.id,
        created_at=timestamp,
        updated_at=timestamp,
    )
    user_message = LiteratureAIMessage(
        id="z-user-message",
        conversation_id=conversation.id,
        role="user",
        content={"question": "Why?"},
        model=None,
        prompt_version=None,
        created_at=timestamp,
    )
    assistant_message = LiteratureAIMessage(
        id="a-assistant-message",
        conversation_id=conversation.id,
        role="assistant",
        content={"answer": "Because"},
        model="deepseek-test",
        prompt_version="ask_paper_v1",
        created_at=timestamp,
    )
    page = LiteratureAIPaperTextPage(
        paper_id=paper.id,
        page_number=1,
        text="Extracted text",
        extractor_version="pypdf-test",
        created_at=timestamp,
        updated_at=timestamp,
    )
    note = LiteratureUserNote(
        id="note-1",
        paper_id=paper.id,
        content="Keep this",
        source="ai_overview",
        created_at=timestamp,
        updated_at=timestamp,
    )
    repository.save_analysis(analysis)
    repository.create_conversation(conversation)
    repository.save_message(user_message)
    repository.save_message(assistant_message)
    repository.replace_paper_text(paper.id, (page,))
    repository.save_user_note(note)

    repository.replace_library(
        provider="zotero",
        library_id="123",
        collections=(),
        papers=(paper,),
        collection_papers={},
        notes=(),
        attachments=(),
        library_version="2",
    )

    assert repository.list_analyses(paper.id) == (analysis,)
    assert repository.get_conversation(conversation.id) == conversation
    assert repository.list_messages(conversation.id) == (
        user_message,
        assistant_message,
    )
    assert repository.list_paper_text(paper.id) == (page,)
    assert repository.list_user_notes(paper.id) == (note,)


def test_message_batch_is_atomic(tmp_path) -> None:
    repository = SQLiteLiteratureRepository(
        f"sqlite:///{(tmp_path / 'literature-ai-atomic.db').as_posix()}"
    )
    timestamp = "2026-08-28T00:00:00+00:00"
    conversation = LiteratureAIConversation(
        id="conversation-atomic",
        paper_id="paper-1",
        created_at=timestamp,
        updated_at=timestamp,
    )
    repository.create_conversation(conversation)
    first = LiteratureAIMessage(
        id="duplicate-message",
        conversation_id=conversation.id,
        role="user",
        content={"question": "Why?"},
        model=None,
        prompt_version=None,
        created_at=timestamp,
    )
    second = LiteratureAIMessage(
        id="duplicate-message",
        conversation_id=conversation.id,
        role="assistant",
        content={"answer": "Because"},
        model="deepseek-test",
        prompt_version="ask_paper_v1",
        created_at=timestamp,
    )

    with pytest.raises(sqlite3.IntegrityError):
        repository.save_messages((first, second))

    assert repository.list_messages(conversation.id) == ()
