## Why

Literature can currently browse Zotero metadata, stream PDFs, and display read-only Zotero Notes, but it cannot turn the current paper into bounded, evidence-aware reading assistance. This change adds an explicit, user-triggered AI reading loop while keeping Activity isolated and preserving Zotero as a read-only provider.

## What Changes

- Add a Literature-owned, replaceable DeepSeek provider and application service for AI Overview, Deep Read, Ask Paper, and PDF-selection actions.
- Extract PDF text by page, cache it locally, and build task-specific bounded paper contexts without embeddings, vector databases, or cross-paper retrieval.
- Persist analyses, paper-bound conversations, messages, model identity, and prompt versions.
- Add local `My Notes` storage that is separate from synced Zotero Notes; AI content enters it only after an explicit `Add to Notes` action.
- Enhance the existing PDF Reader with selectable text and a collapsible Notes / My Notes / AI Assistant sidebar with loading, retry, and error states.
- Add backend provider, context, service, repository, API, migration, regression, and frontend build verification.

## Capabilities

### New Capabilities

- `literature-ai-assistant`: Evidence-aware, paper-bound AI analysis, conversation, PDF selection, context construction, persistence, and Reader UI behavior.
- `literature-user-notes`: Workbench-local paper notes, including explicit user-controlled copying of AI outputs, without Zotero write-back.

### Modified Capabilities

None.

## Impact

- Backend: `apps/api/app/modules/literature/`, the Literature composition in `apps/api/app/main.py`, and the Literature SQLite schema.
- Frontend: the existing Literature PDF Reader, Literature API contracts, and scoped Reader styles.
- Configuration: reuse existing `DEEPSEEK_API_KEY`, `DEEPSEEK_BASE_URL`, and `DEEPSEEK_MODEL`; `.env` remains untouched and browser code never receives credentials.
- Dependency: add a bounded server-side PDF text extractor based on `pypdf`.
- Scope exclusions: Activity and Project Activity, Todo, News, Zotero write-back, embeddings, vector databases, cross-paper RAG, knowledge graphs, global AI frameworks, agents or multi-agent workflows, and automatic batch AI processing.
