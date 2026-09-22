# Tasks

## 1. Safe per-asset acquisition

- [x] 1.1 Add source description/checksum and backed-up source-copy schema; test source-version mapping and preservation.
- [x] 1.2 Implement bounded before/after-verified acquisition and reuse it in primary materialization; test races, size/checksum errors, stream closure and failed-commit retry. Real evidence required verified local-source snapshots and 256 MiB disk-backed source streaming; browser uploads remain at 50 MiB.
- [x] 1.3 Prefer owned copies without rewriting primary selections; test offline full/range reads and independent supplementary/removed-paper state.

## 2. Migration and real acceptance

- [x] 2.1 Add no-network planning and plan-bound backed-up batch apply/reporting; test dry-run, stale plan, partial failure and no-download replay.
- [x] 2.2 Generate the real plan, migrate available PDFs in bounded batches and document every exception; retain backups and original research/source rows. 49 sources acquired, 38 unavailable and eight parent-unresolved descriptors preserved; no missing bytes are claimed recovered.
- [x] 2.3 Verify live owned checksums, replay and source-offline reads plus protected-data fingerprints; run regressions and strict OpenSpec validation, update roadmap and commit.
