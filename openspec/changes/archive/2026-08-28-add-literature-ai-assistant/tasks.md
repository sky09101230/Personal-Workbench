## 1. Contracts and persistence

- [x] 1.1 Add Literature AI and user-note dataclasses, stable errors, application schemas, prompt versions, and provider/context/repository ports.
- [x] 1.2 Advance the Literature SQLite schema to version 3 with AI analyses, conversations, messages, page text cache, and local user notes while preserving existing data.
- [x] 1.3 Implement repository methods and migration tests proving Zotero sync does not remove AI state or My Notes.

## 2. Context and provider infrastructure

- [x] 2.1 Add the bounded `pypdf` page extractor and PaperContextBuilder with metadata-only, representative-page, lexical retrieval, conversation, and selection strategies.
- [x] 2.2 Implement the Literature-local DeepSeek provider with JSON Output, safe error mapping, prompt/model provenance, and no credential leakage.
- [x] 2.3 Cover provider and context behavior for success, timeouts, HTTP/rate-limit failures, invalid output, long/empty PDFs, retrieval, and selection neighbors.

## 3. Application and API

- [x] 3.1 Implement `LiteratureAIService` for cached/regenerated Overview and Deep Read, conversations and Ask Paper, and four selection actions.
- [x] 3.2 Implement local My Notes creation and explicit Add to Notes from paper-owned analyses or assistant messages.
- [x] 3.3 Add typed Literature AI and user-note routes, compose dependencies in `app/main.py`, and map stable errors to HTTP responses.
- [x] 3.4 Add service and endpoint tests for persistence, missing configuration/resources/context, duplicate analysis requests, and existing Literature regressions.

## 4. Reader experience

- [x] 4.1 Add a selectable PDF.js text layer and bounded selection-context wiring without changing existing PDF navigation or download behavior.
- [x] 4.2 Add the collapsible Zotero Notes / My Notes / AI Assistant sidebar with persisted analyses, conversation, selection actions, loading, retry, copy, and explicit Add to Notes states.
- [x] 4.3 Update typed frontend contracts and scoped styles, then verify TypeScript compilation and the production build.

## 5. Final verification

- [x] 5.1 Run focused and full backend tests, frontend build, strict OpenSpec validation, and `git diff --check`.
- [x] 5.2 Review the complete diff for credential safety, prompt placement, note-write explicitness, scope creep, and Activity path isolation.
- [x] 5.3 Prefer the main paper when a Zotero item also contains filename-marked supplementary PDFs, and repeat the live Reader/context acceptance.
