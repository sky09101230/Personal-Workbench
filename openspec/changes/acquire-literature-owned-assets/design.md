# Design

## Context

Use the existing Vault and provider/file/repository ports. The current paper materializer picks one primary, writes via scholarly ingestion and changes its primary selection. Migration instead must cover every eligible attachment while leaving original documents, source descriptors, metadata, Notes, AI, tags, collections and reading state untouched.

## Goals / Non-Goals

Acquire durable verified bytes with resumable source provenance and real acceptance. Exclusions are in proposal.md. Source-unavailable or parent-unresolved data is reported, never assigned by title or discarded.

## Decisions

- Extend the provider with read-only attachment description. Zotero fetches the exact external reference through its authenticated API and maps parent, version, type/link mode and available MD5. Before and after streaming, require stable descriptor/version/parent/reference. Compare downloaded MD5 when supplied, then publish validated PDF bytes under SHA-256 in the Vault and verify the owned asset.
- Real rehearsal found an accessible metadata record with no cloud file. A read-only local audit established a matching Zotero account and parents for all 87 descriptors, with 49 local files present. Add an explicit optional `ZOTERO_DATA_DIR`/CLI source directory. For its exact user-library/item tuple, prefer a registered `storage:` PDF from a validated local SQLite snapshot; otherwise use the Web API. Snapshot DB/WAL/journal copies are accepted only when source file signatures stay stable and copied SQLite integrity passes. Never bypass live SQLite locks with unverified immutable reads or stop Zotero. Local before/after observations include item version, file stat/hash and relative locator; no absolute source path enters the domain records. Missing/ambiguous/redirected local files are not guessed by filename.
- Keep browser uploads bounded at 50 MiB. Real migration found a valid 72 MB PDF, so provider acquisition uses disk-backed streaming with a separate 256 MiB bound; it never buffers the entire source in application memory. Source staging uses `.acquiring` keys excluded from upload cleanup, validates PDF structure through a file handle, and finalizes only after source/hash checks. Always close streams and remove owned temporary staging. Return stable per-asset failure codes; no raw transport exceptions or credentials. Metadata reads are evidence, not scholarly verification.
- Add `literature_asset_copies` in backed-up workflow schema 5: source asset ID, cached source snapshot, observed source snapshot, owned asset ID, SHA-256 and acquisition time. One current mapping per source; historical acquisitions remain in origins and old owned assets remain intact. Equal bytes/role within one paper reuse the existing owned asset; different papers keep independent associations. No source descriptor or canonical metadata rewrite.
- The repository checks the exact cached source snapshot inside the commit transaction. Add a local asset, mapping and deterministic acquisition origin together, without calling scholarly ingestion. A crash after durable file publication but before commit leaves a reusable object; retry completes safely. Preserve primary/preprint/supplementary roles and removed-paper state.
- Default replay verifies an existing matching mapping locally and makes no provider request. Missing/corrupt owned bytes are explicit failures, not silently replaced. `--refresh` explicitly re-observes a source when desired. A source version is an observed snapshot, not a promise that remote storage will never change later.
- Reader prefers an owned copy of an explicitly selected source and local files within the same role. Preserve user primary selections in the database. Explicit interactive materialize continues to select the resulting primary/preprint as before; it shares the new acquisition routine.
- CLI default is a read-only, no-network plan. The saved plan binds DB/Vault and exact source snapshots. `--apply --plan` backs up before DDL or writes, processes a bounded offset/limit or selected IDs, rechecks each source against the plan and reports per-item outcomes. It creates machine-readable reports under ignored `data/literature-migration-reports/`. No source file or database content is deleted. Reuse the existing online backup and schema migration mechanism.
- Non-PDF, unavailable/detached source descriptors and orphan conflicts are explicit plan exclusions. Acquire eligible PDFs even if the canonical paper is soft-removed, without restoring it. Old source references and all historical conflict payloads remain.

## Risks / Trade-offs

- Remote files may be absent/oversize/encrypted → bounded explicit failures and exception report; no fabricated owned status.
- Legacy cached versions may be absent/stale → fresh before/after source observations bind the acquired bytes while original descriptor remains untouched.
- Old local assets may have no source mapping → do not guess by filename; a verified download can reuse matching bytes.
- Source changes after acquisition → retain the owned version independently; later explicit refresh records another acquisition without deleting history.
- Many remote files take time → bounded sequential batches and persistent mapping/report allow interruption and resume without a job platform.

## Migration Plan

1. Validate read-only planning, duplicate bytes, source races, checksum failures, rollback/retry and offline Reader with fixtures and copied data.
2. Generate the actual real plan; inspect its 87 PDF descriptors and eight orphan exceptions. Back up before any apply.
3. Acquire in bounded batches; no Zotero mutations or automatic API/Vite restart. Retry only actionable failures; preserve explicit unrecoverable exceptions.
4. Compare all original research/source records and IDs, verify every new owned object's checksum, repeat acquisition with no downloads, and read owned PDFs with an offline provider. Record actual results and limitations, strict-validate and commit.
