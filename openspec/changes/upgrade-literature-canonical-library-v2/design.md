# Literature V2.0 Migration Plan

## Context

See audit.md for traced ownership, real DB counts, legacy migrations and PLAB findings; proposal.md for motivation. The existing source cache and its tests remain available during transition. All four backend modules retain separate ownership.

## Goals / Non-Goals

Use an additive canonical repository implementing existing Literature ports, retain working source adapter/AI/file contracts, and make migration measurable and recoverable. No worker platform, cross-module SQL/imports, automatic discovery-to-library ingestion, or remote Zotero writes. DOI/URL enrichment and external file downloading beyond existing Zotero support are V2.1.

## Decisions

### Additive ownership and source snapshots

New literature canonical tables store documents, aliases, references, origins, assets, source notes, native collections/memberships, source collections and evidence/conflicts. Keep legacy literature_papers/collections/notes/attachments/references untouched after migration as the initial source snapshot. A new SQLite canonical repository reuses proven AI persistence, replacing source-cache read/write paths in composition. This avoids destructive PK rewrites and keeps legacy schema v1–v3 replay testable. Canonical schema uses its own migration ledger. References use a unique provider/library/item tuple, independent from document ID, and active/detached state. Source metadata is retained even after detachment.

### Identity resolution

Normalize DOI/arXiv/OpenAlex locally within Literature; do not import News helpers. Resolve known aliases and source reference, then DOI, arXiv, stable external identifiers, then exact Unicode-normalized title/year with compatible author evidence. Never match empty/generic titles or unknown years without identifiers. Collect all strong matches and reject disagreement. Different formal DOIs cannot merge even with identical title. arXiv DOI is preprint evidence, not a competing formal DOI; merging preprint/formal requires shared arXiv or sufficiently corroborated title/year/authors. Identifier correction under a stable source requires an evidence gate; otherwise retain existing identity and record a conflict. Legacy ambiguous records each retain an auditable canonical record without claiming another record's conflicting identifier. Public ingest returns explicit 409 on conflict. Serialization uses BEGIN IMMEDIATE and unique indexes for concurrent idempotency.

### Metadata evidence

Each ingestion stores a bounded original metadata snapshot plus source, origin key, confidence/priority and observation time. Canonical field selection fills blanks or accepts stronger evidence; equal-priority same-source updates can revise nonidentity fields. Weaker sources do not overwrite stronger fields. Formal publication DOI supersedes preprint DOI only after safe identity resolution; retain both references/evidence. Date evidence remains typed JSON (preprint/online/issue/unknown) rather than reducing all dates to a conflict. Conflicting candidates remain inspectable in detail. New manual PDFs may create incomplete documents with low-confidence filename title.

### Native organization and connector sync

Migrate source collections to deterministic native UUIDs with a separate mapping. Copy memberships initially; subsequent connector sync updates external collection metadata/membership, not user-owned native membership or names. New source collections are imported once. Reading state is inbox/saved/reading/read/archived and independent of Radar new/seen/interested/dismissed. Library deletion is recoverable soft removal; source sync cannot resurrect a user-deleted Library paper. Explicit user save/import can restore it.

Full sync records incoming source IDs and detaches missing references only in that provider/library scope; incremental removal detaches exact source resources and paper reference. Keep cached notes and file descriptors but mark unavailable resources detached. Do not delete canonical documents, native state, or AI. Persist sync version in the same transaction as changes.

### Radar handoff without module coupling

News exposes a read-only application export of a persisted recommendation and all appearances for its research paper, as plain data. Composition root injects that callable into Literature ingestion service. Literature converts it to its own domain ingestion DTO and records Radar origin snapshots; Radar is never an external reference provider. Save is an explicit Literature endpoint keyed by recommendation ID. A read-only batch saved-status lookup supports refresh without creating origins. Existing News endpoints, digest replay and automation remain unchanged.

### Files and AI

Assets have independent UUID, paper ID, role, storage kind, source reference, content hash and availability. Legacy attachment IDs are aliases. Manual upload uses a bounded raw PDF request (avoids a multipart dependency), validates actual PDF structure, stores bytes through a Literature file-store port, and associates them transactionally. Hash reuse is within an explicitly associated paper; supplementary hashes cannot define paper identity. Reader supports primary and individually selected asset streams, download and byte ranges. Original filenames never become storage paths.

Resolve legacy aliases before all AI reads/writes and ownership checks. Rebind AI paper_id columns transactionally; preserve complete pre-migration AI row snapshots for audit, including text-cache collisions. Keep conversation/message/note IDs and bodies. Cache pages are invalidated when selected primary asset changes and include asset identity in extractor version. Keep pypdf and lexical chunking; processing remains on-demand.

## Risks / Trade-offs

- Live API can hold SQLite handles → use SQLite online backup and transactional migration, test copies before real run; never restart background services.
- Irreconcilable legacy identity → preserve separate document, original snapshot and report; do not guess.
- External file may disappear → preserve paper and descriptor, report unavailable; only manual uploads guarantee local bytes.
- Frozen legacy snapshot is not a continuous rollback mirror → retain complete DB backup and do not restore over post-upgrade user writes. Prefer forward repair/export.
- New metadata-only papers lack text for Ask → existing stable context errors; Overview can use metadata, no fabricated PDF.

## Migration Plan

A. Complete audit/proposal/specs, strict validate, commit documentation. Build canonical model/resolver with conflict and concurrency tests.

B. Implement additive migration and report command. SQLite backup before ANY canonical migration of an existing populated DB, verify backup integrity. Dry-run on a copied DB and compare source-table/AI content counts. Migrate under transaction with durable aliases, snapshots and report. Repeating migration is a no-op.

C. Wire Zotero connector and canonical reads. Verify full/incremental sync/deletion on fixtures, native membership survival and legacy route compatibility.

D. Add persisted News recommendation export, explicit Save and saved status. Verify new/existing/repeated/concurrent save and unchanged Radar/News ingest.

E. Add bounded PDF import, association and local file serving; expose native organization and Library / Radar / Import UI.

F. Canonicalize AI and selected-asset text cache; verify legacy AI/note content and fresh canonical persistence.

G. Run full backend, frontend build, compileall, diff check, secret scan and real DB dry-run/backup/migration. Exercise real local metadata/PDF/AI where configured, use fixture evidence for deletion/conflict and clearly label external-service limitations. Keep legacy schema; retire only composition assumptions. Commit logical stages and push feature branch, never merge main.

Rollback before new user writes: stop API manually, preserve upgraded DB and assets, restore the verified pre-migration database using SQLite backup and return to pre-upgrade code. Never overwrite a DB with subsequent work; use forward repair from aliases/snapshots or a reviewed export. Rehearse rollback into a separate temporary database, not over live data.
