# Literature V2 delivery and acceptance

Date: 2026-09-21. Branch: `codex/literature-v2-canonical-library`. Baseline: `7354657`.

## 1. Current-state audit

See [audit.md](audit.md): traced source/cache/sync/Reader/AI/Radar/Agent paths, legacy schema versions 1–3, real database counts, and all seven requested PLAB reference files at commit `a04646aa5e5fc13502fd1918f2932f2598e628bd`. Baseline backend: 191 passing tests.

## 2. Target architecture

Workbench owns Literature documents. Zotero supplies external references, source metadata, notes and attachment descriptors. Radar remains a News-owned discovery/review domain; explicit save imports a canonical paper and origin. PDF upload stores a local asset separately from scholarly identity. All implementations are composed in app/main.py; no backend module imports another module or reads another module's tables.

## 3. Migration plan

See [design.md](design.md). Canonical foundation → additive legacy migration → source-scoped Zotero ingestion → canonical read/AI → explicit Radar save → PDF/native organization → acceptance. Legacy tables remain untouched snapshots. Automatic schema initialization backs up existing databases before migration. The repeatable CLI supports dry-run and real-run.

```powershell
$env:PYTHONPATH = 'apps/api'
.\.venv\Scripts\python.exe -m app.modules.literature.infrastructure.cache.migrate_canonical --dry-run
.\.venv\Scripts\python.exe -m app.modules.literature.infrastructure.cache.migrate_canonical
```

## 4. OpenSpec change

`upgrade-literature-canonical-library-v2`; proposal, design, audit, tasks and four capability deltas are committed. Strict validation passed. Legacy changes/specs were not removed or prematurely archived.

## 5. Data model

New Literature-owned tables: documents, paper_aliases, identifiers, source_references, origins, metadata_evidence, identity_conflicts, assets, source_notes, native_collections, native_memberships, source_collections, source_memberships, legacy_ai_snapshot and canonical_migrations (all prefixed `literature_`). Existing AI tables are reused with canonical paper IDs. Native state and soft removal live on documents.

## 6. Canonical identity strategy

DOI/arXiv/OpenAlex normalization, strong-reference agreement, then exact normalized title/year with shared author evidence. Different formal DOIs never silently merge. Preprint DOI and formal DOI can converge with supporting identity evidence. Conflicting arXiv/OpenAlex corrections require review instead of overwrite. BEGIN IMMEDIATE serializes concurrent ingestion. Workbench IDs and legacy aliases are durable. File SHA-256 identifies bytes, not arbitrary scholarly identity; an explicit target supports multiple versions and supplementary files.

## 7. Zotero semantics

Full and incremental sync update source evidence/resources and connector version atomically. Missing source references are detached; canonical papers, reading status, native tags/collections and AI are retained. A source deletion only deactivates children belonging to that exact source paper. Native collections are copied once and then independent. There is no Zotero write-back.

## 8. Radar semantics

Existing Agent v1/v2 ingest, News papers/runs/recommendations, latest run, diagnostics and four review states remain. An injected News export supplies persisted metadata and all appearances. Save creates or resolves one paper and atomically records appearance origins; refresh reads durable saved status. Radar is not an external-reference provider. Unreviewed runs create no Library records. Existing daily automation remains ACTIVE at 07:30 in the separate Personal-Workbench-Agent project and was not edited.

## 9. Asset semantics

Assets independently record UUID, role, storage kind, source parent, source version, hash, filename and availability. Zotero files stream through the existing authenticated adapter. Uploaded PDF bytes are validated, bounded to 50 MiB and atomically published under content-addressed filenames in `data/literature-assets/` (ignored by Git). Individual assets support open/download/ranges. Newly uploaded primary files become the default; supplementary files require an existing paper.

## 10. Metadata provenance

Each source observation retains original metadata, evidence, priority and timestamp. Canonical field choices expose their source/priority; weaker observations cannot overwrite stronger values. User tags survive source sync. Typed date evidence is retained per source. Conflicts and source collections are inspectable in paper provenance. Conflict correction UI and broader enrichment remain future work.

## 11. Legacy migration results

