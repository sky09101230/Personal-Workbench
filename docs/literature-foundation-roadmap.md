# Literature foundation: audit and staged Goal

Audit date: 2026-09-22. Baseline commit: `6712bb6840a28713bed243a0ca239f6ea56b3896`.
Working branch: `codex/literature-foundation`. Goal is active. This document records observations and acceptance gates, not a claim that planned features are delivered.

## Scope and invariants

Build reliable canonical identity, Workbench-owned assets, and evidence-driven metadata/provenance. Preserve canonical IDs, aliases, Notes, AI history, native collections/tags/reading state, source references and Radar origins. No automatic merge or split of existing records. No dependency on private repositories. Existing AI reading remains supported; new parsing, chunking, embeddings, vector stores, RAG and maps are out of scope.

## Implementation audit

| Area | Current implementation | Gap / consequence |
| --- | --- | --- |
| Identity | `domain/canonical.py` normalizes DOI/arXiv/OpenAlex; `infrastructure/cache/canonical.py::_ingest` gathers canonical ID, alias, external tuple, origin and scholarly matches in one transaction | It also automatically reuses a document for exact normalized title/year/shared-author matches. Weak evidence can merge unrelated records. |
| DOI/preprints | Different formal DOIs and conflicting arXiv/OpenAlex are rejected; shared arXiv can connect a publication DOI | Syntax is not verification. A source update can promote preprint to publication without an explicit review decision; version evidence is not modeled separately. |
| Canonical data | `literature_documents`, unique identifier index, aliases, source references, origins and per-field source/priority | `complete` only means title/authors/year present. It does not answer identity verification or conflict lifecycle. |
| Metadata | `_ingest` stores source evidence, fills blanks and lets higher priority or same-source equal priority replace nonidentity fields | Priority is not a reliable conflict decision. Source refresh can silently change accepted fields. Selected fields record source/priority, not a specific evidence row. |
| Review | Workflow repository + `MetadataReviewService` + `MetadataReview.tsx` already support propose/accept/reject/edit, snapshots, stale checks and identifier ownership checks | Conflicting identity proposals are rejected before persistence; legacy conflicts have no decision workflow. Reuse this UI and transactions rather than introduce a second generic workflow engine. |
| Upload | `UploadWorkflowService` stages, extracts candidates, confirms each item transactionally and retains failed items; raw PDF import also exists | Both call `_ingest_asset`, but orchestration differs. New-upload origin uses hash: useful replay identity, not scholarly proof. Extracted DOI can be a cited paper's DOI; explicit user confirmation is currently the gate. |
| Zotero | Selective import and full/incremental sync share canonical ingestion; separate source descriptors and notes are retained | Import commits descriptors before optional local materialization. The real library currently has no owned PDF bytes. |
| Materialization | `PdfMaterializationService` bounds downloads to 50 MiB, closes streams, stores and selects local primary, records source asset/version | Only selected primary is copied. Supplements/other versions need an explicit plan. Existing local file check only opens it; it does not verify checksum. |
| Storage | Existing `LiteratureFileStore` Protocol, `LocalLiteratureFiles`, SHA-addressed originals and staging; asset has storage kind/key/hash | Composition fixes root beside DB. No independent configuration, inventory/integrity report or relocation rehearsal. `open` checks key shape but not checksum/symlink containment. Reuse the port and layout. |
| Reader / AI | `LiteratureService.open_pdf` routes local vs provider, supports ranges; AI uses canonical aliases and asset-aware text cache | A remotely backed descriptor is still reported PDF-available. Need a clear owned/remote/missing/corrupt distinction while preserving API compatibility. |
| Radar / Agent | News owns research ingest. Composition injects a persisted export into Literature; explicit Save attaches all appearances | News has its own weaker research identity rules. A grouped set of discovery appearances must not itself become strong Literature identity evidence. Revalidate handoff without cross-module SQL/imports. |
| Migration | Legacy snapshots, SQLite backup, explicit migration gate, dry-run copy and replay ledger already exist | Do not rerun historical migration or rewrite aliases to enforce new rules. Audit old merge evidence and report uncertainty, never guess a split. |

Entry paths traced: selective Zotero import → workflow `_ingest`; sync/legacy migration → `_preserved_ingest` → `_ingest`; Radar save → `ingest_appearances`; immediate/staged PDF → `_ingest_asset`; materialization → `_ingest_asset` with known canonical ID. The common transaction resolver is the first safety boundary to fix.

### OpenSpec state

`upgrade-literature-canonical-library-v2` is complete (31/31) but unarchived; its canonical capability is not yet in main specs. Its older design explicitly allows title fallback. Later V2 workflow design and `docs/handshake/literature-v2-stage3-acceptance.md` supersede early acceptance statements about automatic migration, absent review UI and picker limitations. This Goal will not silently archive other completed changes. New `literature-identity-evidence` specifies the stricter boundary and explicitly supersedes the V2 title-fallback rule for future Literature ingestion. News research identity remains a separate capability.

## Real data audit (read-only)

Opened configured `data/workbench.db` with SQLite `mode=ro` and a read transaction; did not instantiate a repository that could initialize schema. `integrity_check=ok`, no foreign-key errors. No source sync, remote requests, schema writes, service restart or data migration occurred.

