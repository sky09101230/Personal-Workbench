# Tasks

## 1. Audit and proposal

- [x] 1.1 Audit all Literature/Radar/Agent/DB paths and PLAB references; record real counts and baseline tests in audit.md.
- [x] 1.2 Write phased migration, rollback and capability specs; verify proposal scope is internally consistent.
- [x] 1.3 Strict validate OpenSpec and commit audit/design/proposal.

## 2. Canonical foundation

- [x] 2.1 Add canonical ingestion domain and resolver; test normalization, strong identity, conservative fallback and conflicts.
- [x] 2.2 Add atomic canonical schema, aliases, evidence, origins, assets and native collections; test persistence and concurrent idempotency.
- [x] 2.3 Implement backup/migration/report command and legacy AI mapping; test repeat, rollback, orphan preservation and content retention on copies.

## 3. Source integration and reads

- [x] 3.1 Implement scoped Zotero full/incremental ingestion and detach semantics; test paper survival and native state preservation.
- [x] 3.2 Switch composition and existing read paths to canonical; verify alias compatibility, filters, notes, collections and provider independence.
- [x] 3.3 Canonicalize AI ownership and file text cache; test legacy/new notes, conversations and selected-file changes.

## 4. Radar and import

- [x] 4.1 Add independent News export and injected Literature handoff; test new/existing/repeated saves, provenance and unchanged ingest/review.
- [x] 4.2 Add bounded PDF upload, file association and range/download handling; verify invalid files, multiple assets and incomplete metadata.
- [x] 4.3 Add native state/collection/delete APIs; verify sync does not overwrite organization or resurrect deleted papers.

## 5. Product UI

- [x] 5.1 Implement Library/Radar/Import, filters, source indicators and native organization; verify frontend build and browser behavior.
- [x] 5.2 Expose saved Radar state, PDF upload and paper sources/files/AI; verify refresh, error, duplicate and Reader flows. Browser picker limitation is documented in acceptance.md; actual HTTP PDF import and browser Reader passed.

## 6. Acceptance and delivery

- [x] 6.1 Run full backend pytest, frontend build, compileall, diff check and secret scan; record results.
- [x] 6.2 Back up real SQLite, dry-run then migrate, verify counts/content and rehearse rollback into a separate DB; record report. The application migrated during interruption; final CLI replay was a verified no-op.
- [x] 6.3 Verify eight requested acceptance cases and real metadata/PDF/AI where available; distinguish fixtures from live external checks. See acceptance.md for the in-app file chooser limitation.
- [x] 6.4 Final strict validation, staged review, logical commits and feature-branch push; report remote branch and V2.1 limitations.

## 7. Stage 1 backend hardening (Gemini handoff)

- [x] 7.1 Separate sources/origins and implement explicit, backup-protected migration with a real dry-run; test existing v1 and pending legacy databases.
- [x] 7.2 Version workflow DDL upgrades and idempotent saved-state reconciliation without overwriting user state; test repeated/concurrent migration.
- [x] 7.3 Harden staging/finalization/recovery/cleanup and legacy file fallback; test traversal, corruption, failed confirmation and referenced-file protection.

## 8. Stage 2 workflows and API freeze

- [x] 8.1 Complete typed repository/provider ports, composition and routes; verify application services contain no SQL/private infrastructure access.
- [x] 8.2 Complete staged upload, metadata extraction, review/confirm/cancel and retry semantics; test idempotency and partial failures.
- [x] 8.3 Complete metadata proposals with alias resolution, stale/concurrent acceptance checks, identifier uniqueness and evidence; test accept/reject/edit conflicts.
- [x] 8.4 Complete selected Zotero import and bounded PDF materialization; test remote resource loading, local preference, size limits and cleanup.
- [x] 8.5 Freeze A–G API contracts in docs/contracts/literature-v2-api.md; verify OpenAPI schemas and endpoint tests.
- [ ] 8.6 Run full backend pytest, compileall, strict OpenSpec validation, diff/secret checks and existing-DB copy upgrade; commit/push claude/literature-v2-backend-workflows without UI changes or merges.