The real application initialized canonical migration during an interruption, before the final explicit CLI invocation. The final CLI correctly performed an idempotent no-op. Do not attribute later source-sync growth to the initial migration.

Verified real pre-migration backup:

`data/backups/literature-v2-20260921-153119-9960b43f.db`

| Metric | Initial migration | Current after subsequent source sync |
| --- | ---: | ---: |
| Legacy source papers retained | 59 | 59 |
| Canonical documents | 57 | 69 |
| Source paper references | 59 | 80 |
| Normalized identifiers | 63 | 75 |
| Assets | 83 | 105 |
| Source notes/annotations | 66 | 116 |
| Native collections | 14 | 15 |
| Legacy/source aliases | 59 | 80 |
| Original AI row snapshots | 12 | 12 |
| Conflicts/unresolved records | 0 | 8 |

Two pairs of legacy papers resolve to shared canonical identities. Initial migration had no conflicts. Seven legacy metadata tables compare exactly with the real backup. Every original AI/notes/text/message row is retained in migration snapshots; original analyses and notes remain readable via aliases. Both backup and live database return `integrity_check=ok`, with no foreign-key errors.

The eight later unresolved assets were investigated via read-only Zotero requests: all seven parent items are currently in Zotero trash. Two are PDFs and six are HTML/link descriptors. Their full payloads remain in literature_identity_conflicts; no guessed association or deletion was performed. Asset keys: C7PBMVW3, H6A3HUY4, 2SI8EAQT, 376E4VD4, X7VHIUEM, JJRQE23V, NE5K5YHQ, F6H7LLXW. These are connector quarantine records, not lost migrated papers.

## 12. API changes

Existing paper/collection/filter/notes/attachment/PDF/AI paths accept legacy and canonical IDs. New fields describe reading state, sources, file availability and metadata status. Added reading_status filter and optional asset_id on PDF open/download.

| Method/path (under /api/literature) | Behavior |
| --- | --- |
| POST /imports/radar/{recommendation_id} | Explicit idempotent saved-paper handoff |
| POST /imports/radar-saved | Read saved mappings for a bounded ID list |
| POST /imports/pdf | Raw PDF upload with filename/title/target/role |
| GET /papers/{id}/provenance | Sources, identifiers, origins, metadata and conflicts |
| PATCH /papers/{id}/state | Native reading status and tags |
| DELETE /papers/{id} | Recoverable Library removal; sync cannot resurrect it |
| POST /collections | Create native collection |
| PATCH /papers/{id}/collections/{collection_id} | Native membership |

News gained only an internal read-only export port; its HTTP ingest/review contracts remain unchanged.

## 13. UI changes

Literature now offers Library / Radar / Import. Library includes search, year/tag/venue/author filters, reading state, native collection creation/membership and source/PDF indicators. Detail includes local notes, AI, files, upload association and expandable provenance. Radar cards show Save to Library and persistent Saved links; News retains its existing Radar view. Import offers Zotero and PDF, with DOI/URL explicitly marked V2.1. No frontend router dependency was added.

## 14. AI compatibility

Overview, Deep Read, Ask, Selection, conversation ownership and My Notes resolve aliases before persistence/checks. Existing IDs, text and timestamps remain. PDF page cache keys include selected asset identity and hash/source version. Changing the primary PDF refreshes text. Metadata-only papers can use detail-page AI and My Notes. Existing analysis history is retained and explicit regeneration remains available.

## 15. Acceptance cases

| Case | Evidence / result |
| --- | --- |
| 1 Existing Zotero paper | Real copied DB migrates; 59 aliases verified; original metadata and AI reads pass; real remote PDF 206/signature passes |
| 2 Zotero removed | Full/incremental fixture retains canonical/native data; removing one duplicate source preserves other source assets |
| 3 Radar new paper | Real persisted recommendation saved through browser to isolated DB; Library origin recorded |
| 4 Radar existing Zotero paper | Integration fixture resolves to same canonical ID without duplicate |
| 5 Repeated Radar save | API replay and browser reload retain Saved; concurrency resolver test passes |
| 6 Manual PDF | Real HTTP upload to isolated app, duplicate/range/download tests pass; browser Reader renders page and selectable text |
| 7 Identity conflict | Formal DOI and identifier-correction tests reject silent merge; ambiguous legacy records retained/reported |
| 8 AI legacy | Real original notes/analysis read via aliases; conversation/message retention and continuation exercised with fixtures |

