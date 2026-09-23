# Proposal

## Why

The foundation can own and verify PDFs, but the UI still conflates remote references with owned files and selected Zotero imports do not automatically use acquisition. Failure reports and reviewed conflicts also need a consistent operational view before final acceptance.

## What Changes

- Selective Zotero import attempts acquisition of its eligible PDFs through the shared routine and reports metadata/file outcomes separately.
- Persist current acquisition outcomes bound to exact source descriptors; expose owned, source-only, recovery-needed and absent PDF states without claiming unverified bytes are readable.
- Add per-source acquisition retry and show source-to-owned-copy links/integrity in the existing UI.
- Make identity audit respect conflict decisions while retaining history, and complete backend selection metadata through the existing file-store port.
- Reconcile the saved migration exception report safely, validate real preservation/availability, and finalize only this Goal's OpenSpec artifacts and acceptance matrix.

## Capabilities

### New Capabilities

- `literature-library-readiness`: truthful PDF ownership/availability, automatic selected-import acquisition, recovery outcomes and decision-aware audit.

### Modified Capabilities

None in current main specs. Existing foundation capabilities are still in their completed change directories and will be synchronized when finalized.

## Impact

Literature service/repository/read models, composition, existing import/files UI, audit and validation scripts. Additive workflow schema 6 stores current acquisition state; no scientific metadata or research-state backfill. No new storage service or dependency.

## Non-goals

No invented recovery of missing source files, canonical merges, new scholarly verification provider, chunking/embedding/RAG/maps or automatic production restart. The pending question about backup files remains separate from capability completion.
