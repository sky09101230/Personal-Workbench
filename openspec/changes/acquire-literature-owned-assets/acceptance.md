# Owned-asset acquisition acceptance

Date: 2026-09-23. Branch: `codex/literature-foundation`. Previous checkpoint: `1eee698`.

## Actual scope and adjustments

Implemented planned, backed-up per-asset acquisition and source-copy provenance, unified with interactive primary materialization. It preserves original source descriptors, canonical/research records and selections, handles all cached file roles, and prefers owned Reader copies.

Real evidence changed two initial assumptions:

1. The first cloud-file rehearsal failed even though metadata was accessible. A validated local SQLite snapshot confirmed the configured account and all 87 parent bindings; 49 registered local files existed and 38 did not. Added an explicit optional read-only local Zotero source with DB/WAL/journal snapshot validation, account/parent/path guards and channel/relative-locator provenance. No Zotero shutdown or source write was used. A documented [local API path lookup](https://www.zotero.org/support/dev/web_api/v3/local_api) was also tried for a missing item; the registered file still did not exist.
2. One existing valid, unencrypted, 29-page PDF was **72,021,588 bytes** and hit the old 50 MiB bound. Added disk-backed source staging bounded at 256 MiB, keeping browser upload policy at 50 MiB. Source cleanup protection and Vault relocation use the streaming path. Retrying that exact planned asset succeeded; original bytes were preserved.

## Verification

- Full isolated backend suite: **264 passed**, one existing Starlette/httpx deprecation warning (`.venv/tmp/pytest-acquisition-delivery`). Parent-process fingerprints confirmed the migrated real database was unchanged by the suite.
- Eleven acquisition tests cover protected research/source rows, fresh versions/checksums, duplicate bytes and roles, soft-removed papers, source races, source hash mismatch, stream closure, failed-commit recovery, corrupt owned objects, read-only/stale/tampered plans, exact provider descriptions, uncommitted WAL snapshots, account/path rejection, unstable snapshots and bounded source staging excluded from upload cleanup.
- Existing materialization, Reader, upload and Vault regressions passed. No production frontend change; only the isolated fixture provider learned the new description port.
- Strict OpenSpec validation and scoped/staged whitespace checks passed.
- Real-source rehearsal ran on an online DB backup and temporary Vault, acquired a **5,520,357-byte** actual PDF, verified SHA-256, proved offline full/range reads and no-download replay, and preserved the source database.

## Real execution and outcomes

Read-only plan `903412e39892034fa1686f9960d37b4ff5f042c56bf9ed43fc1ee95fd647e21d` contained 87 PDFs: 81 primary and six supplementary. It excluded 18 non-PDF descriptors and separately retained eight unresolved-parent records. The original Web-only plan remains historical; execution used the later plan bound to the verified local source directory.

Five completed batches covered every planned PDF. Initial outcomes were 48 acquired, 38 source unavailable and one size-limit failure. Streaming retry acquired the large PDF, producing the final **49 acquired source mappings / 38 unavailable** outcome. These are not 87 successfully copied files.

First pre-apply backup: `data/backups/literature-v2-20260923-024406-a06c125b.db`. Every batch and the source-copy schema transition had a verified online backup before writes. Workflow schema 5 added the source-copy relation; pending version-4 tables/ledgers were also applied additively. No canonical data migration was repeated.

`manual_verify_asset_migration.py` verified:

| Check | Result |
| --- | ---: |
| Protected tables exactly unchanged | 52 |
| Original rows retained in assets/origins/schema/maintenance tables | All |
| Acquired source mappings | 49 |
| Owned asset records / content objects | 47 / 47 |
| Unique owned bytes | 288,962,223 |
| Owned roles | 44 primary, 3 supplementary |
| Original local source files unchanged | 49 |
| Full and range reads with a nonfunctional provider | 47 |
| Default primary Readers working offline | 44 papers |
| No-download replay | 49 already owned; no row changes |
| Foreign-key errors | 0 |
| SQLite integrity | ok |

The replay created only an additional safety backup; it made no provider requests or duplicate database rows. A subsequent `manual_vault_acceptance.py` copied the entire real owned corpus, including the large PDF, through two disposable Vault locations, checked replay and offline Reader, and kept the real database/source bytes unchanged. Some source PDFs emitted existing xref repair warnings during read validation; original bytes were never rewritten and their checksums matched.

## Exceptions and user action

The 38 unavailable sources affect 29 papers, including **21 without another owned primary**. Detailed filenames/DOI/source keys are in ignored `data/literature-migration-reports/20260923-missing-sources.json`. A user question is pending about backup locations or retaining explicit missing-source status. No assumption of approval or recovery was made. The eight historical orphan descriptors were preserved without guessed parents or automatic review decisions.

The Change completes migration of available assets and the safe retry infrastructure; it does not claim those missing bytes were recovered or the whole Goal is complete. The final Goal phase must expose remaining availability accurately, close operational/spec gaps and account for the unavailable-source decision.

The machine's ignored `.env` gained only the verified `ZOTERO_DATA_DIR` value, preserving all original bytes/settings. `.env`, PDFs, SQLite files, detailed reports and user `AGENTS.md` edits are not included in the commit. No production API/Vite restart or Zotero mutation occurred. Operator instructions: `docs/literature-asset-acquisition.md`.
