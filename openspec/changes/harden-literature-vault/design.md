# Design

## Context

The existing `LiteratureFileStore` Protocol separates byte operations from application services. Assets already store `storage_kind`, `storage_key`, checksum and metadata, without absolute filesystem paths. `LocalLiteratureFiles` uses `staging/`, `originals/` and a legacy flat-root read fallback. Keep these contracts and layouts. Real audit currently reports remote descriptors only; do not mistake inventory success for completed Zotero acquisition.

## Goals / Non-Goals

Goals: an independently located, verified local asset store and a safe operational relocation path, preserving canonical and asset identity. Non-goals are listed in proposal.md. In particular, no new backend implementations or destructive asset repair.

## Decisions

- Add optional `LITERATURE_VAULT_ROOT` in Settings and wire it in the composition root. Empty keeps the current DB-adjacent default. Domain/application APIs remain key-based; `storage_kind=local` is the backend discriminator. Unknown storage kinds fail explicitly rather than falling through to Zotero.
- Reuse the file-store Protocol and add an integrity inspection result (asset ID, state, byte size, checksum); it exposes no absolute path. Distinguish verified, missing, corrupt, invalid key/path, unreadable, remote-only and unsupported backend states. A claimed checksum must agree with the content key. Legacy keys themselves supply the checksum when the old payload lacks it.
- Verify the entire file through the same open handle used for delivery before returning even a range. This deliberately costs a sequential read per request in the current small local library. A future verified-stat cache requires explicit invalidation design; no unchecked fast path now. Detect truncation via SHA-256. Inspection never changes metadata or stored bytes.
- Reject symlinks/junction redirection under the configured resolved root and ensure managed paths stay in their intended directories. Stage/finalize/cleanup use the same path guards. Root relocation is explicit configuration, not a file payload path.
- Publish an independently copied, fsynced temporary original with exclusive hard-link publication to the final key, then remove that temporary link. It is independent of the staging inode. Existing target bytes must verify; never replace a corrupt object silently. Failed publication leaves no partial final object; staging remains retryable. NTFS/local filesystem is the supported initial backend.
- Inventory reads raw SQLite `mode=ro` without initializing schema, examining Literature asset records only. Remote descriptors are reported without network calls. CLI defaults to read-only, `--copy-to` plans relocation, and `--apply` copies only verified referenced local objects to the target via the storage adapter. Report per-asset outcomes and verify destination hashes; leave source/DB/config unchanged. Replays reuse verified objects. Refuse relocation while any upload item still requires staging, or if any owned asset fails source integrity. Operators must stop imports/sync before a final relocation and manually switch configuration/restart after verification. No source deletion, automatic recovery or GC.
- Add a paper-scoped integrity endpoint through `LiteratureService` and the existing router. Preserve existing attachment availability fields; richer UI status will be integrated in the evidence Change.

## Risks / Trade-offs

- Hashing every range costs I/O → bounded local PDFs and correctness first; document the cost.
- Out-of-process writers can mutate a file during delivery → Workbench never mutates originals; use one verified handle and detect premature EOF. This is not a filesystem ACL or protection against a hostile local administrator.
- Windows junctions and symlink races → resolve/reject before access; verify content from the returned handle. No claim of race-proof OS-level sandboxing.
- Relocation is not an online multi-writer transaction → operator quiesces writes; pending staging blocks apply; copy is non-destructive and repeatable. Never silently set the new root.
- Existing corrupt local object cannot be automatically rematerialized over the same key → report corruption and retain evidence; separate reviewed repair later.

## Migration Plan

No schema or key migration. Existing deployment keeps its current default root. New storage reads legacy flat objects safely; new writes remain under originals. Inventory before acquisition; test old keys, ranges, missing/corrupt data, duplicate/concurrent publication and source-independent reads. Rehearse copy/verify/replay with real on-disk PDFs and the production Reader API in disposable directories; fingerprint the DB and source. Read-only inventory of the real DB records remaining remote files. Commit after backend regression, strict OpenSpec validation and operator documentation. Never restart API/Vite automatically.
