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
- [ ] 6.4 Final strict validation, staged review, logical commits and feature-branch push; report remote branch and V2.1 limitations.