| Metric | Count |
| --- | ---: |
| Canonical documents | 69 |
| Identifiers | 75 (66 DOI, 9 arXiv) |
| Documents without indexed scholarly ID | 3 |
| Canonical aliases | 80 (69 new, 11 stable_identifier; no title-fallback reason recorded) |
| Source references / origins | 80 / 80 |
| Metadata evidence / proposals | 89 / 0 |
| Metadata complete / incomplete | 63 / 6 |
| Assets | 105, all active Zotero descriptors |
| PDF / HTML descriptors | 87 / 18 |
| Local assets / checksummed assets | 0 / 0 |
| Historical unresolved records | 8, all `Source asset parent unresolved` |
| Native collections / memberships | 15 / 80 |
| Source notes | 116 |
| User notes / analyses / cached pages | 2 / 1 / 9 |
| AI conversations / messages | 0 / 0 |
| Preserved legacy AI snapshots | 12 |
| Original legacy papers / attachments / notes | 59 / 83 / 66 |

The 87 PDF descriptors have `downloadable=true`; this is not evidence that 87 downloads will succeed. No claim about remote availability is made. Prior documentation reports trashed parents for the eight unresolved records; that external state was not rechecked. Alias reasons contain no recorded weak merges, but this alone cannot prove all historical evidence was correct. Audit identifier/evidence consistency before any remediation.

Baseline: full backend **225 passed**, one existing Starlette/httpx deprecation warning. No frontend change or new browser verification in this planning stage.

## Sequential roadmap

Only create/implement one Change at a time. Names after Change 1 are provisional and may change with evidence.

| Order | Change / boundary | Migration / real acceptance gate |
| --- | --- | --- |
| 1 | `tighten-literature-identity-evidence`: strong evidence only for automatic association; weak matches become explicit review candidates/errors; distinguish file replay from scholarly evidence; audit historical identity without rewriting | Read-only identity audit, copied real DB before/after preservation comparison, concurrent/replay/conflict tests across existing adapters. No automatic split/merge or live canonical rewrite. |
| 2 | Harden existing local Vault: independently configured root, backend/key contract, contained immutable file access, checksum/size verification and inventory; safe copy/verify relocation | Keep current root and keys as default, recognize legacy flat files. Missing/corrupt files are reported, not deleted or silently replaced. Rehearse copied Vault under another root with unchanged IDs. |
| 3 | Evidence-driven ingestion/review: reuse common resolver and proposal workflow; retain incoming conflicts, stable evidence IDs, explicit decision status, version evidence; expose review and asset state in existing UI | Additive schema with backup, dry-run and replay. Test source refresh cannot overwrite accepted metadata; stale review and conflicting identity cannot mutate canonical ownership. Browser acceptance on disposable data. |
| 4 | Migrate existing assets into owned Vault: per-asset plan for available Zotero PDFs including supplementary/version assets, resumable bounded acquisition, source provenance and integrity report | Dry-run first; online DB backup before writes; per-file verified publish then transactional association; preserve source descriptors/IDs and research state. Repeated run is a no-op for verified assets. Unavailable or unresolved assets remain explicit exceptions. No source deletion. |
| 5 | Close operational gaps: integrated audit/review/integrity, source-offline behavior, duplicate bytes, recovery and storage relocation; finish only remaining requirements | Full backend/build, browser workflows, copied real data preservation, real owned-byte checksum inventory, repeat/dry-run/recovery checks and an honest exception report. Document manual restarts required. |

Each Change must document why, scope/non-goals, design, migration strategy, tests, actual acceptance evidence, strict OpenSpec validation and a focused Conventional Commit. Finish/validate/commit the current Change before implementing the next. Update this ledger at every checkpoint; do not mark the Goal complete for documentation or synthetic tests alone.

## Design constraints for subsequent stages

Canonical ID, scholarly identifiers and file SHA-256 remain distinct. A valid DOI is a claimed identifier until supported by recorded evidence; do not label syntactically valid source metadata verified. No DOI is required for import. Conflicting or insufficient evidence stays unresolved/reviewable. Shared arXiv and later DOI require explainable version evidence or explicit review; title similarity alone never promotes a version.

Maintain one core ingestion policy behind adapters, using existing ports/SQLite transactions. Future Agent entry is an adapter to that policy, not a new parallel store. The storage backend contract must allow future NAS/WebDAV/S3 without implementing those backends now. The current `staging/` and `originals/` layout is sufficient; add directories only for concrete lifecycle operations, not cosmetic resemblance to the requested example.

Real migration uses SQLite online backup, independent file copies, verified checksums and transactionally recorded progress. Preserve all source bytes and descriptors. Recovery after subsequent user writes is forward repair; never restore an old DB over new research state. No garbage collection or automatic quarantine deletion in this Goal.

## Progress

- [x] Current implementation, workflow and real-data read-only audit.
- [x] Baseline backend verification and dependency-ordered roadmap.
- [x] Change 1 proposed, implemented, accepted, validated and committed: `tighten-literature-identity-evidence`; 231 backend tests; copied real DB preservation across 55 tables. See its acceptance.md.
- [ ] Change 2 accepted and committed.
- [ ] Change 3 accepted and committed.
- [ ] Change 4 accepted and committed.
- [ ] Change 5 accepted; final Goal gaps reviewed and closed.
