# Literature V2 backend API contract — Stage 1 / Stage 2

Frozen for `claude/literature-v2-backend-workflows`, 2026-09-21. Base URL `/api/literature`. The existing frontend is unchanged in this backend-only delivery. Consumers must treat every ID as opaque, URL-encode path parameters, and never derive Zotero keys from canonical IDs. `/openapi.json` includes request schemas and typed workflow responses.

## Common rules

- Request/response JSON uses snake_case. All timestamps are UTC ISO-8601; timestamps/IDs are server-assigned. Raw PDF bodies use `application/pdf` and a 50 MiB maximum, not base64 or multipart.
- `sources` contains active external-reference providers, e.g. `zotero`. `origins` contains ingestion/discovery kinds, e.g. `zotero_import`, `zotero_selective`, `radar`, `manual_pdf`, `zotero_materialization`, `legacy_recovery`. An origin is not a source. Frontend clients must render both categories separately when needed.
- Reading state: `inbox | saved | reading | read | archived`. Radar review state remains `new | seen | interested | dismissed` in News and is independent.
- Stable errors have `{"detail":{"code":"..."}}`; a safe reason/candidates array may be included. 404 `workflow_not_found`, 409 `workflow_conflict`, 409 `identity_conflict`, 409 `migration_required`, 413 `pdf_too_large`, 422 validation/`invalid_upload`/`invalid_update`/`invalid_proposal`/`invalid_pdf`. Pydantic validation uses the standard FastAPI detail array. Existing provider errors remain 503 `provider_not_configured`, 502 `provider_authentication_failed`/`provider_unavailable`.
- A workflow batch can succeed partly. HTTP 200 confirmation/materialization responses must be inspected per item; HTTP success alone does not mean every item succeeded. Operational provider failures expose stable codes, not raw exceptions, paths or credentials.
- Source identity conflicts do not silently merge. Formal DOI replacement/removal and conflicting arXiv/OpenAlex changes remain gated even in user-edited proposals. No generic arbitrary metadata object may modify ownership, IDs, state or file paths.

## A. Library queries and detail

| Method/path | Request | Response |
| --- | --- | --- |
| GET `/status` | none | module, provider, provider_configured, sync_state, library_version, last_synced_at |
| GET `/papers` | limit 1–100 (50), offset ≥0, collection_id, query, author, year, journal, tag, reading_status | `{items: Paper[], total, library_version}` |
| GET `/papers/{paper_id}` | canonical or legacy alias | `{paper: Paper, collections: Collection[], pdf_available}` |
| GET `/filters` | none | `{years: int[], journals: string[], tags: string[]}` |
| GET `/papers/{paper_id}/provenance` | canonical or alias | references, identifiers, origins, metadata_evidence, selected_fields, conflicts, source_collections |
| GET `/papers/{paper_id}/notes` | canonical or alias | `{items: SourceNote[]}` |

`Paper`: id, title, authors[], abstract?, year?, journal?, doi?, tags[], external_ref? (legacy compatibility), arxiv_id?, openalex_id?, reading_status, sources[], origins[], pdf_available, metadata_status, date_evidence{}, primary_asset_id?. `metadata_status` is `incomplete`, `complete`, or `conflict`; complete is field completeness, not scholarly verification. Origin snapshots retain discovery time, run, rank, scores, reason and AI summary. Provenance is inspectable evidence, not an instruction to trust every candidate.

`SourceNote`: id, paper_id, content, kind (`note|annotation`), page_label?, color?, external_ref?, source_paper_id?, active. Detached notes remain available as historical source evidence.

## B. Native organization and state

| Method/path | Request | Response |
| --- | --- | --- |
| GET `/collections` | none | `{items: Collection[]}` |
| POST `/collections` | `{name: string(1..200), parent_id?: string}` | 201 Collection |
| PATCH `/papers/{id}/collections/{collection_id}` | `{present: boolean}` | `{present}` |
| PATCH `/papers/{id}/state` | `{reading_status?: enum, tags?: string[]}` | updated Paper |
| DELETE `/papers/{id}` | none | `{deleted:true,recoverable:true}` |

`Collection`: id, name, parent_id?, external_ref?. Native collection IDs are independent from Zotero. Source collection metadata/membership is separate. Source sync cannot delete native collections, overwrite explicit tags/state, or resurrect a removed paper. Soft-deleted data is retained; explicit import of a known source identity can restore it. No Trash/rename/move API is introduced here. State edits made by this version are audited for reconciliation safety.

## C. PDFs and assets

| Method/path | Request | Response |
| --- | --- | --- |
| GET `/papers/{id}/attachments` | none | `{items: Attachment[]}` |
| GET `/papers/{id}/pdf` | optional asset_id, Range header | PDF 200/206; 416 unsatisfiable local range |
| GET `/papers/{id}/pdf/download` | optional asset_id, Range header | attachment disposition; same range semantics |
| POST `/imports/pdf` | raw PDF; filename (≤240), optional title (≤1000), paper_id, role | 201 `{paper_id,created,reason,asset}` |

