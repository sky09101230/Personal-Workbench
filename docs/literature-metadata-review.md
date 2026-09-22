# Literature metadata evidence and review

Source imports now use one common rule: the first explicit import establishes provisional metadata; later non-empty differences become proposals. Neither higher priority nor another refresh of the same source silently replaces an existing title, author list, abstract, publication year/venue or scholarly identifier. Previously blank fields also require review when filled later. Native reading status, tags and collections keep their separate controls.

## Reviewing a paper

Open a paper's 元数据 section. The panel distinguishes information completeness from review state. A complete source record can still be 尚未完整审核. 待审核 means there are pending proposals; 已人工审核 means every populated bibliographic field has an explicit user decision. These labels do not claim registry, PDF or scientific verification.

Source suggestions show current/candidate values and expandable supporting observations. Accept applies a valid current proposal; Reject retains its history; 编辑后接受 records the final edited candidate. Conflicting identifiers remain visible, but direct acceptance is disabled and the server checks ownership again at decision time. Changed canonical snapshots invalidate old pending proposals; reject and recreate them rather than forcing acceptance.

After resolving pending proposals, use 确认当前元数据已人工核对 to confirm the displayed snapshot. This action stores a user decision and previous field-choice evidence, without changing bibliographic values. A concurrent metadata change or unresolved canonical identity conflict prevents confirmation. Reviewing only one correction does not automatically mark every other field reviewed.

OpenAlex is available alongside DOI and arXiv in the metadata form. Adding a publication DOI to a preprint remains a proposal; accepting it retains existing scholarly identifiers as historical evidence. Replacement/removal of conflicting accepted identifiers is still gated. Full conflict and version-relationship operations are the next foundation Change.

## Evidence and APIs

`GET /api/literature/papers/{paper_id}/provenance` includes stable IDs for metadata evidence and deciding evidence IDs on new/reviewed field choices. Decision records retain before/after, proposal/supporting evidence IDs and previous field choices. Historical source/priority selections without one exact evidence pointer are explicitly `legacy_unlinked`; no migration guesses historical scientific truth.

Existing proposal endpoints now return `evidence_ids` and a current `identity_conflict` explanation. Proposal creation retains syntactically valid conflicting candidates; acceptance still returns 409 without mutation when identity or snapshot validation fails. Invalid syntax and unsupported fields remain rejected.

`POST /api/literature/papers/{paper_id}/metadata/confirm` takes `{ "snapshot": { ... } }` with all bibliographic fields: `title`, `authors`, `year`, `journal`, `doi`, `arxiv_id`, `openalex_id`, `abstract`. Send arrays/nulls as returned by the paper API. Omitted fields are not a full-snapshot confirmation. Identical confirmation reuses its evidence ID.

## Additive upgrade

Workflow schema version 3 adds `literature_proposal_evidence`. Before upgrading an existing canonical database, the repository makes an SQLite online backup, then creates the relation and migration records transactionally. It does not rewrite historical canonical values, Notes, AI, assets or relationships. Failed DDL rolls back; replay does not repeat the upgrade. Original aliases and field choices remain intact.

Use the existing explicit migration CLI for a dry-run on a copy:

```powershell
$env:PYTHONPATH = 'apps/api'
.\.venv\Scripts\python.exe -m app.modules.literature.infrastructure.cache.migrate_canonical --dry-run
```

Read the current report's workflow schema version; the original V2 migration report remains historical. The new upgrade's backup location is recorded under `metadata_evidence_schema` in `literature_maintenance_actions`. Canonical startup also applies this additive schema upgrade with a backup. Legacy canonical-data migration remains explicit and separately gated.

Tests now isolate default application startup, database, Vault and provider credentials before importing the application. Manual acceptance scripts explicitly read a named real DB and only exercise review mutations on temporary copies. To rehearse against either the current DB or a pre-upgrade backup:

```powershell
.\.venv\Scripts\python.exe apps/api/tests/manual_metadata_acceptance.py
# Optional: add --database 'path/to/pre-upgrade-backup.db'
```

Restart the API manually to load the new rule, and rebuild/reload the frontend as appropriate. Do not restore an old database over newer research work; retain the upgraded DB and use forward review/repair. No application service is automatically restarted by this workflow.
