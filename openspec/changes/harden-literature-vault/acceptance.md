# Vault acceptance

Date: 2026-09-23. Branch: `codex/literature-foundation`. Depends on committed identity Change `45455b8`.

## Delivered

Independent optional `LITERATURE_VAULT_ROOT`, existing portable backend/key/checksum records and file-store Protocol; path-free asset integrity inspection; verified full/range reads; independent atomic original publication; read-only inventory and explicit copy/verify relocation. Unsupported backend dispatch no longer falls through to Zotero. Defaults and legacy flat storage remain supported with no schema migration or ID/key rewrite.

The implementation found and fixed a Windows concurrent-directory path-resolution edge: the same drive path can transiently retain the extended `\\?\` prefix. Normalization now treats equivalent drive/UNC forms consistently without allowing redirected child paths. Actual Windows junction rejection and deterministic extended-prefix regression are tested.

## Tests and real acceptance

```powershell
.\.venv\Scripts\python.exe -m pytest -q apps\api\tests --basetemp .venv\tmp\pytest-vault-final -p no:cacheprovider
$env:PYTHONPATH = 'apps/api'
.\.venv\Scripts\python.exe -m app.modules.literature.infrastructure.vault
.\.venv\Scripts\python.exe apps/api/tests/manual_vault_acceptance.py
openspec validate harden-literature-vault --strict
```

- **238 backend tests passed**, one existing Starlette/httpx deprecation warning.
- Seven new regressions cover root default/override composition; staging mutation and old hard-link detachment; concurrent identical publication; hash/range/missing/corrupt/invalid/unsupported states; failed publication recovery; actual Windows junction read/write/cleanup rejection; production integrity/Reader API; CLI dry-run; flat legacy objects, relocation replay and pending-upload/source-integrity guards.
- Real read-only inventory: **105 remote-only descriptors**, no pending staged uploads. The earlier audit established 87 PDF and 18 HTML descriptors. No source download, schema update or live asset migration occurred here.
- Manual acceptance used an online backup of the real database and an actual generated on-disk PDF. Dry-run created no destination; apply verified copied bytes; replay reused the object. Reader served complete bytes and HTTP 206 ranges from the relocated Vault with a provider that fails on any remote call. Canonical ID, asset ID, key and checksum remained stable.
- All **55 copied DB tables** remained unchanged across relocation; original PDF bytes remained; real source table fingerprints before/after were identical. Temporary copies were removed by the harness.
- Strict OpenSpec validation and scoped/staged whitespace checks passed. No frontend change, frontend build or browser rendering claim.

## Operations and remaining Goal gaps

See `docs/literature-vault-operations.md` for configuration, copy/replay, manual switch and recovery. No service was restarted or `.env` changed. API restart is needed to load this backend version.

This Change verifies owned files; it does not yet acquire the real Zotero PDFs or finish metadata/version/conflict review. Real remote-only descriptors are explicit remaining Goal work. There is no destructive repair, GC or NAS/WebDAV/S3 implementation. Whole-file verification per range is an intentional I/O cost; local filesystem permissions remain the operator's boundary against unrelated writers. Integrity inspection does not claim scientific verification of PDF identity.
