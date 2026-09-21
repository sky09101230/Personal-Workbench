# Proposal

## Why

Zotero currently acts as the effective Literature database: source deletion removes a paper, metadata sync owns the library, and AI references source IDs. Workbench must own canonical literature identity so Zotero, reviewed Radar discoveries and PDF uploads converge without losing existing research data.

## What Changes

- Introduce Workbench canonical papers, external references, ingestion origins, independent assets and explainable metadata evidence.
- Migrate existing data additively with backup, dry-run, durable aliases, reports and rollback instructions; preserve legacy tables and AI content.
- Convert Zotero full/incremental sync to scoped connector ingestion; source removal detaches references and retains papers.
- Provide Library / Radar / Import navigation, native reading state, collections, source badges, PDF upload and explicit idempotent Save to Library.
- Bind Reader, AI and My Notes to canonical identity while accepting legacy IDs.
- Keep Radar ingestion, automation, history, review and News providers unchanged. DOI/URL enrichment is deferred to V2.1.

## Capabilities

### New Capabilities

- `canonical-literature-library`: Canonical ownership, identity, references, origins, evidence, migration, connector sync, assets and Library UI.

### Modified Capabilities

- `literature-ai-assistant`: Resolve aliases and bind analysis/conversation/text cache to canonical papers and selected assets.
- `literature-user-notes`: Preserve and rebind historical native notes to canonical identity.
- `paper-research-ingest`: Add explicit Library handoff without changing ingest/review ownership.

## Impact

Literature domain/application/infrastructure/presentation, composition root, additive News export read port, React Library/Reader/Radar UI and backend tests. SQLite canonical migration has independent versioning alongside legacy v1–v3. No new service, worker, ORM or frontend router. Existing REST read/AI/PDF paths remain valid; new ingestion/state/organization endpoints are additive.

Non-goals: Feedback learning, Project/Todo linking, Zotero write-back, knowledge/citation graphs, embeddings, cross-paper RAG, automatic assignment or automatic Zotero changes.
