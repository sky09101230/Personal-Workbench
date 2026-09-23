# Literature foundation acceptance matrix

Checkpoint: 2026-09-23, branch `codex/literature-foundation`.

| Original requirement | Evidence | Result / boundary |
| --- | --- | --- |
| A paper has a reliable canonical identity | Strong DOI/arXiv/OpenAlex resolver; weak-match conflict queue; snapshot identity confirmation/correction; version links retain two IDs | Pass. Human confirmation is explicitly not scientific registry verification. |
| Weak evidence never silently merges | 10 identity review tests; `keep_separate` requires exact reviewed retry and cannot override strong owners | Pass. Existing history is preserved. |
| Conflicts and metadata are explainable | Evidence-linked proposals, identity conflict history, reasons, before/after snapshots, decision-aware audit | Pass. Eight historical orphan descriptors remain unresolved/quarantined candidates. |
| PDF bytes are Workbench-owned and content identified | 49 source mappings to 47 SHA-256 verified local objects; Vault integrity endpoint and offline Reader | Pass for available sources. 38 source PDFs remain unavailable. |
| Duplicate PDF bytes are safe | Same content reused per paper/role; distinct papers remain separate; original filenames are not storage keys | Pass. |
| Zotero failure does not break owned reading | Offline Reader full/range reads verified against a provider that raises on every call | Pass for 44 default-primary papers and 47 owned objects. |
| Every entry uses one ingestion policy | Zotero/Radar/upload/materialization route shared canonical and acquisition services; Radar saves only selected recommendation | Pass. |
| Old data is protected | 52 protected tables unchanged in copied migration verification; all original rows retained; source file hashes unchanged; SQLite integrity/FK checks pass | Pass. Real DB received only additive schema/state writes after backup; no Notes/AI/metadata rewrite. |
| Migration is dry-run, bounded, resumable and idempotent | Plan digest, offsets, per-file JSONL reports, backups, retry/replay tests and real five-batch run | Pass. |
| Future storage can replace local backend | `LiteratureFileStore` declares backend; alternate backend contract test passes; domain stores opaque backend/key/hash | Pass; no NAS/WebDAV/S3 implementation claimed. |
| Metadata is evidence-driven | Source refresh proposals, current snapshot confirmation, identifier correction and evidence IDs | Pass. |
| PDF migration has truthful exceptions | 38 unavailable sources (29 papers; 21 without another owned primary), eight unresolved-parent descriptors, 18 non-PDF exclusions, one oversized PDF acquired through 256 MiB disk staging | Pass as an exception report; recovery is incomplete by definition. |

## Verification commands

```powershell
$env:PYTHONPATH = 'apps/api'
.\.venv\Scripts\python.exe -m pytest -q apps/api/tests --basetemp .venv\tmp\pytest-final -p no:cacheprovider
npm.cmd --prefix apps/web run build
openspec validate close-literature-foundation-operations --strict
```

The final isolated regression suite reached **269 passed**. The production build and browser flow were inspected on the disposable fixture server: source-only and needs-recovery states are visible, retry remains available, selected import shows metadata success alongside per-file failure, and owned files show SHA-256 and an offline open link. The browser file picker could not supply a path during one replacement-upload attempt (`File` became unavailable); the API and upload workflow are covered, so this limitation is retained rather than claimed as a UI pass.

## Data and deployment boundaries

The real acquisition wrote only additive schema/state/copy rows after per-batch backups. It did not delete or mutate Zotero files, source metadata, canonical metadata, Notes, AI, collections, tags, reading state or existing primary selection. `.env` gained only the verified local Zotero data directory; credentials and private reports remain ignored. No API/Vite/Zotero service was restarted. Restart API manually to load final code/config. Do not mark missing source PDFs recovered without a real backup or reviewed replacement upload.