`Attachment`: id, paper_id, filename, content_type?, downloadable, link_mode?, external_ref?, role (`primary|preprint|supplementary`), storage_kind (`zotero|local`), storage_key?, sha256?, active, content_version?, source_paper_id?, plus API availability. Storage keys are opaque, not local filesystem paths. Local bytes live in `literature-assets/originals/{hash}.pdf`; old flat paths remain read-compatible.

Single-shot `/imports/pdf` remains backward compatible and is an explicit immediate save. New staged workflows below are the review-before-save alternative. Uploading supplementary/preprint files requires an existing paper. Primary-file changes invalidate page text via asset/hash/version. Historical analyses are preserved; regeneration remains explicit.

## D. Staged PDF upload workflow

| Method/path | Request | Response |
| --- | --- | --- |
| POST `/uploads/batches` | no body | 201 UploadBatch |
| POST `/uploads/batches/{batch_id}/files` | raw PDF, filename query | 201 UploadItem |
| GET `/uploads/batches/{batch_id}` | none | UploadBatch or 404 |
| PATCH `/uploads/batches/{batch_id}/items/{item_id}` | MetadataPatch | UploadItem |
| POST `/uploads/batches/{batch_id}/confirm` | none | `{results: UploadConfirmResult[]}` |
| POST `/uploads/batches/{batch_id}/cancel` | none | UploadBatch |
| POST `/uploads/batches/{batch_id}/items/{item_id}/cancel` | none | UploadItem |
| POST `/uploads/cleanup` | max_age_seconds ≥3600 (3600) | `{removed:int}` |

`UploadBatch`: id, status, items[], created_at, confirmed_at?, cancelled_at?. At most 50 files. Status is staging → reviewing (partial result or metadata edits) → confirmed/cancelled. A confirmed batch cannot be edited/cancelled. An empty batch cannot be confirmed.

`UploadItem`: id, batch_id, filename, staging_key, sha256, status, extracted_metadata{}, candidate_metadata{}, warnings[], target_paper_id?, error?, created_at, updated_at. Extracted fields have `{value,source,confidence}` and remain separate from user edits. Current extractor reads PDF info and at most three pages; no OCR, AI call or network lookup. File creation date has low confidence and an explicit warning; scanned identifiers require review. A missing title is `needs_review`; user must supply it before confirmation.

`MetadataPatch`: only title (nonblank ≤1000), authors (≤100 nonblank strings of ≤512), year (strict integer 1000..3000), doi, arxiv_id, journal (≤1000), abstract (≤30000). Fields not supplied remain unchanged. Optional text/year may be cleared with null; authors clear with `[]`. Existing identifiers cannot be removed by proposal acceptance. IDs/reading state/path keys and unknown fields are rejected. DOI/arXiv values normalize on update/decision.

`UploadConfirmResult`: item_id, status (`confirmed|already_confirmed|cancelled|conflict|needs_review|failed`), paper_id?, asset_id?, created?, error?. Each item commits canonical identity, asset and confirmed status in one DB transaction. Successful siblings are retained if another fails. Conflicting/failed items remain editable and retryable; staging bytes remain referenced until success/cancel. Identical file replay reuses stable file-origin identity and asset. Cancelled items are skipped by confirmation. Cancel of a partial batch preserves already-confirmed Library items and originals.

Finalize publishes complete content-addressed originals, checks the hash, and keeps staging through the DB commit. A crash after publishing but before committing can leave a safe unreferenced original; retry reuses it. Cleanup deletes only old unreferenced/closed staging, under the repository write lock shared with registration/confirmation. It never removes originals or active review items. Failed file cleanup after a DB success is retried by cleanup.

Example:

```http
POST /api/literature/uploads/batches
POST /api/literature/uploads/batches/{batch}/files?filename=paper.pdf
Content-Type: application/pdf

<PDF bytes>
```

```json
{"title":"Reviewed title","authors":["Alice Smith"],"year":2026,"doi":"https://doi.org/10.1234/example"}
```

Send that JSON to the item PATCH endpoint, then POST confirm. Staging and extraction alone create no Library paper.

## E. Zotero selective import and PDF materialization

| Method/path | Request | Response |
| --- | --- | --- |
| GET `/imports/zotero/collections` | none | `{collections: Collection[]}` from connector |
| GET `/imports/zotero/items` | collection_id?, limit 1–100, offset≥0 | `{items: (Paper + import_status + canonical_id)[], total}` |
| POST `/imports/zotero/selective` | `{item_keys:string[1..100]}` | `{results: ImportItemResult[]}` |
| POST `/papers/{id}/materialize-pdf` | none | MaterializationResult |
| POST `/papers/materialize-pdfs` | `{paper_ids:string[1..50]}` | BatchMaterializationResult |
| POST `/sync`, `/sync/async` | existing contract | existing sync result/task |

Pass selected `items[].id` unmodified as item_keys; the provider also accepts a valid raw Zotero item key. Only the provider interprets connector identifiers and rejects another library's ID, trashed items and non-paper items. Selected import loads the paper, source collections and ancestors, child notes/attachments and attachment annotations. It resolves/merges canonical identity, records `zotero_selective` origin, initializes new papers as saved, and preserves state on existing papers. It does not advance the global incremental sync cursor. Browse import_status means this source item is already attached; a DOI-only canonical match can still be resolved at import.

