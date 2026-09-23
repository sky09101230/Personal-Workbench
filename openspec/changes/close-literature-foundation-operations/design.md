# Design

## Context

Real migration owns 49 source associations as 47 verified objects; 38 sources remain unavailable. The previous `pdf_available` boolean describes references, not independent storage. Keep it for compatibility, but stop presenting it as proof of owned bytes.

## Goals / Non-Goals

Close operational gaps through existing ports and views. Missing originals remain missing until restored or the user explicitly accepts that exception; no synthetic replacement or guessed association. No unrelated module/schema changes.

## Decisions

- Add `literature_asset_acquisition_state` in backed-up workflow schema 6, keyed by source asset and bound to its normalized descriptor. Failure is recorded separately from scholarly identity. Success updates the current state atomically with the owned association; already-owned replay does not write. Ignore stale failure state after source changes. JSONL reports preserve attempt history; this table is the current operational view.
- Compute `pdf_state` from existing managed records and matching source outcomes: owned primary, owned other files, source-only, recovery-needed or none. These are inventory/ownership states; current SHA verification remains the integrity endpoint. Do not hash every file on Library listing.
- Extend integrity projection with owned-copy ID and acquisition error. A source with a verified owned copy is shown as such rather than merely remote. Corrupt/missing owned copies remain explicit failures. Add exact-source retry through the existing materializer; validate paper ownership and reuse all acquisition checks.
- Inject the acquisition callable into selective import at composition. Once canonical import succeeds, attempt all eligible attachments belonging to the selected source paper, preserving metadata success even when files fail. Return per-file outcomes, including supplementary files. Existing source sync remains observation, not an implicit bulk downloader; explicit import/save is the ownership boundary.
- Add the configured file-store backend name to the existing port. Manual/staged/source writes use that name rather than hardcoding local storage in application orchestration. No new backend is implemented; a fake backend contract test verifies dispatch/metadata decoupling.
- Audit reports retain all conflict history but separate open, quarantined and reviewed records. No scientific verification is inferred from an empty error list.
- Seed current failure states only from this Goal's validated plan/report IDs and exact current source descriptors, after backup. Do not overwrite valid owned mappings or apply failure state to a changed source. Preserve all prior rows and recovery artifacts.
- Finalize the Goal's own completed Changes, synchronize their capability specs and create an acceptance matrix against the original request. Do not archive unrelated existing Changes or merge the branch into main.

## Risks / Trade-offs

- File acquisition extends selected-import duration → use existing selected-item/per-file bounds and report successes separately; no worker system is introduced.
- Stored ownership is not physical integrity → labels say saved/owned, while the file view verifies current bytes.
- Old reports can become stale → exact descriptor/plan validation and owned-copy checks prevent stale failure backfill.
- Missing originals cannot be recovered from metadata → keep explicit recovery state and the pending backup question; do not mark the overall Goal achieved without a complete scope audit.

## Migration Plan

Validate schema-6 dry-run/backup/replay on copies and test import partial success, file retry, state transitions, backend metadata, audit decisions and no research mutations. Reconcile the known 38 source failures from saved reports on the real DB only after validation. Recheck original data against pre-acquisition baseline, owned bytes and offline reads. Build/test/browser validate, commit this Change, finalize only Goal-owned specs, then perform the full completion audit.
