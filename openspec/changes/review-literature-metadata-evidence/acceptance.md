# Metadata evidence acceptance

Date: 2026-09-23. Branch: `codex/literature-foundation`. Prerequisites: identity Change `45455b8`, Vault Change `a883125`.

## Delivered behavior

All existing ingestion adapters share the protected bibliographic-field rule. Incoming differences create evidence-linked proposals, including additions of previously blank fields and publication DOI promotion. Source replay deduplicates proposals and retains prior rejection. Only accepted identifiers enter the canonical index. New and accepted field choices reference stable evidence; decisions preserve previous field choices so current confirmation does not sever source provenance.

Conflicting proposals are retained with explanations; acceptance remains atomic and ownership/staleness-gated. Ordinary metadata edits no longer clear an unrelated canonical identity conflict. Metadata completeness and computed review state are separate. The current-snapshot confirmation API and UI explicitly record user review. OpenAlex can be proposed/reviewed. No scientific-verification label is inferred.

## Validation

- Full backend **243 passed**, one existing Starlette/httpx deprecation warning; final run used `.venv/tmp/pytest-metadata-final`. A parent-process fingerprint check verified the final isolated suite made no changes to the real database.
- Five new integration tests cover source refresh/proposal evidence/rejection replay, publication DOI gating/index update, conflicting AI/user proposals and snapshot confirmation, OpenAlex normalization, unrelated conflict retention, and schema dry-run/backup/rollback/replay.
- Frontend TypeScript checks and Vite production build passed (`npm.cmd --prefix apps/web run build`). Vite required sandbox permission to write its normal temporary build output; no dependency or config workaround was introduced.
- Strict OpenSpec validation and scoped/staged whitespace checks passed.

## Browser acceptance

Used built UI and production API through `apps/web/scripts/literature-acceptance-server.py --port 8014`, with temporary database/Vault and fixture providers. Verified:

- Source update retains original title and shows a pending proposal with the original source observation.
- Accept changes the canonical title; partial review remains 尚未完整审核.
- A conflicting DOI proposal is stored, displays its reason and disables direct Accept while canonical DOI remains unchanged.
- Edit-accept restores the correct DOI, adds OpenAlex and an abstract; state/values update correctly.
- Explicit current metadata confirmation marks populated fields reviewed. Refresh retains correct DOI, OpenAlex, title, abstract and reviewed state.
- Field-choice table displays user confirmation; screenshot inspected for visible layout.
- Accepting one of multiple pending proposals marks older snapshots stale and disables their acceptance/edit controls. A stale proposal can still be rejected, retaining history.
- Browser warning/error log was empty. No real external provider calls or user-library UI mutations.

The temporary browser tab was closed. Ctrl+C stopped the acceptance listener but its Python launcher/child remained; only those exact command lines/PIDs/creation times were identified and terminated. No production API or Vite service was restarted.

## Real data audit and test-isolation incident

During the initial regression run, the pre-existing `test_literature_status_keeps_provider_behind_workbench_api` used global application configuration and reached the real database. It triggered the new additive startup schema upgrade at **2026-09-23 00:21:56 +08:00**, before the explicit copied-real-data rehearsal. Do not describe the whole Change as making no live schema writes.

The upgrade created and recorded this pre-upgrade online backup:

`data/backups/literature-v2-20260923-002156-82002739.db`

Read-only comparison of that backup to the live database proved only `literature_workflow_schema` and `literature_maintenance_actions` changed, and only `literature_proposal_evidence` was added. All other pre-existing tables were unchanged, including **32 Literature tables** and every non-Literature table. Live integrity was `ok`, with no foreign-key errors. Canonical documents remained 69, metadata evidence 89, proposals 0, and source assets 105; no research values were edited by this upgrade.

Root cause was fixed in `apps/api/tests/conftest.py`: before importing the app, pytest now binds startup to a temporary DB/Vault and clears provider credentials in its own process. The browser harness likewise explicitly binds its Vault. The final complete suite's before/after real-table fingerprints were identical. The live additive schema was retained; no stale backup was restored over user state.

`manual_metadata_acceptance.py` was run against both the current database and the actual pre-upgrade backup. The latter compared **55 historical tables** through dry-run, backed-up schema upgrade and replay. Canonical field values and research rows were preserved; only schema/maintenance ledgers changed. On a copy, a priority-999 source update did not overwrite the title, explicit proposal acceptance and full confirmation worked, and canonical DOI/ID plus all unrelated research state remained unchanged. Source fingerprints remained identical. The identity acceptance harness also passed against the new 56-table schema.

## Remaining Goal work

The next independent Change must complete identity-conflict decisions, explicit version relationships and Radar appearance validation, including provenance/asset-state UI gaps. Real Zotero PDF acquisition is still pending. No merge/split, external enrichment, embeddings, chunking or maps were implemented. See `docs/literature-metadata-review.md` for operations; load backend changes with a manual API restart.
