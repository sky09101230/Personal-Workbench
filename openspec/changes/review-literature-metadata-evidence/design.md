# Design

## Context

All source adapters already converge on canonical `_ingest`. Metadata proposals already provide snapshots, stale guards and atomic acceptance. Preserve those boundaries; do not create a second ingestion engine. Existing metadata completeness is not evidence of review or scholarly verification.

## Goals / Non-Goals

Protect existing bibliographic fields, retain candidate evidence and decisions, and make review practical in the existing UI. The following identity/version Change handles unresolved source conflicts and relationships; this Change cannot clear an unrelated identity conflict through ordinary metadata edits.

## Decisions

- Initial explicit import stores the source observation as provisional canonical metadata with field evidence IDs. It does not claim scholarly verification. Confirmed staged upload marks supplied fields user-reviewed. Subsequent imports never fill or replace existing bibliographic fields, including blanks, automatically; they generate a proposal from non-empty differing candidate fields. Tags, reading state, collection/source activity and typed date evidence keep their existing separate semantics.
- Only accepted canonical identifiers enter the unique index. A new DOI on a shared arXiv/source association remains a pending candidate until explicit acceptance. Strong ownership conflicts still stop unsafe ingestion; preserved source conflicts keep their evidence and can create a conflicting proposal without changing identity fields.
- Reuse `literature_metadata_proposals`. Add only `literature_proposal_evidence(proposal_id,evidence_id)` to link stable source observations to proposals. Deterministic IDs based on canonical snapshot/source/patch prevent replay from reopening identical decisions. Multiple observations can support the same proposal. No historical canonical field backfill or guessed evidence assignment.
- Source and manual proposals retain syntactically valid but ownership-conflicting identifiers. Response includes current conflict explanation; acceptance always revalidates against current canonical/index state. Invalid syntax/allowlist remains rejected. Stale acceptance remains atomic/no-op.
- Accepted fields record decision evidence ID, reviewed flag, source and prior snapshot. Expose evidence IDs in provenance; old source/priority choices remain explicitly legacy-unlinked until reviewed. Completeness stays `metadata_status`; add computed `metadata_review_status` (`unreviewed`, `needs_review`, `reviewed`, `conflict`). A full current-snapshot confirmation can mark all populated metadata fields reviewed after stale, pending-proposal and identity-conflict checks. Reviewed means user confirmation, never provider/scientific verification.
- Schema version 3 is an additive workflow upgrade. Before DDL on an existing canonical database, create an SQLite online backup; record backup/report in maintenance ledger and version in workflow ledger transactionally. Existing migration CLI dry-run uses a disposable copy and reports schema version. No Notes, AI, canonical IDs, field values or asset rows are rewritten. Concurrent startup may create redundant valid backups but only one migration record.
- Extend existing metadata UI for field evidence, current-review status, OpenAlex field and confirmation. Show conflict reasons while allowing reject or corrective edit; backend remains authoritative. Do not add new workflow navigation.

## Risks / Trade-offs

- Source changes can produce more review work → deduplicate same-source/snapshot/candidate proposals and preserve rejected decisions.
- Legacy provenance may lack one exact deciding evidence row → keep original choices/evidence and display this limitation, not invent a historical pointer.
- Partial field acceptance is not whole-record verification → compute review state from field decisions; expose a separate explicit full-snapshot confirmation.
- Older running API still has old metadata policy → deployment needs a manual API restart; do not claim un-restarted processes run the new rule.

## Migration Plan

Audit version 2; validate version-3 upgrade/dry-run/idempotency and failure rollback with fixtures; compare all historical rows on a real DB copy allowing only the new table and migration ledgers. Verify sync/Radar/upload all queue metadata through the shared resolver and accepted identifiers remain stable. Exercise source proposal accept/reject/edit/stale and explicit snapshot confirmation in backend/API and browser on disposable data. Build frontend, strict-validate and commit before identity/version work. No live data migration is required for this implementation acceptance; deployment will back up before additive DDL.
