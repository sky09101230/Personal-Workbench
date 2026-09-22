# Design

## Context

See proposal.md and `docs/literature-foundation-roadmap.md`. Existing `_ingest` already serializes identity decisions and is shared by source sync, selected import, Radar and both upload paths. V2's weak fallback is a small but consequential branch in that resolver. Real data contains 69 canonical documents and no aliases explicitly recorded with the title-fallback reason; this is an audit observation, not authorization to rebuild data.

## Goals / Non-Goals

**Goals:** Remove weak automatic association at the common boundary, retain actionable candidates on rejection, preserve repeat imports and report historical risks without changing identity ownership.

**Non-Goals:** No new merge engine, verification provider, document split, asset relocation or complete conflict-resolution interface. Retain current completeness labels; do not relabel syntactically valid identifiers as verified.

## Decisions

### Strong matches must agree

Keep normalized identifier lookup plus known canonical/alias/source/origin replay. Collect all matches and reject disagreement before metadata, assets or origin writes. DOI is preferred scholarly evidence, but missing DOI does not prohibit arXiv/OpenAlex or a new unresolved document. A shared strong identifier with incompatible other identifiers remains a conflict. Stable source identity licenses replay, not silent replacement of a conflicting scholarly identifier.

Alternative rejected: precedence rules that select DOI and ignore a source/arXiv match to a different paper. They can steal origins and research state from a second canonical owner.

### Weak evidence produces review, never association

Keep exact title/year/shared-author detection as a candidate signal, but raise the existing `IdentityConflictError` with candidate IDs instead of adding those IDs to the strong match set. Existing same-title/different-formal-DOI errors remain conservative review signals. Public operations return their existing conflict contract; staged upload retains the item, candidate metadata and bytes for correction/retry. Sync/migration use the existing preservation path to retain independent ambiguous source records and conflict evidence.

A previously unknown no-ID paper without a weak collision still imports as incomplete. Do not create a requirement that all papers have DOI. The immediate user path for a correct match is to review and supply reliable identity evidence; arbitrary manual canonical merges remain out of scope. Broader candidate decisions will be added in the later evidence Change.

Alternative rejected: automatically create a second canonical record for every matching upload and leave the user no indication. This avoids merge but conceals ambiguity. Alternative rejected: invent a second review table now when upload state, conflict payloads and candidate IDs already provide the boundary behavior.

### File replay is a separate explanation

The deterministic `manual_pdf` origin can reuse the previously imported association for identical bytes. It must still reject a supplied DOI that belongs to another canonical document. Explicitly associating identical bytes to two existing documents must not merge those documents. Preserve the checksum and origin evidence; make result reasons distinguish canonical/source/origin/identifier association from weak similarity and file replay where appropriate. Never introduce global hash-to-paper uniqueness.

### Audit rather than repair history

Add a reproducible read-only CLI/report for canonical identity state: counts, indexed identifiers, recorded weak aliases, metadata/index mismatches, source/origin ownership and unresolved conflicts. Read raw SQLite in a read transaction without calling schema initialization; tolerate/report legacy or missing canonical schema. Inspect only Literature-owned tables. Output opaque IDs and bounded reasons, not credentials, note bodies or whole evidence blobs. Hash/count preservation acceptance uses a SQLite online backup of the real DB and disposable copies.

No data migration is required for removing the fallback. Any existing weak aliases are reported for future review; no automatic split or reindex. This keeps all current aliases, Notes, AI and file associations usable. Auditing cannot retroactively establish scientific correctness and must state that limitation.

## Risks / Trade-offs

- More imports may require review → return candidate IDs and preserve retryable uploads; do not weaken the rule to maintain old deduplication counts.
- Existing tests assert weak merging → replace those expectations and keep strong/replay/concurrency regression coverage.
- News may already have grouped appearances by weaker rules → do not infer a Literature merge from similarity; record this handoff limitation for the unified evidence Change.
- Source sync preserves ambiguous records through `_preserved_ingest` → verify it does not overwrite identifiers, aliases or state of another canonical record.
- Historical unarchived V2 spec allows title fallback → this capability explicitly takes precedence for new Literature operations; do not edit unrelated accepted News behavior.

## Migration Plan

1. Capture read-only real audit and baseline backend results (completed in roadmap).
2. Implement resolver guard and repeatable audit; run focused regression fixtures and full backend tests.
3. Online-backup real DB into the repository temporary area; compare canonical IDs and all existing Literature table rows before/after read-only audit and repository reopen. Use separate synthetic copied-data operations to exercise new ingestion without modifying the real library.
4. Record actual acceptance, limitations and strict OpenSpec validation; commit only this Change's work. No background API/Vite restart. User must manually restart API to load resolver changes.
5. Roll forward if review reveals old ambiguous aliases. Do not roll back to permissive matching as a data repair, and never restore a stale DB over later writes.
