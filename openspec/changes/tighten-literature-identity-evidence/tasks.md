# Tasks

## 1. Evidence and planning baseline

- [x] 1.1 Trace identity, ingestion, review, storage, Reader/AI and existing OpenSpec; verify findings and real read-only database counts are recorded in `docs/literature-foundation-roadmap.md`.
- [x] 1.2 Run full backend baseline; verify 225 tests pass and record the existing warning separately from new failures.

## 2. Strong identity boundary

- [x] 2.1 Replace weak title/year/author association with explicit review candidates at the shared resolver; verify same-title/no-ID records never silently merge and DOI/arXiv/source replay still works.
- [x] 2.2 Preserve actionable candidate IDs/reasons in existing API and staged review outcomes; verify upload retry and source-sync preservation keep evidence without claiming another paper's identifiers.
- [x] 2.3 Verify checksum replay cannot override contradictory scholarly evidence or merge explicit targets; cover renamed uploads, two canonical targets and strong-match disagreement in regression tests.

## 3. Historical audit and data preservation

- [x] 3.1 Add a read-only identity audit CLI with legacy-schema reporting; verify repeat runs create no tables, modify no rows and report weak aliases/index inconsistencies without exposing private contents.
- [x] 3.2 Run audit on the real library and perform online-backup/copied-data acceptance; compare all existing Literature records and canonical relationships before/after audit/reopen and record actual results.

## 4. Acceptance and checkpoint

- [x] 4.1 Run full backend tests and relevant API/ingestion acceptance; record commands, outcomes and remaining limitations in acceptance.md (build frontend only if frontend changes).
- [x] 4.2 Run strict OpenSpec validation and git diff checks; commit only current Change work, update roadmap and review Goal gaps before creating the next Change.
