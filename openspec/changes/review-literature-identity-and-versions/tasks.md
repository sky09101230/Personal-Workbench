# Tasks

## 1. Identity review backend

- [x] 1.1 Add backed-up schema version 4 and durable rejected-ingestion evidence; verify replay and unchanged canonical/research rows.
- [x] 1.2 Implement snapshot/evidence-checked identity confirmation/correction and conflict decisions; test stale requests, collision, quarantine/reopen and canonical-ID preservation.
- [x] 1.3 Implement evidence-backed version links/retraction without merging; test independent Notes/assets/identifiers and stale relation changes.
- [x] 1.4 Make Radar origins recommendation-scoped while retaining unverified grouped evidence; test weak-group isolation and explicit compatible saves.

## 2. UI and acceptance

- [x] 2.1 Add identity/conflict/version review controls and asset integrity indicators in existing Literature views; verify production build and disposable browser workflows.
- [x] 2.2 Audit/upgrade a real DB copy, preserve historical rows and inspect the eight orphan conflicts without deciding them automatically; record dry-run/replay/integrity evidence.
- [x] 2.3 Run full regression, strict OpenSpec validation and diff checks; document operations/acceptance, update roadmap and commit before asset acquisition.