`ImportItemResult`: item_key, paper_id?, status (`imported|already_exists|conflict|failed`), created, error?. Duplicate input IDs are processed once. Source failures and identity conflicts are per-item results.

`MaterializationResult`: paper_id, status (`materialized|already_local|pdf_missing|pdf_failed|pdf_skipped`), asset_id?, sha256?, error?. Alias input returns canonical paper_id when resolved. Local primary must actually open before returning already_local. A local supplementary PDF does not suppress remote primary materialization. Remote stream is bounded to 50 MiB and always closed, including size/transport failures. Source asset/version is checked again before the local asset and primary selection commit. Local bytes stay readable if Zotero becomes unavailable.

`BatchMaterializationResult`: total, materialized, already_local, missing, failed, skipped, results[]. Duplicate IDs are coalesced; no input silently truncated. Calls are synchronous, bounded, and continue after per-paper failures; no worker/automatic backfill was introduced.

## F. Metadata proposal review

| Method/path | Request | Response |
| --- | --- | --- |
| GET `/papers/{id}/metadata/proposals` | none | `{proposals: MetadataProposal[]}` |
| POST `/papers/{id}/metadata/proposals` | `{source:string(1..100),proposed_metadata:MetadataPatch}` | 201 MetadataProposal |
| GET `/metadata/proposals/{proposal_id}` | none | MetadataProposal |
| POST `/metadata/proposals/{proposal_id}/accept` | none | MetadataProposal |
| POST `/metadata/proposals/{proposal_id}/reject` | none | MetadataProposal |
| POST `/metadata/proposals/{proposal_id}/edit-accept` | `{edits:MetadataPatch}` | MetadataProposal |

`MetadataProposal`: id, canonical paper_id, source, status (`pending|accepted|rejected`), current_metadata, proposed_metadata, fields_changed[], created_at, resolved_at?, resolved_by?. Creation captures normalized proposed fields and a current snapshot; no-op proposals are rejected. All decisions lock and recheck pending status; accept/edit-accept compare current metadata to the captured snapshot. Stale decisions return 409 without silently overwriting another update. Reject never changes paper metadata. Resolved proposals cannot be decided twice (409).

Both acceptance paths apply identical identifier/field validation. New identifiers are globally checked and indexed in the same transaction as metadata, provenance and proposal status. Before/after values and edits are retained. Source priority is 95 for accepted proposals and 100 for edited user decisions; ordinary Zotero metadata cannot overwrite stronger accepted fields. This is a proposal review API, not an automatic enrichment or AI suggestion generator.

Existing `/papers/{id}/ai/*` and `/user-notes` paths remain unchanged, including canonical alias ownership checks and old conversation/note IDs. They also return 409 migration_required when legacy identity migration is pending.

## G. Explicit migration and reconciliation

| Method/path | Request | Response |
| --- | --- | --- |
| GET `/migration/status` | none | `{migration_required:boolean}`; read-only |
| POST `/migration/run` | dry_run boolean query (false) | `{status:migrated|already_migrated,report:{...},dry_run:boolean}` |
| POST `/migration/reconcile-reading-status` | none | `{corrected:int,already_applied:boolean}` |

Canonical data migration ledger remains version 1; workflow DDL uses independent `literature_workflow_schema` version 2. Already-canonical databases gain workflow tables without replaying identity migration. Legacy data is not migrated on GET or sync. Pending canonical reads/writes return 409 until explicit migration. Empty fresh databases initialize normally. Status checks do not create a database or schema. Routine DDL initialization can add tables, but never migrates paper/AI ownership.

Explicit migration backs up the SQLite database before schema/data work, then transforms data atomically; failure retains legacy data and leaves the migration pending for retry. Dry-run copies first and leaves original bytes unchanged. A returned dry-run backup path is ephemeral, not a durable recovery backup. Real runs report a durable backup path; repeats return already_migrated. CLI remains available:

```powershell
$env:PYTHONPATH = 'apps/api'
.\.venv\Scripts\python.exe -m app.modules.literature.infrastructure.cache.migrate_canonical --dry-run
.\.venv\Scripts\python.exe -m app.modules.literature.infrastructure.cache.migrate_canonical
```

New legacy migrations initialize retained/recovered papers as saved. For already-migrated v1 databases, reconciliation is explicit and one-time, records its report, selects only original legacy aliases that remain inbox and are not removed, and excludes state edits recorded by this backend. It does not change reading/read/archived/saved or later Radar/upload papers. Historical v1 did not audit a user's explicit choice of inbox, so that historical choice cannot be distinguished from its default; operators should review this narrow correction before invoking it. No reconciliation is run on application startup or GET.

Rollback of workflow DDL is unnecessary for data preservation: new tables are additive and legacy data remains. Preserve upgraded DB/assets before any code rollback. Never restore an old backup over later user writes. No real-library workflow decisions or background service restarts are performed by the delivery verification.
