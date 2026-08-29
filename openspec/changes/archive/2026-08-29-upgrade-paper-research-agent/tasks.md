## 1. Domain and Contract

- [x] 1.1 Add explicit Paper Research domain models, ingest result, and paged Feed projection types without changing existing FeedItem fields
- [x] 1.2 Add strict Pydantic request models and POST/GET News endpoints with contract validation tests

## 2. Persistence and Ingest

- [x] 2.1 Add News schema migration for Paper, Research Run, and Recommendation tables with required unique constraints and indexes
- [x] 2.2 Implement DOI/arXiv/OpenAlex normalization, fallback identity, and repository-level paper metadata upsert
- [x] 2.3 Implement atomic idempotent run/recommendation ingest and latest-recommendation query projection through repository ports and NewsService
- [x] 2.4 Add persistence, deduplication, rollback, idempotency, and historical recommendation tests

## 3. API and UI Integration

- [x] 3.1 Add API success, validation, replay, GET research feed, and persistence-recreation tests
- [x] 3.2 Merge Research results into the Papers view and render AI Research summary, reason, scores, provenance, and topics with scoped styling
- [x] 3.3 Verify existing GitHub Trending and OpenAlex API/card behavior remains unchanged

## 4. Real Acceptance and Quality

- [x] 4.1 Add a source-grounded five-real-paper Research JSON fixture and test its metadata contract
- [x] 4.2 Execute the fixture twice against on-disk SQLite, recreate the service, and record stable Run/Paper/Recommendation counts and recovered GET data
- [x] 4.3 Run the complete backend suite, Python compile check, frontend build/typecheck, available lint/test commands, and git diff checks
- [x] 4.4 Commit the focused implementation and report branch, commit, status, architecture, database, API, UI, verification, acceptance counts, and phase-two exclusions
