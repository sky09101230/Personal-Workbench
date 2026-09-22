# Tasks

## 1. Evidence-protected metadata

- [x] 1.1 Add backed-up version-3 evidence-link schema and dry-run/report support; test legacy preservation, replay and rollback.
- [x] 1.2 Queue evidence-linked source proposals at common ingestion instead of overwriting fields or indexing new candidate identifiers; test refresh/replay and preprint DOI behavior.
- [x] 1.3 Retain conflicting proposals, enforce atomic stale/identity decisions, record field evidence and explicit current-snapshot confirmation; verify API and review-state tests.

## 2. Review and acceptance

- [x] 2.1 Extend the existing metadata UI with evidence, conflict reasons, OpenAlex and current confirmation; production build and disposable browser acceptance must pass.
- [x] 2.2 Run real DB copy migration/preservation and source proposal acceptance; record actual schema/data results. The isolated rehearsal made no source mutations; an existing unisolated test earlier triggered backed-up live additive DDL, audited and fixed as documented in acceptance.md.
- [x] 2.3 Run backend suite, strict OpenSpec validation and diff checks; record acceptance, update roadmap and commit before starting identity/version Change.
