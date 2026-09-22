# Literature Vault operations

The Local Filesystem backend owns finalized PDFs under `originals/<sha256>.pdf`, with separate `staging/` files for upload review. Legacy flat `<sha256>.pdf` objects remain readable. Asset rows retain `storage_kind=local`, a relative content key, SHA-256, filename and association metadata; they never need an absolute file path.

## Configuration

`LITERATURE_VAULT_ROOT` optionally selects an independent filesystem directory. Empty/unset preserves `<database-directory>/literature-assets`. Put an override in local `.env` only, for example `LITERATURE_VAULT_ROOT=D:/Research/LiteratureVault`. The API must be restarted manually after configuration changes. Do not change the root before copying and verifying existing assets.

The initial backend supports local filesystems with exclusive hard-link publication (tested on Windows/NTFS). A mounted directory can retain the same key contract, but another protocol such as WebDAV/S3 requires an adapter implementing `LiteratureFileStore`; no such adapter is installed by this change. Keep a custom in-repository Vault excluded from Git, or place it outside the repository. The existing default `data/literature-assets/` is already ignored.

## Inventory and integrity

From the repository root:

```powershell
$env:PYTHONPATH = 'apps/api'
.\.venv\Scripts\python.exe -m app.modules.literature.infrastructure.vault
```

This reads the configured DB without schema initialization, checks all referenced local assets (including inactive associations), and makes no remote requests. Use `--database` and `--root` for an explicit database/Vault pair. An inventory lists:

- `verified`: actual SHA-256 equals the content key and recorded hash, with byte count.
- `missing`, `corrupt`, `invalid`, `unreadable`: an owned file requires attention; the command does not alter it.
- `remote_only`: a Zotero descriptor; this does not prove its remote bytes still exist.
- `unsupported_backend`: an asset needs a configured storage implementation.

`GET /api/literature/papers/{paper_id}/assets/integrity` provides the same path-free inspection for a paper through its opaque ID. A local PDF/range read validates the complete object through the serving handle before returning bytes. Each request therefore reads the whole object once for verification. This is deliberate for the current local library; integrity is not inferred from filename or stat alone.

## Copy and verify a relocation

1. Stop imports/sync and stop the API manually for the final relocation. Keep a current SQLite backup and the original Vault. This tool does not coordinate with external writers or change server state.
2. Finish or cancel staged uploads through the existing workflow. Pending staged items block relocation so their files cannot be left behind unnoticed.
3. Plan a copy to a separate, non-overlapping destination (example path only):

```powershell
.\.venv\Scripts\python.exe -m app.modules.literature.infrastructure.vault --copy-to 'D:/Research/LiteratureVault'
```

4. Inspect the report. `planned` makes no destination directory and changes no DB rows. Missing/corrupt/unsupported owned files or pending uploads return `blocked`.
5. Copy verified objects with explicit apply:

```powershell
.\.venv\Scripts\python.exe -m app.modules.literature.infrastructure.vault --copy-to 'D:/Research/LiteratureVault' --apply
```

6. Require `ready_to_switch=true`. Re-run is safe: existing verified destination objects report `already_verified`; inconsistent destination bytes are never overwritten. Partial failures leave successful objects available for retry and all source objects untouched. The manifest is checked again before readiness is reported.
7. Set `LITERATURE_VAULT_ROOT` to that destination, manually restart the API, inspect the new Vault and open a known local PDF. Paper IDs, asset IDs and keys stay unchanged. Retain the original Vault until independent backup/recovery checks are complete.

This copies referenced owned objects, not arbitrary loose files, derived caches or remote Zotero attachments. No source file, unreferenced original, staging record, metadata or configuration is deleted or rewritten. It is not a whole-directory backup. Remote acquisition is the later asset-migration workflow. Do not interpret a remote-only inventory as proof that all PDFs are locally owned.

## Recovery and limitations

A corrupt object is retained and reported; do not silently replace it or relabel its checksum. Restore a separately verified copy under an operator-reviewed repair procedure. If relocation fails, keep the old root configured and fix/retry the copy. Switching back to an old root after new uploads requires preserving those new assets first. Never restore a stale DB over newer Notes or AI history.

The adapter prevents Workbench from mutating published bytes and rejects redirected child paths. It does not impose OS ACLs against other local programs; do not externally edit hash-named originals. The maximum new PDF size remains 50 MiB and the existing PDF format validation remains in effect.

Reproducible copied-real-data rehearsal:

```powershell
.\.venv\Scripts\python.exe apps/api/tests/manual_vault_acceptance.py
```

It reads the real source, seeds only temporary independent Vault copies, then exercises copy/replay and the production Reader router with an offline provider. Source/DB fingerprint checks fail if concurrent user writes occur, so rerun in a stable window. It never restarts services.
