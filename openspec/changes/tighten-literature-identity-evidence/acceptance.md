# Identity evidence acceptance

Date: 2026-09-22. Branch: `codex/literature-foundation`.

## Delivered behavior

- Shared resolver no longer associates canonical papers through title/year/shared-author evidence. Weak matches return explicit conflict reasons and sorted candidate IDs.
- Existing DOI/arXiv, canonical/alias, source and origin replay remain supported; matching reasons now identify the evidence category, including file-import replay.
- Upload confirmation and selected Zotero import expose candidate IDs. Staged conflicts retain candidate metadata and bytes; conflict evidence is persisted with the item. Sync retains ambiguous source records independently.
- A rejected source identifier cannot fill an existing canonical identity blank. Same bytes attached to separate canonical targets do not merge those targets; conflicting DOI versus file replay is rejected.
- Read-only `audit_identity` reports missing canonical schema, weak historical aliases, identifier/ownership inconsistencies, no-ID documents and historical conflict records. It does not label absence of issues as scientific verification and does not emit note/evidence contents.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest -q apps\api\tests --basetemp .venv\tmp\pytest-identity-final -p no:cacheprovider
$env:PYTHONPATH = 'apps/api'
.\.venv\Scripts\python.exe -m app.modules.literature.infrastructure.cache.audit_identity
.\.venv\Scripts\python.exe apps/api/tests/manual_identity_acceptance.py
openspec validate tighten-literature-identity-evidence --strict
```

- Full backend: **231 passed**, one existing Starlette/httpx deprecation warning.
- Six new integrated regressions cover strong disagreement, no-DOI preprint replay, weak candidate API responses for upload/Radar/Zotero, source preservation, note retention and upload retry, file replay/explicit targets, conflicting source DOI fill, and read-only legacy/canonical audit.
- Existing concurrency, legacy migration, AI/Notes and materialization regressions pass. No frontend changes; no browser behavior is claimed by pytest and no frontend build is required for this Change.
- Strict OpenSpec validation passed; staged diff whitespace check passed.

## Real database acceptance

The audit opened the configured real SQLite DB with `mode=ro`; no schema initialization, remote request or source sync occurred. It reported 69 canonical papers, 75 identifiers, three documents without indexed identifiers, no recorded weak aliases and no detected metadata/index or owner mismatches. Eight historical `Source asset parent unresolved` records remain. These findings are structural, not scientific verification.

The reproducible manual script took an online SQLite backup into a disposable repository-local temporary directory and fingerprinted all **55 tables**, including **34 Literature tables**. Repeated audit and repository reopen preserved every row; a weak import based on actual copied bibliographic data was rejected without writes. Compatible strong replay retained the existing ID; all tables except the explicitly ingested document/origin/evidence tables remained byte-for-byte equivalent at row serialization level. Integrity check returned `ok` and foreign-key check returned no rows. The real source fingerprints before/after were identical. Temporary acceptance copies were cleaned up; no live database writes occurred.

## Remaining Goal work

This Change intentionally leaves broader metadata decision status, version evidence, review UI, durable Vault integrity/configuration and asset migration to subsequent Changes. Historical conflict records are append-only observations here; accepting a retried upload does not delete prior conflict evidence or claim a global conflict lifecycle exists. Existing shared arXiv/publication behavior remains until the evidence/version Change provides an explicit decision gate. Radar appearance grouping still needs handoff hardening there.

Restart the API manually to load these backend changes. No API or Vite service was restarted. The user's existing `AGENTS.md` edit is excluded from this commit.
