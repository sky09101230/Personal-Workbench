## Context

Literature already owns provider-neutral Paper, Note, and Attachment models, reads from a module-owned SQLite cache, proxies Zotero PDFs through the backend, and renders one PDF page at a time with PDF.js. Zotero Notes are synchronized read-only. DeepSeek configuration already exists for News and Todo, but those modules remain independent and their implementations cannot be reused through cross-module imports.

The AI assistant is a synchronous, explicitly triggered feature for one local user. It must work with metadata-only papers, extract useful text from ordinary PDFs, fail clearly for scanned PDFs without OCR, preserve provenance, and never write to Zotero or Activity.

## Goals / Non-Goals

**Goals:**

- Add Literature-local provider, context, repository, and service abstractions for AI reading.
- Produce schema-validated Overview, Deep Read, Ask Paper, and selection results with model and prompt-version provenance.
- Cache normalized PDF text by page and construct deterministic, bounded task contexts.
- Persist analyses and paper-bound conversations, and reuse existing analyses unless the user explicitly retries.
- Add local My Notes that receive AI content only through an explicit user action.
- Enhance the existing Reader without turning Literature into a general chat surface.

**Non-Goals:**

- Activity or Project Activity changes or dependencies.
- Todo, News, Project, or global AI abstractions.
- Zotero write-back, OCR, embeddings, vector databases, cross-paper RAG, knowledge graphs, agents, or background batch generation.

## Decisions

### Literature owns the complete AI boundary

`LiteratureAIService` depends on three application Protocols: `LiteratureAIProvider`, `PaperContextProvider`, and `LiteratureAIRepository`. `DeepSeekProvider`, `PaperContextBuilder`, and the SQLite implementation live under Literature infrastructure and are assembled in `app/main.py` as `app.state.literature_ai_service`.

This repeats a small amount of provider plumbing already present in News and Todo, but preserves the repository rule that modules do not import one another. A global LLM client is rejected until multiple modules have a stable shared contract.

### JSON output is validated into dataclasses

Prompts are centralized and versioned as `overview_v1`, `deep_read_v1`, `ask_paper_v1`, and one version for each selection action. DeepSeek requests use JSON Output, explicitly instruct the model to return JSON, and disable streaming. Application parsers validate required keys and value types into dataclasses; provider response shape, JSON syntax, and application schema failures become stable Literature AI errors.

Overview and Deep Read use different prompts and schemas. Ask Paper returns paper evidence, AI interpretation, and uncertainty separately, and must state when supplied context is insufficient.

### PDF text is extracted and cached per page

The context builder obtains the existing protected PDF stream through `LiteratureService`, enforces a 50 MiB input bound, extracts each page with `pypdf`, normalizes whitespace, and stores non-empty page text with extractor/version metadata. The cache is keyed by paper and page and is independent from Zotero note replacement. A PDF with no extractable page text raises a stable no-text error; OCR is not attempted. Metadata and abstract remain available for Overview and Deep Read even when PDF extraction is unavailable.

When a Zotero parent item has multiple downloadable PDFs, `LiteratureService` keeps the selection deterministic but ranks filenames explicitly marked as supplementary, supporting information, MOESM, or ESM after ordinary PDFs. This prevents a supplement from silently replacing the main paper without adding provider-specific attachment selection to the Reader. The extractor version changes with attachment-selection semantics, and `PaperContextBuilder` replaces mismatched cached pages before building Overview or Ask Paper context.

### Context selection is deterministic and bounded

- Overview includes metadata and abstract, then first pages, last pages, and evenly spaced middle pages up to an 80,000-character text budget.
- Deep Read applies the same representative-page policy with a 160,000-character budget.
- Ask Paper divides page text into 2,000-character chunks with 250-character overlap, tokenizes Latin terms plus CJK characters/bigrams, ranks chunks by query overlap, and includes at most eight chunks and the eight most recent bounded messages.
- Selection sends only the selected text, page number, at most 2,000 characters before and after the selection, and an optional question. The backend validates all request limits and never reloads the full paper for a selection action.

Character budgets are intentionally transparent and dependency-free. They control cost and latency without claiming token-perfect accounting.

### One SQLite migration owns all Literature AI state

The Literature schema advances from version 2 to version 3 and adds `literature_ai_analyses`, `literature_ai_conversations`, `literature_ai_messages`, `literature_ai_paper_text`, and `literature_user_notes`. Existing metadata tables are not rebuilt. Full and incremental Zotero sync continue replacing only Zotero-owned tables, so AI data and My Notes survive.

One-shot outputs, including selection results, are stored as analyses. Assistant messages store model and prompt version; user messages store neither. API ids remain opaque UUIDs. Existing Overview or Deep Read is returned by default; an explicit retry/regenerate flag creates a new analysis.

### My Notes are local and explicit

`literature_notes` remains the exact synchronized Zotero source. `literature_user_notes` stores local content and a small source enum (`manual`, `ai_overview`, `ai_deep_read`, `ai_chat`, `ai_selection`). `Add to Notes` verifies that the referenced analysis or message belongs to the current paper, then copies its rendered content into a new local note. No AI operation calls this path automatically.

### Reader gains a selectable text layer and one auxiliary sidebar

PDF.js continues drawing the page canvas. A synchronized absolutely positioned text layer built from `getTextContent()` enables browser selection and supplies page-local neighboring text. The current right sidebar becomes tabs for Zotero Notes, My Notes, and AI Assistant; it remains collapsible, never opens AI automatically, and disables repeated buttons while a request is in flight.

## Risks / Trade-offs

- [PDF extraction can be slow or memory-heavy] → Bound PDF size, cache page text, close provider streams, and show explicit loading states.
- [Scanned or malformed PDFs have no text] → Return a stable no-extractable-text result while allowing metadata/abstract analysis.
- [Lexical retrieval misses semantic matches] → Include metadata/abstract and recent conversation, expose uncertainty, and defer embeddings to a future change.
- [Model JSON can be valid but semantically wrong] → Validate schemas, require evidence/inference separation, persist prompt/model provenance, and avoid automatic note creation.
- [Concurrent duplicate clicks can spend twice] → Reuse persisted Overview/Deep Read by default and disable per-action UI controls while requests are pending.
- [Activity branch also edits composition files] → Keep Literature edits localized to its imports/state/router and do not modify Activity paths or branch history.

## Migration Plan

1. Apply the idempotent version-3 Literature migration; existing rows remain untouched.
2. Deploy backend code with the existing DeepSeek environment settings and new `pypdf` dependency.
3. Deploy the Reader enhancement after API contract tests and TypeScript build pass.
4. If rollback is required, older code ignores the additive version-3 tables; no table deletion or data downgrade is performed.

## Open Questions

None for this phase. Zotero write-back, OCR, semantic retrieval, and cross-paper context require separate changes.
