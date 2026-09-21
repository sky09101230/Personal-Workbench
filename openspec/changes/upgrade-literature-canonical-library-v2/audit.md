# Literature V2 Current-State Audit

Audited 2026-09-21 against main `7354657`, before production edits. Backend baseline: 191 tests pass. Reference: PLAB-Scientific-Agent commit `a04646aa5e5fc13502fd1918f2932f2598e628bd` (read-only Git copy).

## Architecture and ownership

FastAPI composition in `app/main.py` constructs LiteratureService, SQLiteLiteratureRepository, ZoteroWebProvider, LiteratureAIService and PaperContextBuilder. Application ports are Protocols; dataclass domain objects carry one optional external_ref. The provider is read-only. No modules may import another module or read its tables. News owns Radar independently; the browser currently presents Radar inside News.

`Paper.id`, Collection.id, Note.id and Attachment.id are constructed by the Zotero adapter as `zotero:<library>:<key>`. The repository treats those IDs as primary keys. External references exist, but are a projection of source identity, not an independent literature identity. A Paper supports only one reference and no reading state, provenance, origins, or asset roles.

## Schema and real database

The configured local database is `data/workbench.db`. SQLite integrity check is `ok`; foreign_key_check is empty. Literature uses the historical unprefixed `schema_migrations` table (versions 1–3); News uses news_schema_migrations v4. Other modules own their own migrations.

| Existing table / data | Count | Ownership and migration concern |
| --- | ---: | --- |
| literature_papers | 59 | Source IDs; metadata has no per-field evidence |
| literature_collections | 14 | Source IDs; self-FK is deferred |
| literature_collection_papers | 61 | Paper/collection CASCADE FKs |
| literature_tags | 72 | Source tags; paper CASCADE |
| literature_notes | 66 | Notes/annotations; paper CASCADE |
| literature_attachments | 83 | Metadata only, no local file storage; paper CASCADE |
| literature_external_references | 222 | Polymorphic logical references; unique source tuple |
| literature_library_state | 1 | Connector version and success/error state |
| literature_ai_analyses | 1 | Logical paper_id, no paper FK |
| literature_ai_conversations / messages | 0 / 0 | Conversation → paper logical; messages → conversation CASCADE |
| literature_ai_paper_text | 9 | Composite paper/page key; extraction version |
| literature_user_notes | 2 | Logical paper_id; content must survive |
| news_papers / research_runs / recommendations | 29 / 6 / 65 | Retain all history and review state |

Migration v1 creates metadata, memberships, tags and references. V2 adds annotation kind/page/color and attachment link_mode, clears connector version once to force asset backfill. V3 adds AI analyses/conversations/messages/text and native notes. ensure_schema executes migrations under BEGIN IMMEDIATE with rollback. No V2 canonical migration exists.

## Sync and deletion hazards

LiteratureService.full_sync reads top-level and per-collection pages, deduplicates by source ID, obtains notes/assets, then calls replace_library. That method deletes ALL metadata, references, memberships, connector state and source resources, then inserts a complete snapshot in one transaction. AI tables survive physically, but may become inaccessible when their paper disappears. Incremental sync calls list_changes using persisted library_version. The provider combines changed collections/items/assets and deleted/trashed IDs. apply_changes updates source metadata unconditionally, replaces tags/membership, deletes removed papers, and cascades resources. These operations must never target canonical ownership.

Provider assets resolve annotation parents through attachment lookup, fetching missing parents when needed. Attachments are downloadable only for PDFs in imported_file/imported_url modes. File opening validates provider/library and forwards Range; redirects omit Zotero credentials. Preserve this adapter behavior. The top-level page loop uses returned filtered item count, an existing assumption to keep under regression coverage.

## Reader and AI

Reader route is `/literature/papers/<opaque-id>/reader`; API paths use encodeURIComponent. PDF stream/download share LiteratureService.open_pdf, selecting a nonsupplementary PDF first. Range metadata and stream close callback are forwarded. There is no persisted browser reading-page state/localStorage in PdfReaderPage.

Overview, Deep Read, Selection, Ask and My Notes validate get_paper but continue using the requested old ID. Conversation ownership compares string IDs. Therefore alias resolution MUST precede every AI operation, including resource-ownership comparisons. Existing conversation/message/analysis/note IDs must stay stable. Page cache is keyed by paper, not file; introducing multiple assets requires binding cache validity to selected asset. Current extractor uses pypdf, bounded text, representative pages, lexical chunk retrieval; reuse it rather than introduce a processing platform. Existing AI UI lives in Reader; metadata-only papers need access to it from detail.

## Frontend

App.tsx routes by pathname; LiteraturePage reads cached collections/filters/papers and synchronizes Zotero. Empty states and header equate Library availability with provider configuration. PaperInspector exposes metadata, read-only Zotero Notes and attachment availability; no native reading status/collection management. PaperPane has title/authors/venue/year/tags. These are reusable with canonical IDs and additive contracts. Existing source collection IDs need aliases during transition.

## Radar and Agent

News separates papers, research runs, and recommendation judgments. V4 records rank, selection kind, five scores, date/source/evidence/relationship JSON, review status, run diagnostics, source statuses and ingest digest. `POST /api/news/papers/research/ingest` accepts v1/v2; latest Radar and review PATCH remain independent. News resolver normalizes DOI/arXiv/OpenAlex and title, collects matches and rejects multiple identities; title matching is broader than safe canonical matching. It can prefer a formal DOI over arXiv DOI and correct arXiv under equal formal DOI. Reuse concepts, NOT a cross-module import or unguarded title merge.

There is no apps/agent in this checkout. Actual Agent lives in sibling `Personal-Workbench-Agent`. Its literature.py validates V0.1 artifacts, maps them to schema `2`, uses digest-based ingest_identity and posts through client.py to the existing News endpoint. Daily automation `daily-literature-radar` is ACTIVE at 07:30 in that separate project. This upgrade neither edits it nor runs discovery. Save must be explicit, persistent and idempotent; unsaved candidates must never enter canonical tables.

## Reference architecture assessment

Reviewed all seven requested PLAB files. CanonicalDocument owns metadata/status/evidence; ExternalReference has a unique source tuple; UploadedDocument independently carries hash, storage, file role and relationship evidence. Ingestion validates PDF and deduplicates file association transactionally. Zotero merges missing fields and records evidence. DocumentProcessingJob → DocumentParse → LiteratureChunk / DocumentAnalysis preserves parser/prompt versions and file lineage; storage_layout supports dry-run, collision reporting and recovery. Workbench should use stdlib SQLite transactions, existing pypdf and ports, not copy Django workers, multi-user uploaders, or NAS implementation. A file hash identifies bytes, not universal scholarly identity.

## Proposed target and compatibility

Add canonical-owned tables alongside untouched legacy source snapshots. A canonical repository implements existing read/sync ports and reuses AI persistence. Source sync resolves identity, updates scoped references/evidence/resources and marks missing references detached. Legacy IDs map via durable aliases; canonical IDs are opaque Workbench UUIDs. Imported collections receive native IDs and a separate source mapping. Radar export is supplied through an injected callable wired at composition root, with News reading only News tables and Literature only Literature tables. Manual PDF uses the same ingestion model with a file store port. Migration preserves all old metadata tables and original AI rows in an audit snapshot before canonical rebinding; collisions are preserved/reported, never silently merged. See design.md for phases and rollback.