Browser additionally verified native collection creation, reading-state update, My Notes persistence, Radar diagnostics and saved status. UI actions affected only `.venv/tmp/literature-v2-acceptance-vbmlv6x6/acceptance.db`, not the real Library.

Live external checks on a separate copy (`.venv/tmp/literature-v2-acceptance-jntwu6lg/report.json`): Zotero incremental sync succeeded with 30 changed papers at version 7618; actual PDF range request returned 206 and `%PDF` header; configured AI generated/persisted a canonical Overview. No discovery run or remote Zotero mutation was triggered.

Browser limitation: the in-app browser's file chooser supplied a File that could not be read (`NotFoundError`, before any HTTP POST). Both Windows and slash paths referenced an existing file. Therefore the native picker → upload-button path is NOT claimed as passed. API upload, concurrent storage, persisted association and actual browser Reader are verified; a normal browser picker smoke check remains recommended.

## 16. Tests

- Full backend: **209 passed**, one pre-existing Starlette/httpx deprecation warning.
- Frontend TypeScript checks and Vite production build: passed.
- compileall: passed after allowing writes to project __pycache__.
- git diff --check: passed.
- Secret scan: configured secret values and token/private-key patterns absent from staged changes; final branch scan repeated before push. No .env, databases, dependencies or build artifacts are staged.
- Migration dry-run/real replay, per-table preservation, concurrent identity/PDF ingest, rollback and original AI snapshot checks: passed.

Reproducible isolated manual acceptance: `PYTHONPATH=apps/api python apps/api/tests/manual_canonical_acceptance.py`; add `--live-check` for configured external providers or `--serve` for a loopback-only static-build/API test surface on 8765. It uses a fresh DB copy.

## 17. OpenSpec validation

`openspec validate upgrade-literature-canonical-library-v2 --strict` passed. Delivery tasks and limitations are recorded rather than silently deleting unfinished verification caveats.

## 18. Git commits

- `6a1daea` docs: current-state audit, migration design and OpenSpec.
- `bd2c606` canonical identity and recoverable migration.
- `fb164f1` source/Radar/assets/AI integration and tests.
- `749d6e0` native Library/Radar/Import UI.
- Final acceptance/documentation commit follows these.

## 19. Remote branch

Delivery target: `origin/codex/literature-v2-canonical-library`. Push is verified in the final task response. No merge into main is authorized or performed.

## 20. Known limitations and operations

- In-app browser file picker limitation described above; real HTTP upload and Reader are verified.
- Eight source attachments have trashed parents and remain quarantined with evidence.
- DOI/URL enrichment, BibTeX/RIS, OCR, external file caching and a conflict-resolution UI are deferred.
- Legacy tables remain initial snapshots, not a continuously updated rollback mirror. Soft removal retains data; explicit import/save can restore known identity. There is no Trash management UI yet.
- Canonical metadata queries currently scan the small single-user Library; large-library indexing is future work.
- Existing cached analyses remain history after file changes; explicit regeneration uses the current file. Page-text cache is automatically asset-aware.
- Automatic migration backs up and runs transactionally; no service was restarted by this task. Restart the API manually to load final backend changes; restart/reload the frontend as appropriate for the deployment. Do not run pre-V2 source-sync code against an actively used V2 library.

Rollback: stop the API manually, preserve the upgraded DB and local asset directory, and restore the verified backup ONLY if there have been no subsequent user writes. Otherwise use forward repair/export; never overwrite later work. Rollback was rehearsed into a separate database, not over live data. At handoff the real DB already has subsequent sync changes, so restoring the initial backup would discard those changes and is not recommended.

## 21. Recommended V2.1 scope

DOI/URL metadata enrichment and reviewed correction, source-conflict/quarantine resolution, richer date/version relationships, explicit primary-file selection, BibTeX/RIS import, native collection rename/move/Trash UI, and asset garbage-collection policy. Keep Project/Todo/Feedback/knowledge-graph work outside this scope.
