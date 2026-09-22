# Literature owned-asset acquisition

Workbench retains the original Zotero descriptors and adds independently owned PDFs to its Vault. Each association records the cached source snapshot, a fresh source observation, actual version/channel, relative locator when local, SHA-256, size and owned asset ID. It does not change canonical IDs, metadata, Notes, AI, tags, collections, reading/deletion state or stored primary selections.

## Sources and validation

The Zotero adapter can read registered local files when `ZOTERO_DATA_DIR` is set. It validates the local account and user-library/item/parent, and reads only the registered `storage:` PDF. It does not search by title or guess a renamed file. The local database may be locked by Zotero: the adapter copies DB/WAL/journal into a private temporary snapshot, requires stable source signatures, validates copied SQLite integrity, and reads the snapshot. Any copied hot journal is recovered only in the copy. Zotero is not stopped and its DB/files are never opened for writing.

Local observations carry item version, file stat/hash, source channel and a relative `storage/<item-key>/<filename>` locator. Missing local files fall back to the authenticated Zotero Web API. A wrong local account is an error, not permission to use another user's file. Web API credentials are not forwarded across attachment redirects.

Acquisition checks the source before and after streaming, verifies available MD5 and always computes SHA-256. Provider transfers are streamed through bounded `.acquiring` staging up to **256 MiB**; browser uploads stay at **50 MiB**. PDF structure validation remains in place. Upload cleanup does not remove acquisition staging. Only after source and checksum checks does the store publish an independent content object and atomically record its association. Failed association can reuse a previously published object on retry.

Same bytes/role within a paper reuse an owned association; different papers remain separate. Primary/preprint/supplementary roles are preserved. The Reader prefers an owned copy of an explicitly selected source attachment, or an owned source/default within the same role. It still works when Zotero disappears or its reference is detached.

## Plan and execute

The CLI defaults to a no-network, read-only plan. Saving a report creates only the requested report file, not database or Vault writes. Plans bind the database, Vault, optional local Zotero directory and exact source descriptors.

```powershell
$env:PYTHONPATH = 'apps/api'
.\.venv\Scripts\python.exe -m app.modules.literature.infrastructure.acquire_assets --report data/literature-migration-reports/plan.json
# If local source data is not already configured, add --zotero-data-dir 'C:/Users/you/Zotero'
```

Inspect the eligible PDFs, excluded descriptors and orphan sources. Then apply a bounded batch, using the same source-directory option when the plan includes it:

```powershell
.\.venv\Scripts\python.exe -m app.modules.literature.infrastructure.acquire_assets --apply --plan data/literature-migration-reports/plan.json --offset 0 --limit 20
```

Continue at offsets 20, 40, etc. `--asset-id <opaque-id>` selects particular planned sources for retry. A changed descriptor returns `planned_source_changed`; create a fresh plan rather than forcing it. An edited plan or different DB/Vault/source directory is rejected. Every apply backs up the database before schema/writes and produces a durable JSONL report with per-asset results. Exit 1 means the completed batch contains failures; successful siblings remain safely committed. An interrupted report need not be restarted from scratch: repeat the selected scope and verified mappings return `already_owned` without provider access or duplicate rows.

`--refresh` explicitly re-observes an already owned source. New source versions retain prior owned objects and acquisition origins. Missing/corrupt owned objects are reported, not silently replaced. File references with unavailable sources or unknown parents remain intact. Reports under `data/literature-migration-reports/` and all database/Vault data are excluded from Git.

## Actual migration checkpoint (2026-09-23)

- Planned: 87 PDF descriptors (81 primary, 6 supplementary); 18 non-PDF descriptors excluded; eight parent-unresolved source records retained.
- Owned: **49 source mappings → 47 verified content objects**, **288,962,223 bytes** (about 276 MiB). There are 44 primary and three supplementary owned records; duplicate bytes/associations were reused.
- Verified: all 47 full/range reads and 44 default primary Readers work with a provider that cannot fetch anything. All 49 source mappings replay without a download or DB-row change. All 49 original local source files match their pre-copy hashes.
- Preserved: 52 protected tables match their baseline; every original row in the four additive tables also remains. Integrity is `ok`, with no foreign-key errors.
- Unavailable: **38 source PDFs**, affecting 29 papers. Eight of those papers have another owned primary; **21 still lack an owned primary**. These were not labeled acquired. Eight orphan descriptors also remain unassigned; two are PDF descriptors and six are HTML.

Local-only detailed artifacts:

- `data/literature-migration-reports/20260923-owned-assets-local-plan.json`
- `data/literature-migration-reports/20260923-acquisition-batch-01.jsonl` through `batch-05.jsonl`, plus `20260923-acquisition-large-retry.jsonl`
- `data/literature-migration-reports/20260923-acquisition-verification.json`
- `data/literature-migration-reports/20260923-missing-sources.json` — titles, DOI, filenames, source keys and whether another primary is already owned

The first pre-apply backup is `data/backups/literature-v2-20260923-024406-a06c125b.db`. Later batches and schema transitions also have their own backups. Do not restore an old backup over subsequent Notes or other user work.

## Recover missing sources

Restore the registered PDF in Zotero from a known backup or another device, then retry its planned source ID. If the Workbench descriptor changed, make a new plan first. Alternatively, upload a reviewed replacement/version explicitly to the existing Workbench paper; do not claim an arbitrary new download is byte-identical to the missing original. Metadata and provenance stay available while bytes are missing. No content was invented for missing files.

The verified local source directory was added to this machine's ignored `.env` as `ZOTERO_DATA_DIR`; all earlier configuration bytes were retained. Manually restart the API to load code/config changes. Owned reads do not depend on that source directory. No production service was restarted automatically.

For relocation and checksum operations, use `docs/literature-vault-operations.md`. The real migrated corpus, including the 72 MB PDF, was copied and verified in temporary Vaults with unchanged IDs/keys; it was not moved out of the configured Vault.
