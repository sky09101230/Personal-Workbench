# Literature V2 Stage 1 / Stage 2 completion

2026-09-21. Continued from Gemini's `literature-v2-stage1-stage2-handshake.md` on `claude/literature-v2-backend-workflows`, based on `dcfeb06`. The original handoff is preserved as context; this document describes the delivered behavior and supersedes its provisional implementation claims.

## Completed scope

- Stage 1: independent sources/origins; explicit migration with read-only status, real dry-run, durable backups, retry/concurrency guards; additive workflow schema v2 for existing canonical libraries; explicit one-time saved-state reconciliation; staging/originals storage with hash/path validation and legacy flat-layout fallback.
- Stage 2: reviewable PDF upload batches, bounded local PDF metadata extraction, candidate edits, atomic per-item confirmation, conflict retry, cancellation and protected staging cleanup; metadata proposal accept/reject/edit with canonical aliases, stale checks, identity-index consistency and before/after provenance; selective Zotero import including source notes/annotations/attachments/collections; bounded local PDF materialization and per-paper batch outcomes.
- All services/routes are composed in main.py. Application workflows use typed ports and do not execute SQL, import infrastructure classes, inspect file paths or call private provider methods. SQLite operations live in `infrastructure/cache/workflows.py`; extraction is an injected infrastructure function.
- API contract frozen in [literature-v2-api.md](../contracts/literature-v2-api.md), covering A–G, request/response shapes, lifecycle, errors, idempotency, migration and compatibility. Upload/review/materialization responses are represented in OpenAPI.

## Important fixes to the inherited draft

1. Existing canonical v1 databases previously returned early and never received the new workflow tables; versioned DDL now upgrades them without replaying data migration.
2. A pending DDL-only migration previously broke on the second ensure_schema call. Pending reads/writes now consistently return migration_required, while explicit repeat/concurrent runs are safe. Library status/sync and AI also honor the guard.
3. Draft workflows wrote SQL and accessed private file/provider internals from application services. These responsibilities now cross explicit public ports.
4. Proposal edit-accept previously bypassed identifier checks and failed to update identifier lookup. All decisions now share validation, reject other-paper identifiers/formal DOI downgrades, recheck pending/stale state under lock, and update provenance and identifiers transactionally.
5. Confirming uploads previously finalized/deleted staging before separately writing status, leaving failed items unrecoverable. Originals publish atomically while staging survives until confirmed state commits; conflicts remain editable. Replay and concurrent confirmation do not create duplicate assets.
6. Materialization previously joined an unbounded stream, could omit close on failure, treated local supplementary PDFs as primary, and updated legacy IDs directly. It is bounded to 50 MiB, closes in finally, resolves canonical identity, checks source version, prefers local primary files, and returns stable errors.
7. PDF creation time and scanned reference DOIs are only low-confidence candidates, with warnings. Extraction never initiates network lookup or AI generation.

## Verification

- Full backend pytest: **225 passed** (209 baseline + 16 new workflow tests). One existing Starlette/httpx deprecation warning remains.
- compileall: passed for apps/api/app and apps/api/tests.
- OpenSpec strict validation: passed for upgrade-literature-canonical-library-v2.
- git diff --check: passed; final staged/branch secret scanning occurs before push.
- No frontend files changed; frontend build/browser work is not claimed for this backend-only continuation.

Real configured database was copied using SQLite backup. Workflow schema initialization preserved digests of all **49 existing tables**. API-level upload → candidate edit → confirm → metadata proposal accept → local PDF range response all passed. Database integrity was ok, with no FK errors.

Live external verification on a separate copy also passed: selected Zotero import returned already_exists for an existing canonical record, actual remote PDF was materialized locally, and the Reader service returned the local PDF range successfully. No Zotero mutation or real-library workflow decision was performed.

Local evidence (ignored temporary files):

- `.venv/tmp/literature-workflows-57q2ueg3/report.json`: isolated existing-DB/API verification.
- `.venv/tmp/literature-workflows-3iyn6u9_/report.json`: actual Zotero selective import and PDF materialization.

Repeatable command:

```powershell
$env:PYTHONPATH = 'apps/api'
.\.venv\Scripts\python.exe apps/api/tests/manual_literature_workflows.py
# Optional read-only remote Zotero verification; all persistence stays in a fresh DB copy:
.\.venv\Scripts\python.exe apps/api/tests/manual_literature_workflows.py --live-check
```

## Boundaries / next consumer notes

- UI was intentionally not changed. A frontend consumer must read `origins` separately rather than expecting Radar/Upload in `sources`.
- Native metadata correction cannot remove/replace conflicting strong identifiers; dedicated reviewed correction/merge tools remain out of scope. No automatic DOI lookup, OCR, AI metadata enrichment, worker or scheduler was added.
- Batch operations are synchronous and bounded (50 PDFs/materializations; 100 selected Zotero IDs); confirmation atomicity is per item, with explicit partial outcomes.
- Orphan originals may survive a crash/failed DB commit and are content-addressed/reusable. Cleanup intentionally only targets unreferenced old staging, never originals.
- Reconciliation cannot infer an explicit inbox choice made by old v1 code, which had no state-edit audit. It is therefore explicit, one-time and restricted to original legacy aliases. Current-version state edits are protected. It was not run on the real library during delivery.
- Existing canonical data does not require repeating identity migration. Legacy-only installations now require explicit POST/CLI migration before Library/AI/sync access; see contract G.
- No API/Vite service was restarted. Manually restart the API to load these backend changes. Do not merge main or the canonical baseline branch as part of this delivery.
