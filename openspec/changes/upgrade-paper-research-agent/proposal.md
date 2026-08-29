## Why

Personal Workbench currently discovers Papers only through bounded OpenAlex topic refreshes, so externally produced, structured research recommendations cannot be ingested with durable provenance or displayed without losing the distinction between objective paper metadata and run-specific AI judgment. This change establishes that receiving boundary now while keeping research execution and scheduling outside Workbench.

## What Changes

- Add a versioned, schema-validated Research Ingest contract under the News API.
- Persist objective Paper entities separately from Research Runs and run-specific Recommendations.
- Normalize DOI, arXiv, and OpenAlex identifiers and deduplicate papers while making repeated `(task_key, run_key)` submissions idempotent in one SQLite transaction.
- Add a read API that projects the latest recommendation per paper while preserving all historical recommendations.
- Extend the existing Papers UI minimally to identify AI Research results and show AI Summary, recommendation reason, scores, and topics without changing GitHub Trending behavior.
- Add contract, persistence, deduplication, idempotency, historical recommendation, API, regression, and five-real-paper acceptance coverage.
- Explicitly exclude Codex execution, Zotero access, scheduling, feedback, and ProjectActivity changes.

## Capabilities

### New Capabilities
- `paper-research-ingest`: Versioned external research-result ingestion, transactional SQLite provenance, paper identity deduplication, latest-recommendation querying, and AI Research presentation in the existing Papers area.

### Modified Capabilities

None.

## Impact

- Backend: News domain/application ports and service, News SQLite repository and schema migration, News FastAPI contracts/router, and application composition only as needed.
- Frontend: existing `/news` Papers data client, types, cards, and scoped styles only.
- API: adds `POST /api/news/papers/research/ingest` and `GET /api/news/papers/research`; existing News endpoints remain compatible.
- Data: adds only `news_*` tables and constraints in the shared SQLite database.
- Verification: backend regression suite, frontend build/typecheck through the existing build command, compile checks, diff checks, and repeatable five-paper persistence acceptance.
