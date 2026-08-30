import json
import sqlite3
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.modules.news.application.errors import PaperResearchIdentityConflictError
from app.modules.news.application.research import (
    canonical_title,
    canonical_title_year,
    research_payload_digest,
)
from app.modules.news.domain.models import FeedItem, FeedItemType, FeedPage, Topic
from app.modules.news.domain.research_models import (
    PaperResearchFeedPage,
    PaperResearchIngest,
    PaperResearchIngestResult,
    PaperResearchPaperInput,
    PaperResearchRadarItem,
    PaperResearchRadarRun,
    PaperResearchReviewResult,
)


@dataclass(frozen=True)
class SchemaVersion:
    version: int


_SCHEMA_VERSION = 4
_SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS news_feed_items (
        id TEXT PRIMARY KEY,
        type TEXT NOT NULL,
        source TEXT NOT NULL,
        title TEXT NOT NULL,
        summary TEXT,
        url TEXT NOT NULL,
        authors_json TEXT NOT NULL,
        published_at TEXT,
        fetched_at TEXT,
        metadata_json TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS news_topics (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        keywords_json TEXT NOT NULL,
        negative_keywords_json TEXT NOT NULL,
        enabled_sources_json TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS news_item_topics (
        item_id TEXT NOT NULL REFERENCES news_feed_items(id) ON DELETE CASCADE,
        topic_id TEXT NOT NULL REFERENCES news_topics(id) ON DELETE CASCADE,
        PRIMARY KEY (item_id, topic_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS news_user_state (
        item_id TEXT PRIMARY KEY REFERENCES news_feed_items(id) ON DELETE CASCADE,
        read INTEGER NOT NULL DEFAULT 0,
        saved INTEGER NOT NULL DEFAULT 0,
        hidden INTEGER NOT NULL DEFAULT 0
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS news_source_state (
        source TEXT PRIMARY KEY,
        last_successful_refresh_slot TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS news_feed_items_type_idx ON news_feed_items(type)",
    "CREATE INDEX IF NOT EXISTS news_feed_items_published_idx ON news_feed_items(published_at)",
    "CREATE INDEX IF NOT EXISTS news_item_topics_topic_idx ON news_item_topics(topic_id)",
    """
    CREATE TABLE IF NOT EXISTS news_papers (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        authors_json TEXT NOT NULL DEFAULT '[]',
        doi TEXT,
        arxiv_id TEXT,
        openalex_id TEXT,
        canonical_title TEXT,
        canonical_title_year TEXT NOT NULL UNIQUE,
        published_at TEXT,
        venue TEXT,
        publication_type TEXT,
        url TEXT,
        pdf_url TEXT,
        abstract TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS news_paper_research_runs (
        id TEXT PRIMARY KEY,
        task_key TEXT NOT NULL,
        run_key TEXT NOT NULL,
        schema_version TEXT NOT NULL,
        status TEXT NOT NULL,
        generated_at TEXT NOT NULL,
        ingested_at TEXT NOT NULL,
        agent_type TEXT NOT NULL,
        agent_model TEXT NOT NULL,
        prompt_version TEXT NOT NULL,
        query_plan_json TEXT NOT NULL,
        papers_found INTEGER NOT NULL,
        papers_accepted INTEGER NOT NULL,
        run_kind TEXT NOT NULL DEFAULT 'paper_research',
        ingest_identity TEXT,
        payload_digest TEXT,
        profile_json TEXT NOT NULL DEFAULT '{}',
        search_window_json TEXT NOT NULL DEFAULT '{}',
        candidate_count INTEGER,
        verified_candidate_count INTEGER,
        recommended_count INTEGER,
        warnings_json TEXT NOT NULL DEFAULT '[]',
        source_status_json TEXT NOT NULL DEFAULT '[]',
        zotero_context_json TEXT NOT NULL DEFAULT '{}',
        diagnostics_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL,
        UNIQUE (task_key, run_key)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS news_paper_research_recommendations (
        id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL REFERENCES news_paper_research_runs(id) ON DELETE CASCADE,
        paper_id TEXT NOT NULL REFERENCES news_papers(id) ON DELETE CASCADE,
        ai_summary TEXT NOT NULL,
        recommendation_reason TEXT NOT NULL,
        relevance_score REAL CHECK (relevance_score IS NULL OR relevance_score BETWEEN 0 AND 1),
        novelty_score REAL CHECK (novelty_score IS NULL OR novelty_score BETWEEN 0 AND 1),
        scientific_value_score REAL CHECK (scientific_value_score IS NULL OR scientific_value_score BETWEEN 0 AND 1),
        recency_score REAL CHECK (recency_score IS NULL OR recency_score BETWEEN 0 AND 1),
        overall_score REAL CHECK (overall_score IS NULL OR overall_score BETWEEN 0 AND 1),
        topics_json TEXT NOT NULL DEFAULT '[]',
        matched_topics_json TEXT NOT NULL DEFAULT '[]',
        relationship_to_library TEXT,
        source_json TEXT NOT NULL DEFAULT '{}',
        selection_kind TEXT NOT NULL DEFAULT 'recommended',
        selection_rank INTEGER,
        date_evidence_json TEXT NOT NULL DEFAULT '{}',
        zotero_relationship_json TEXT NOT NULL DEFAULT '{}',
        evidence_json TEXT NOT NULL DEFAULT '{}',
        review_status TEXT NOT NULL DEFAULT 'new',
        created_at TEXT NOT NULL,
        UNIQUE (run_id, paper_id)
    )
    """,
    "CREATE UNIQUE INDEX IF NOT EXISTS news_papers_doi_unique ON news_papers(doi) WHERE doi IS NOT NULL",
    "CREATE UNIQUE INDEX IF NOT EXISTS news_papers_arxiv_unique ON news_papers(arxiv_id) WHERE arxiv_id IS NOT NULL",
    "CREATE UNIQUE INDEX IF NOT EXISTS news_papers_openalex_unique ON news_papers(openalex_id) WHERE openalex_id IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS news_research_runs_generated_idx ON news_paper_research_runs(generated_at DESC)",
    "CREATE INDEX IF NOT EXISTS news_recommendations_paper_idx ON news_paper_research_recommendations(paper_id, created_at DESC)",
)

_V4_INDEX_STATEMENTS = (
    "CREATE INDEX IF NOT EXISTS news_papers_canonical_title_idx ON news_papers(canonical_title)",
    "CREATE UNIQUE INDEX IF NOT EXISTS news_research_runs_ingest_identity_unique "
    "ON news_paper_research_runs(ingest_identity) WHERE ingest_identity IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS news_research_runs_kind_generated_idx "
    "ON news_paper_research_runs(run_kind, generated_at DESC)",
    "CREATE INDEX IF NOT EXISTS news_recommendations_selection_idx "
    "ON news_paper_research_recommendations(run_id, selection_kind, selection_rank)",
)


class SQLiteNewsRepository:
    """Owns the News-only schema within the shared Workbench SQLite file."""

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
                    CREATE TABLE IF NOT EXISTS news_schema_migrations (
                        version INTEGER PRIMARY KEY,
                        applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                applied = connection.execute(
                    "SELECT 1 FROM news_schema_migrations WHERE version = ?",
                    (_SCHEMA_VERSION,),
                ).fetchone()
                if applied is None:
                    for statement in _SCHEMA_STATEMENTS:
                        connection.execute(statement)
                    _ensure_schema_v4(connection)
                    for statement in _V4_INDEX_STATEMENTS:
                        connection.execute(statement)
                    connection.execute(
                        "INSERT INTO news_schema_migrations (version) VALUES (?)",
                        (_SCHEMA_VERSION,),
                    )
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        return SchemaVersion(version=_SCHEMA_VERSION)

    def get_source_refresh_slot(self, source: str) -> str | None:
        self.ensure_schema()
        with sqlite3.connect(self._database_path) as connection:
            row = connection.execute(
                "SELECT last_successful_refresh_slot FROM news_source_state WHERE source = ?",
                (source,),
            ).fetchone()
        return str(row[0]) if row is not None else None

    def ingest_paper_research(
        self,
        payload: PaperResearchIngest,
    ) -> PaperResearchIngestResult:
        self.ensure_schema()
        ingested_at = _utc_now()
        payload_digest = research_payload_digest(payload)
        created_paper_ids: set[str] = set()
        updated_paper_ids: set[str] = set()
        created_recommendation_ids: set[str] = set()
        updated_recommendation_ids: set[str] = set()
        accepted_paper_ids: set[str] = set()

        with sqlite3.connect(self._database_path) as connection:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("BEGIN IMMEDIATE")
            try:
                run_row = None
                if payload.ingest_identity is not None:
                    run_row = connection.execute(
                        """
                        SELECT id, task_key, run_key, ingest_identity, payload_digest,
                               papers_accepted
                        FROM news_paper_research_runs
                        WHERE ingest_identity = ?
                        """,
                        (payload.ingest_identity,),
                    ).fetchone()
                if run_row is None:
                    run_row = connection.execute(
                        """
                        SELECT id, task_key, run_key, ingest_identity, payload_digest,
                               papers_accepted
                        FROM news_paper_research_runs
                        WHERE task_key = ? AND run_key = ?
                        """,
                        (payload.task_key, payload.run_key),
                    ).fetchone()

                created_run = run_row is None
                if run_row is not None and payload.ingest_identity is not None:
                    existing_identity = str(run_row[3]) if run_row[3] is not None else None
                    existing_digest = str(run_row[4]) if run_row[4] is not None else None
                    if (
                        str(run_row[1]) != payload.task_key
                        or str(run_row[2]) != payload.run_key
                        or (
                            existing_identity is not None
                            and existing_identity != payload.ingest_identity
                        )
                    ):
                        raise PaperResearchIdentityConflictError(
                            "Radar ingest identity conflicts with an existing run"
                        )
                    if existing_digest is not None and existing_digest != payload_digest:
                        raise PaperResearchIdentityConflictError(
                            "Radar ingest identity was reused with different content"
                        )
                    if existing_digest == payload_digest:
                        connection.commit()
                        return PaperResearchIngestResult(
                            run_id=str(run_row[0]),
                            created_run=False,
                            created_papers=0,
                            updated_papers=0,
                            created_recommendations=0,
                            updated_recommendations=0,
                            papers_found=len(payload.papers),
                            papers_accepted=int(run_row[5]),
                        )

                run_id = str(run_row[0]) if run_row else f"research-run:{uuid4()}"
                run_values = (
                    payload.schema_version,
                    payload.generated_at,
                    ingested_at,
                    payload.agent.type,
                    payload.agent.model,
                    payload.agent.prompt_version,
                    _json(payload.query_plan),
                    len(payload.papers),
                    payload.run_kind,
                    payload.ingest_identity,
                    payload_digest if payload.ingest_identity is not None else None,
                    _json(payload.profile),
                    _json(payload.search_window),
                    payload.candidate_count,
                    payload.verified_candidate_count,
                    payload.recommended_count,
                    _json(payload.warnings),
                    _json(payload.source_status),
                    _json(payload.zotero_context),
                    _json(payload.diagnostics),
                )
                if created_run:
                    connection.execute(
                        """
                        INSERT INTO news_paper_research_runs (
                            id, task_key, run_key, schema_version, status, generated_at,
                            ingested_at, agent_type, agent_model, prompt_version,
                            query_plan_json, papers_found, papers_accepted, run_kind,
                            ingest_identity, payload_digest, profile_json, search_window_json,
                            candidate_count, verified_candidate_count, recommended_count,
                            warnings_json, source_status_json, zotero_context_json,
                            diagnostics_json, created_at
                        ) VALUES (
                            ?, ?, ?, ?, 'succeeded', ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?,
                            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                        )
                        """,
                        (
                            run_id,
                            payload.task_key,
                            payload.run_key,
                            *run_values,
                            ingested_at,
                        ),
                    )
                else:
                    connection.execute(
                        """
                        UPDATE news_paper_research_runs
                        SET schema_version = ?, status = 'succeeded', generated_at = ?,
                            ingested_at = ?, agent_type = ?, agent_model = ?,
                            prompt_version = ?, query_plan_json = ?, papers_found = ?,
                            run_kind = ?, ingest_identity = ?, payload_digest = ?,
                            profile_json = ?, search_window_json = ?, candidate_count = ?,
                            verified_candidate_count = ?, recommended_count = ?,
                            warnings_json = ?, source_status_json = ?, zotero_context_json = ?,
                            diagnostics_json = ?
                        WHERE id = ?
                        """,
                        (*run_values, run_id),
                    )

                for paper in payload.papers:
                    paper_id, created_paper = _upsert_research_paper(
                        connection,
                        paper,
                        ingested_at,
                    )
                    accepted_paper_ids.add(paper_id)
                    if created_paper:
                        created_paper_ids.add(paper_id)
                    else:
                        updated_paper_ids.add(paper_id)

                    recommendation_row = connection.execute(
                        """
                        SELECT id
                        FROM news_paper_research_recommendations
                        WHERE run_id = ? AND paper_id = ?
                        """,
                        (run_id, paper_id),
                    ).fetchone()
                    recommendation_values = (
                        paper.ai_summary,
                        paper.recommendation_reason,
                        paper.relevance_score,
                        paper.novelty_score,
                        paper.scientific_value_score,
                        paper.recency_score,
                        paper.overall_score,
                        _json(paper.topics),
                        _json(paper.matched_topics),
                        paper.relationship_to_library,
                        _json(paper.source),
                        paper.selection_kind,
                        paper.selection_rank,
                        _json(paper.date_evidence),
                        _json(paper.zotero_relationship),
                        _json(paper.evidence),
                    )
                    if recommendation_row is None:
                        recommendation_id = f"research-recommendation:{uuid4()}"
                        connection.execute(
                            """
                            INSERT INTO news_paper_research_recommendations (
                                id, run_id, paper_id, ai_summary, recommendation_reason,
                                relevance_score, novelty_score, scientific_value_score,
                                recency_score, overall_score, topics_json,
                                matched_topics_json, relationship_to_library, source_json,
                                selection_kind, selection_rank, date_evidence_json,
                                zotero_relationship_json, evidence_json, review_status, created_at
                            ) VALUES (
                                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                                'new', ?
                            )
                            """,
                            (
                                recommendation_id,
                                run_id,
                                paper_id,
                                *recommendation_values,
                                ingested_at,
                            ),
                        )
                        created_recommendation_ids.add(recommendation_id)
                    else:
                        recommendation_id = str(recommendation_row[0])
                        connection.execute(
                            """
                            UPDATE news_paper_research_recommendations
                            SET ai_summary = ?, recommendation_reason = ?,
                                relevance_score = ?, novelty_score = ?,
                                scientific_value_score = ?, recency_score = ?,
                                overall_score = ?, topics_json = ?, matched_topics_json = ?,
                                relationship_to_library = ?, source_json = ?,
                                selection_kind = ?, selection_rank = ?, date_evidence_json = ?,
                                zotero_relationship_json = ?, evidence_json = ?
                            WHERE id = ?
                            """,
                            (*recommendation_values, recommendation_id),
                        )
                        updated_recommendation_ids.add(recommendation_id)

                connection.execute(
                    """
                    UPDATE news_paper_research_runs
                    SET papers_accepted = ?
                    WHERE id = ?
                    """,
                    (len(accepted_paper_ids), run_id),
                )
                connection.commit()
            except sqlite3.IntegrityError as error:
                connection.rollback()
                raise PaperResearchIdentityConflictError(
                    "Paper identifiers conflict with existing Research data"
                ) from error
            except Exception:
                connection.rollback()
                raise

        return PaperResearchIngestResult(
            run_id=run_id,
            created_run=created_run,
            created_papers=len(created_paper_ids),
            updated_papers=len(updated_paper_ids - created_paper_ids),
            created_recommendations=len(created_recommendation_ids),
            updated_recommendations=len(updated_recommendation_ids - created_recommendation_ids),
            papers_found=len(payload.papers),
            papers_accepted=len(accepted_paper_ids),
        )

    def list_paper_research(
        self,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> PaperResearchFeedPage:
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        if offset < 0:
            raise ValueError("offset must be non-negative")
        self.ensure_schema()
        latest = """
            SELECT recommendation.*, ROW_NUMBER() OVER (
                PARTITION BY recommendation.paper_id
                ORDER BY run.generated_at DESC, run.ingested_at DESC,
                         recommendation.created_at DESC, recommendation.id DESC
            ) AS recency
            FROM news_paper_research_recommendations AS recommendation
            JOIN news_paper_research_runs AS run ON run.id = recommendation.run_id
        """
        with sqlite3.connect(self._database_path) as connection:
            total = connection.execute(
                f"SELECT COUNT(*) FROM ({latest}) AS latest WHERE latest.recency = 1"
            ).fetchone()[0]
            rows = connection.execute(
                f"""
                SELECT
                    paper.id, paper.title, paper.authors_json, paper.doi,
                    paper.arxiv_id, paper.openalex_id, paper.published_at,
                    paper.venue, paper.url, paper.pdf_url, paper.abstract,
                    latest.ai_summary, latest.recommendation_reason,
                    latest.relevance_score, latest.novelty_score,
                    latest.topics_json, latest.matched_topics_json,
                    latest.relationship_to_library, latest.source_json,
                    run.id, run.task_key, run.run_key, run.schema_version,
                    run.generated_at, run.ingested_at, run.agent_type,
                    run.agent_model, run.prompt_version, run.query_plan_json
                FROM ({latest}) AS latest
                JOIN news_papers AS paper ON paper.id = latest.paper_id
                JOIN news_paper_research_runs AS run ON run.id = latest.run_id
                WHERE latest.recency = 1
                ORDER BY run.generated_at DESC, paper.published_at DESC, paper.id
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            ).fetchall()
        return PaperResearchFeedPage(
            items=tuple(_research_feed_item(row) for row in rows),
            total=int(total),
            limit=limit,
            offset=offset,
        )

    def latest_literature_radar(self) -> PaperResearchRadarRun | None:
        self.ensure_schema()
        with sqlite3.connect(self._database_path) as connection:
            run_row = connection.execute(
                """
                SELECT id, task_key, run_key, generated_at, ingested_at,
                       profile_json, search_window_json, candidate_count,
                       verified_candidate_count, recommended_count, warnings_json,
                       source_status_json, zotero_context_json, diagnostics_json,
                       papers_found, papers_accepted
                FROM news_paper_research_runs
                WHERE run_kind = 'literature_radar'
                ORDER BY generated_at DESC, ingested_at DESC, id DESC
                LIMIT 1
                """
            ).fetchone()
            if run_row is None:
                return None
            item_rows = connection.execute(
                """
                SELECT
                    recommendation.id, paper.id, recommendation.selection_kind,
                    recommendation.selection_rank, paper.title, paper.authors_json,
                    paper.doi, paper.arxiv_id, paper.published_at, paper.venue,
                    paper.publication_type, paper.url, recommendation.ai_summary,
                    recommendation.recommendation_reason,
                    recommendation.relevance_score, recommendation.novelty_score,
                    recommendation.scientific_value_score,
                    recommendation.recency_score, recommendation.overall_score,
                    recommendation.relationship_to_library,
                    recommendation.zotero_relationship_json,
                    recommendation.date_evidence_json, recommendation.evidence_json,
                    recommendation.source_json, recommendation.review_status
                FROM news_paper_research_recommendations AS recommendation
                JOIN news_papers AS paper ON paper.id = recommendation.paper_id
                WHERE recommendation.run_id = ?
                ORDER BY
                    CASE recommendation.selection_kind
                        WHEN 'recommended' THEN 0 ELSE 1
                    END,
                    COALESCE(recommendation.selection_rank, 999999),
                    COALESCE(recommendation.overall_score, -1) DESC,
                    paper.title
                """,
                (str(run_row[0]),),
            ).fetchall()

        items = tuple(_radar_item(row) for row in item_rows)
        recommendations = tuple(
            item for item in items if item.selection_kind == "recommended"
        )
        alternatives = tuple(
            item for item in items if item.selection_kind == "verified_not_selected"
        )
        return PaperResearchRadarRun(
            id=str(run_row[0]),
            task_key=str(run_row[1]),
            run_key=str(run_row[2]),
            generated_at=str(run_row[3]),
            ingested_at=str(run_row[4]),
            profile=dict(json.loads(str(run_row[5]))),
            search_window=dict(json.loads(str(run_row[6]))),
            candidate_count=(
                int(run_row[7]) if run_row[7] is not None else int(run_row[14])
            ),
            verified_candidate_count=(
                int(run_row[8]) if run_row[8] is not None else int(run_row[15])
            ),
            recommended_count=(
                int(run_row[9]) if run_row[9] is not None else len(recommendations)
            ),
            warnings=tuple(json.loads(str(run_row[10]))),
            source_status=tuple(
                dict(item) for item in json.loads(str(run_row[11]))
            ),
            zotero_context=dict(json.loads(str(run_row[12]))),
            diagnostics=dict(json.loads(str(run_row[13]))),
            recommendations=recommendations,
            verified_alternatives=alternatives,
        )

    def update_paper_research_review(
        self,
        recommendation_id: str,
        review_status: str,
    ) -> PaperResearchReviewResult | None:
        if review_status not in {"new", "seen", "interested", "dismissed"}:
            raise ValueError("invalid paper research review status")
        self.ensure_schema()
        with sqlite3.connect(self._database_path) as connection:
            cursor = connection.execute(
                """
                UPDATE news_paper_research_recommendations
                SET review_status = ?
                WHERE id = ?
                """,
                (review_status, recommendation_id),
            )
            connection.commit()
        if cursor.rowcount == 0:
            return None
        return PaperResearchReviewResult(
            recommendation_id=recommendation_id,
            review_status=review_status,
        )

    def topics_match(self, topics: Iterable[Topic]) -> bool:
        self.ensure_schema()
        expected = sorted(
            (
                topic.id,
                topic.name,
                _json(topic.keywords),
                _json(topic.negative_keywords),
                _json(topic.enabled_sources),
            )
            for topic in topics
        )
        with sqlite3.connect(self._database_path) as connection:
            persisted = connection.execute(
                """
                SELECT id, name, keywords_json, negative_keywords_json, enabled_sources_json
                FROM news_topics
                ORDER BY id
                """
            ).fetchall()
        return persisted == expected

    def save_refresh(
        self,
        *,
        items: Iterable[FeedItem],
        topics: Iterable[Topic],
        item_topics: Mapping[str, Iterable[str]],
        source_slots: Mapping[str, str] | None = None,
        item_types: Iterable[FeedItemType] | None = None,
    ) -> int:
        self.ensure_schema()
        feed_items = tuple(items)
        topic_items = tuple(topics)
        refreshed_types = None if item_types is None else tuple(dict.fromkeys(item_types))

        with sqlite3.connect(self._database_path) as connection:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.executemany(
                    """
                    INSERT INTO news_topics
                        (id, name, keywords_json, negative_keywords_json, enabled_sources_json)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        name = excluded.name,
                        keywords_json = excluded.keywords_json,
                        negative_keywords_json = excluded.negative_keywords_json,
                        enabled_sources_json = excluded.enabled_sources_json
                    """,
                    (
                        (
                            topic.id,
                            topic.name,
                            _json(topic.keywords),
                            _json(topic.negative_keywords),
                            _json(topic.enabled_sources),
                        )
                        for topic in topic_items
                    ),
                )
                topic_ids = tuple(topic.id for topic in topic_items)
                if topic_ids:
                    placeholders = ", ".join("?" for _ in topic_ids)
                    connection.execute(
                        f"DELETE FROM news_topics WHERE id NOT IN ({placeholders})",
                        topic_ids,
                    )
                else:
                    connection.execute("DELETE FROM news_topics")
                connection.executemany(
                    """
                    INSERT INTO news_feed_items
                        (id, type, source, title, summary, url, authors_json, published_at, fetched_at, metadata_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        type = excluded.type,
                        source = excluded.source,
                        title = excluded.title,
                        summary = excluded.summary,
                        url = excluded.url,
                        authors_json = excluded.authors_json,
                        published_at = excluded.published_at,
                        fetched_at = excluded.fetched_at,
                        metadata_json = excluded.metadata_json
                    """,
                    (
                        (
                            item.id,
                            item.type.value,
                            item.source,
                            item.title,
                            item.summary,
                            item.url,
                            _json(item.authors),
                            item.published_at,
                            item.fetched_at,
                            _json(item.metadata),
                        )
                        for item in feed_items
                    ),
                )
                item_ids = tuple(item.id for item in feed_items)
                if refreshed_types is None:
                    if item_ids:
                        placeholders = ", ".join("?" for _ in item_ids)
                        connection.execute(
                            f"DELETE FROM news_feed_items WHERE id NOT IN ({placeholders})",
                            item_ids,
                        )
                    else:
                        connection.execute("DELETE FROM news_feed_items")
                elif refreshed_types:
                    type_values = tuple(item_type.value for item_type in refreshed_types)
                    type_placeholders = ", ".join("?" for _ in type_values)
                    if item_ids:
                        item_placeholders = ", ".join("?" for _ in item_ids)
                        connection.execute(
                            f"DELETE FROM news_feed_items "
                            f"WHERE type IN ({type_placeholders}) "
                            f"AND id NOT IN ({item_placeholders})",
                            (*type_values, *item_ids),
                        )
                    else:
                        connection.execute(
                            f"DELETE FROM news_feed_items WHERE type IN ({type_placeholders})",
                            type_values,
                        )
                connection.executemany(
                    "DELETE FROM news_item_topics WHERE item_id = ?",
                    ((item.id,) for item in feed_items),
                )
                connection.executemany(
                    "INSERT INTO news_item_topics (item_id, topic_id) VALUES (?, ?)",
                    (
                        (item.id, topic_id)
                        for item in feed_items
                        for topic_id in item_topics.get(item.id, ())
                    ),
                )
                connection.executemany(
                    """
                    INSERT INTO news_source_state (source, last_successful_refresh_slot)
                    VALUES (?, ?)
                    ON CONFLICT(source) DO UPDATE SET
                        last_successful_refresh_slot = excluded.last_successful_refresh_slot
                    """,
                    tuple((source, slot) for source, slot in (source_slots or {}).items()),
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        return len(feed_items)

    def list_feed(
        self,
        *,
        item_type: FeedItemType | None = None,
        topic_id: str | None = None,
        period: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> FeedPage:
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        if offset < 0:
            raise ValueError("offset must be non-negative")
        self.ensure_schema()

        where, parameters = _feed_filter(
            item_type=item_type,
            topic_id=topic_id,
            period=period,
        )
        rank_order = (
            """
                    CASE
                        WHEN json_type(item.metadata_json, '$.rank') IN ('integer', 'real') THEN 0
                        ELSE 1
                    END,
                    CASE
                        WHEN json_type(item.metadata_json, '$.rank') IN ('integer', 'real')
                        THEN json_extract(item.metadata_json, '$.rank')
                    END,
            """
            if item_type is not None
            else ""
        )
        with sqlite3.connect(self._database_path) as connection:
            total = connection.execute(
                f"SELECT COUNT(*) FROM news_feed_items AS item {where}",
                parameters,
            ).fetchone()[0]
            rows = connection.execute(
                f"""
                SELECT
                    item.id, item.type, item.source, item.title, item.summary, item.url,
                    item.authors_json, item.published_at, item.fetched_at, item.metadata_json,
                    COALESCE(state.read, 0), COALESCE(state.saved, 0), COALESCE(state.hidden, 0)
                FROM news_feed_items AS item
                LEFT JOIN news_user_state AS state ON state.item_id = item.id
                {where}
                ORDER BY
                    {rank_order}
                    COALESCE(item.published_at, item.fetched_at) DESC,
                    item.id
                LIMIT ? OFFSET ?
                """,
                (*parameters, limit, offset),
            ).fetchall()
            topic_map = _topics_by_item(connection, tuple(row[0] for row in rows))

        return FeedPage(
            items=tuple(_item_from_row(row, topic_map.get(row[0], ())) for row in rows),
            total=total,
            limit=limit,
            offset=offset,
        )


def _feed_filter(
    *,
    item_type: FeedItemType | None,
    topic_id: str | None,
    period: str | None,
) -> tuple[str, tuple[object, ...]]:
    clauses: list[str] = []
    parameters: list[object] = []
    if item_type is not None:
        clauses.append("item.type = ?")
        parameters.append(item_type.value)
    if topic_id is not None:
        clauses.append(
            "EXISTS (SELECT 1 FROM news_item_topics AS match "
            "WHERE match.item_id = item.id AND match.topic_id = ?)"
        )
        parameters.append(topic_id)
    if period is not None:
        clauses.append("json_extract(item.metadata_json, '$.period') = ?")
        parameters.append(period)
    return (f"WHERE {' AND '.join(clauses)}" if clauses else "", tuple(parameters))


def _topics_by_item(
    connection: sqlite3.Connection,
    item_ids: tuple[str, ...],
) -> dict[str, tuple[str, ...]]:
    if not item_ids:
        return {}
    placeholders = ", ".join("?" for _ in item_ids)
    rows = connection.execute(
        f"""
        SELECT item_id, topic_id
        FROM news_item_topics
        WHERE item_id IN ({placeholders})
        ORDER BY topic_id
        """,
        item_ids,
    ).fetchall()
    result: dict[str, list[str]] = {}
    for item_id, topic_id in rows:
        result.setdefault(item_id, []).append(topic_id)
    return {item_id: tuple(topic_ids) for item_id, topic_ids in result.items()}


def _item_from_row(row: tuple[object, ...], topics: tuple[str, ...]) -> FeedItem:
    return FeedItem(
        id=str(row[0]),
        type=FeedItemType(str(row[1])),
        source=str(row[2]),
        title=str(row[3]),
        summary=str(row[4]) if row[4] is not None else None,
        url=str(row[5]),
        authors=tuple(json.loads(str(row[6]))),
        published_at=str(row[7]) if row[7] is not None else None,
        fetched_at=str(row[8]) if row[8] is not None else None,
        topics=topics,
        metadata=dict(json.loads(str(row[9]))),
        read=bool(row[10]),
        saved=bool(row[11]),
        hidden=bool(row[12]),
    )


def _upsert_research_paper(
    connection: sqlite3.Connection,
    paper: PaperResearchPaperInput,
    updated_at: str,
) -> tuple[str, bool]:
    title_key = canonical_title(paper.title)
    fallback_key = canonical_title_year(paper.title, paper.published_at)
    matches: set[str] = set()
    for column, value in (
        ("doi", paper.doi),
        ("arxiv_id", paper.arxiv_id),
        ("canonical_title", title_key),
        ("openalex_id", paper.openalex_id),
        ("canonical_title_year", fallback_key),
    ):
        if value is None:
            continue
        rows = connection.execute(
            f"SELECT id FROM news_papers WHERE {column} = ?",
            (value,),
        ).fetchall()
        matches.update(str(row[0]) for row in rows)
    if len(matches) > 1:
        raise PaperResearchIdentityConflictError(
            "Paper identifiers resolve to multiple existing papers"
        )

    if not matches:
        paper_id = f"research-paper:{uuid4()}"
        connection.execute(
            """
            INSERT INTO news_papers (
                id, title, authors_json, doi, arxiv_id, openalex_id,
                canonical_title, canonical_title_year, published_at, venue,
                publication_type, url, pdf_url, abstract, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                paper_id,
                paper.title,
                _json(paper.authors),
                paper.doi,
                paper.arxiv_id,
                paper.openalex_id,
                title_key,
                fallback_key,
                paper.published_at,
                paper.venue,
                paper.publication_type,
                paper.url,
                paper.pdf_url,
                paper.abstract,
                updated_at,
                updated_at,
            ),
        )
        return paper_id, True

    paper_id = next(iter(matches))
    existing = connection.execute(
        "SELECT doi, arxiv_id, openalex_id FROM news_papers WHERE id = ?",
        (paper_id,),
    ).fetchone()
    assert existing is not None
    existing_doi = str(existing[0]) if existing[0] is not None else None
    existing_arxiv_id = str(existing[1]) if existing[1] is not None else None
    preferred_doi = _preferred_doi(existing_doi, paper.doi)
    preferred_arxiv_id = _preferred_arxiv_id(
        existing_arxiv_id,
        paper.arxiv_id,
        existing_doi=existing_doi,
        incoming_doi=paper.doi,
    )
    existing_openalex_id = str(existing[2]) if existing[2] is not None else None
    if (
        existing_openalex_id is not None
        and paper.openalex_id is not None
        and existing_openalex_id != paper.openalex_id
    ):
        raise PaperResearchIdentityConflictError(
            "Incoming OpenAlex id conflicts with the existing paper"
        )
    connection.execute(
        """
        UPDATE news_papers
        SET title = ?,
            authors_json = CASE WHEN ? = '[]' THEN authors_json ELSE ? END,
            doi = ?,
            arxiv_id = ?,
            openalex_id = COALESCE(?, openalex_id),
            canonical_title = ?,
            canonical_title_year = ?,
            published_at = COALESCE(?, published_at),
            venue = COALESCE(?, venue),
            publication_type = COALESCE(?, publication_type),
            url = COALESCE(?, url),
            pdf_url = COALESCE(?, pdf_url),
            abstract = COALESCE(?, abstract),
            updated_at = ?
        WHERE id = ?
        """,
        (
            paper.title,
            _json(paper.authors),
            _json(paper.authors),
            preferred_doi,
            preferred_arxiv_id,
            paper.openalex_id,
            title_key,
            fallback_key,
            paper.published_at,
            paper.venue,
            paper.publication_type,
            paper.url,
            paper.pdf_url,
            paper.abstract,
            updated_at,
            paper_id,
        ),
    )
    return paper_id, False


def _preferred_arxiv_id(
    existing: str | None,
    incoming: str | None,
    *,
    existing_doi: str | None,
    incoming_doi: str | None,
) -> str | None:
    if existing is None:
        return incoming
    if incoming is None or incoming == existing:
        return existing
    same_formal_doi = (
        existing_doi is not None
        and incoming_doi is not None
        and existing_doi == incoming_doi
        and not existing_doi.casefold().startswith("10.48550/arxiv.")
    )
    if same_formal_doi:
        return incoming
    raise PaperResearchIdentityConflictError(
        "Incoming arXiv id conflicts with the existing paper"
    )


def _preferred_doi(existing: str | None, incoming: str | None) -> str | None:
    if existing is None:
        return incoming
    if incoming is None or incoming == existing:
        return existing
    existing_is_arxiv = existing.casefold().startswith("10.48550/arxiv.")
    incoming_is_arxiv = incoming.casefold().startswith("10.48550/arxiv.")
    if existing_is_arxiv and not incoming_is_arxiv:
        return incoming
    if incoming_is_arxiv and not existing_is_arxiv:
        return existing
    raise PaperResearchIdentityConflictError(
        "Incoming DOI conflicts with the existing paper"
    )


def _radar_item(row: tuple[object, ...]) -> PaperResearchRadarItem:
    evidence = dict(json.loads(str(row[22])))
    doi = str(row[6]) if row[6] is not None else None
    arxiv_id = str(row[7]) if row[7] is not None else None
    url = (
        str(row[11])
        if row[11] is not None
        else str(evidence.get("primary_url"))
        if evidence.get("primary_url")
        else f"https://doi.org/{doi}"
        if doi
        else f"https://arxiv.org/abs/{arxiv_id}"
    )
    return PaperResearchRadarItem(
        recommendation_id=str(row[0]),
        paper_id=str(row[1]),
        selection_kind=str(row[2]),
        selection_rank=int(row[3]) if row[3] is not None else None,
        title=str(row[4]),
        authors=tuple(json.loads(str(row[5]))),
        doi=doi,
        arxiv_id=arxiv_id,
        published_at=str(row[8]) if row[8] is not None else None,
        venue=str(row[9]) if row[9] is not None else None,
        publication_type=str(row[10]) if row[10] is not None else None,
        url=url,
        ai_summary=str(row[12]),
        recommendation_reason=str(row[13]),
        relevance_score=float(row[14]) if row[14] is not None else None,
        novelty_score=float(row[15]) if row[15] is not None else None,
        scientific_value_score=float(row[16]) if row[16] is not None else None,
        recency_score=float(row[17]) if row[17] is not None else None,
        overall_score=float(row[18]) if row[18] is not None else None,
        relationship_to_library=str(row[19]) if row[19] is not None else None,
        zotero_relationship=dict(json.loads(str(row[20]))),
        date_evidence=dict(json.loads(str(row[21]))),
        evidence=evidence,
        source=dict(json.loads(str(row[23]))),
        review_status=str(row[24]),
    )


def _research_feed_item(row: tuple[object, ...]) -> FeedItem:
    doi = str(row[3]) if row[3] is not None else None
    arxiv_id = str(row[4]) if row[4] is not None else None
    openalex_id = str(row[5]) if row[5] is not None else None
    url = (
        str(row[8])
        if row[8] is not None
        else str(row[9])
        if row[9] is not None
        else f"https://doi.org/{doi}"
        if doi
        else f"https://arxiv.org/abs/{arxiv_id}"
        if arxiv_id
        else f"https://openalex.org/{openalex_id}"
    )
    topics = tuple(json.loads(str(row[15])))
    matched_topics = tuple(json.loads(str(row[16])))
    return FeedItem(
        id=f"research:{row[0]}",
        type=FeedItemType.PAPER,
        source="research",
        title=str(row[1]),
        summary=str(row[11]),
        url=url,
        authors=tuple(json.loads(str(row[2]))),
        published_at=str(row[6]) if row[6] is not None else None,
        fetched_at=str(row[24]),
        topics=topics,
        metadata={
            "summary_kind": "ai",
            "research_kind": "ai_research",
            "recommendation_reason": str(row[12]),
            "relevance_score": float(row[13]) if row[13] is not None else None,
            "novelty_score": float(row[14]) if row[14] is not None else None,
            "matched_topics": list(matched_topics),
            "relationship_to_library": str(row[17]) if row[17] is not None else None,
            "source": dict(json.loads(str(row[18]))),
            "venue": str(row[7]) if row[7] is not None else None,
            "doi": doi,
            "arxiv_id": arxiv_id,
            "openalex_id": openalex_id,
            "pdf_url": str(row[9]) if row[9] is not None else None,
            "abstract": str(row[10]) if row[10] is not None else None,
            "research_run": {
                "id": str(row[19]),
                "task_key": str(row[20]),
                "run_key": str(row[21]),
                "schema_version": str(row[22]),
                "generated_at": str(row[23]),
                "ingested_at": str(row[24]),
                "agent_type": str(row[25]),
                "agent_model": str(row[26]),
                "prompt_version": str(row[27]),
                "query_plan": list(json.loads(str(row[28]))),
            },
        },
    )


def _ensure_schema_v4(connection: sqlite3.Connection) -> None:
    columns = {
        "news_papers": (
            "canonical_title TEXT",
            "publication_type TEXT",
        ),
        "news_paper_research_runs": (
            "run_kind TEXT NOT NULL DEFAULT 'paper_research'",
            "ingest_identity TEXT",
            "payload_digest TEXT",
            "profile_json TEXT NOT NULL DEFAULT '{}'",
            "search_window_json TEXT NOT NULL DEFAULT '{}'",
            "candidate_count INTEGER",
            "verified_candidate_count INTEGER",
            "recommended_count INTEGER",
            "warnings_json TEXT NOT NULL DEFAULT '[]'",
            "source_status_json TEXT NOT NULL DEFAULT '[]'",
            "zotero_context_json TEXT NOT NULL DEFAULT '{}'",
            "diagnostics_json TEXT NOT NULL DEFAULT '{}'",
        ),
        "news_paper_research_recommendations": (
            "scientific_value_score REAL",
            "recency_score REAL",
            "overall_score REAL",
            "selection_kind TEXT NOT NULL DEFAULT 'recommended'",
            "selection_rank INTEGER",
            "date_evidence_json TEXT NOT NULL DEFAULT '{}'",
            "zotero_relationship_json TEXT NOT NULL DEFAULT '{}'",
            "evidence_json TEXT NOT NULL DEFAULT '{}'",
            "review_status TEXT NOT NULL DEFAULT 'new'",
        ),
    }
    for table, definitions in columns.items():
        existing = {
            str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")
        }
        for definition in definitions:
            name = definition.split(maxsplit=1)[0]
            if name not in existing:
                connection.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")
                existing.add(name)
    rows = connection.execute(
        "SELECT id, title FROM news_papers WHERE canonical_title IS NULL"
    ).fetchall()
    connection.executemany(
        "UPDATE news_papers SET canonical_title = ? WHERE id = ?",
        ((canonical_title(str(title)), str(paper_id)) for paper_id, title in rows),
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _sqlite_path(database_url: str) -> str:
    prefix = "sqlite:///"
    if not database_url.startswith(prefix):
        raise ValueError("News cache requires a sqlite:/// database URL")
    return database_url.removeprefix(prefix)
