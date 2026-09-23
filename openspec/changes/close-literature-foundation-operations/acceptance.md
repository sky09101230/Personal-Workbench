# Operational closure acceptance

Date: 2026-09-23. Branch: `codex/literature-foundation`. Previous asset commit: `16e709a`.

## Delivered

- Workflow schema 6 stores descriptor-scoped current acquisition state. `source_unavailable`, stale descriptors and successful retries are distinguishable; reviewed source failures do not modify canonical metadata or research rows.
- Selective Zotero import uses the shared acquisition routine for every eligible source PDF and returns metadata result plus per-attachment outcomes. A metadata import can succeed while a missing supplementary file remains retryable.
- Library and Files views distinguish `已保存主 PDF`, `受管 PDF`, `仅有 PDF 来源引用` and `PDF 待恢复 / 重试`; exact-source retry remains visible. Files show SHA-256 and link directly to verified owned bytes. Missing-source papers no longer expose a Reader entry as if a remote descriptor were owned.
- `LiteratureFileStore.storage_kind` is consumed by manual upload, staged confirmation and source acquisition; alternate backend contract tests pass without changing the domain record shape.
- Read-only identity audit separates open, quarantined and reviewed conflict history. It retains every row and does not call migration.

## Verification

- Final isolated backend suite: **269 passed**, one existing Starlette/httpx deprecation warning; real database fingerprints were unchanged before/after.
- Frontend TypeScript/Vite build passed after final ownership/readiness UI changes.
- Strict OpenSpec validation passed for this Change; scoped diff checks passed (the only workspace whitespace warning is the user-owned `AGENTS.md` edit and is excluded from commits).
- Readiness regressions cover stale failures, successful retry, selected import partial success, exact-source retry, alternate backend dispatch, decision-aware audit, report reconciliation idempotency and source-state projections.

## Browser acceptance

On the isolated fixture server and built UI:

- List and detail display `已保存主 PDF` for owned papers and `PDF 待恢复 / 重试` for a source-only unavailable paper.
- Missing source files show the source reference and exact retry action; retry failure remains `失败 · 来源暂不可用 / 需恢复源文件` and creates no owned bytes.
- Selective import displays successful metadata/file acquisition and a separate per-file failure for another item. Imported metadata remains available, and the owned file opens with a displayed SHA-256.
- The final build presented no unexpected browser console warnings/errors in the inspected flow. One replacement-upload file chooser attempt failed because the browser could not retain the temporary file path; API/upload regression coverage remains valid and the limitation is documented.

## Real library closure evidence

- Plan: 87 PDFs (81 primary, 6 supplementary), 18 non-PDF exclusions, eight unresolved-parent descriptors.
- Acquisition: 49 source mappings to 47 verified objects (44 primary, 3 supplementary), 288,962,223 unique bytes; 44 papers have offline default primary reads.
- Current state after reconciliation: 44 `owned_primary`, 21 `needs_recovery`, 4 `none`; 38 unavailable source PDFs affect 29 papers, 21 without another owned primary.
- Reconciliation used a saved plan/report digest, backed up before schema/state writes, added exactly 38 current failure states and was idempotent. It did not alter canonical metadata, Notes, AI, collections, tags, reading state, source descriptors or existing rows. Existing rows in the additive tables remained unchanged; SQLite integrity and foreign keys were clean.
- `manual_verify_asset_migration.py` revalidated all owned bytes, full/range offline reads, source-file hashes, protected table fingerprints and no-download replay. No source file was deleted or rewritten.

## Remaining Goal gap

The foundation cannot claim all PDFs are independently owned while 38 source bytes remain unavailable. The detailed recovery list is `data/literature-migration-reports/20260923-missing-sources.json` (ignored local artifact). A known Zotero backup/another device directory or reviewed replacement uploads are required to close those exceptions. The eight orphan descriptors remain unassigned by design. This Change closes operational truthfulness and retryability; it does not silently mark the Goal complete.
