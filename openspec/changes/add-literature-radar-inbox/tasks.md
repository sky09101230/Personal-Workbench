## 1. Contract and persistence

- [x] Audit existing Phase 1 Research schema, repository, service, router, tests, and Papers UI.
- [x] Define a backward-compatible schema v2 mapping for Literature Radar V0.1.
- [x] Add News schema v4 columns/indexes without parallel Radar tables.
- [x] Implement stable ingest identity, normalized payload digest, exact replay, and conflict handling.
- [x] Implement DOI/arXiv/canonical-title paper reuse and formal DOI upgrade.
- [x] Add latest Radar run query and persistent review PATCH.
- [x] Add representative synthetic schema v2 fixture and backend acceptance tests.

## 2. Radar UI

- [x] Add Papers Feed/Radar switch and Radar Inbox component.
- [x] Show run summary, source health, warnings, recommendations, alternatives, diagnostics, and review controls.
- [x] Verify production frontend build and browser behavior.

## 3. Agent transport

- [x] Add validator-gated Literature Radar mapper and manual ingest service.
- [x] Add `workbench-agent literature ingest <result.json>` with config/.env transport.
- [x] Add CLI/client/mapping tests and documentation.

## 4. End-to-end acceptance

- [x] Run both complete regression suites and static checks.
- [x] Ingest the real V0.1 output twice through HTTP and confirm stable SQLite counts.
- [x] Restart/recreate backend and refresh browser to confirm persistence.
- [x] Commit and push both feature branches independently.

