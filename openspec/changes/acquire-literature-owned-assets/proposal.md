# Proposal

## Why

The real library has 87 PDF descriptors (81 primary, 6 supplementary), but no owned bytes. Fifty-three descriptors lack a cached source version. A primary-only materializer cannot safely migrate every attachment or prove that downloaded bytes match a stable source observation.

## What Changes

- Add per-attachment acquisition with before/after source metadata, optional source MD5 validation and mandatory local SHA-256/PDF verification.
- Support an explicitly selected local Zotero data directory after cloud-file unavailability was observed; verify account/item/parent through a validated read-only snapshot and retain source-channel provenance.
- Retain source descriptors and canonical/research records; record versioned source-to-owned-copy provenance and preserve roles.
- Reuse the same acquisition routine for existing explicit primary materialization.
- Add read-only plans and an explicit backed-up, bounded, resumable apply CLI with per-asset outcomes and replay verification.
- Prefer owned copies in the Reader, including copies of an explicitly selected source attachment, without rewriting existing primary selections.
- Run the real migration after fixture/copied-data acceptance and report unavailable/unassigned exceptions honestly.

## Capabilities

### New Capabilities

- `literature-asset-acquisition`: version-aware owned PDF acquisition, source-copy provenance and recoverable migration.

### Modified Capabilities

None in main specs. Extends the completed Vault and identity foundation Changes; source and canonical identities remain separate.

## Impact

Existing materialization service, Zotero adapter, file-store/repository ports, additive workflow schema, Reader selection and operational CLI/tests. No new dependency, background worker or source mutation.

## Non-goals

No guessed parents for the eight historical orphan descriptors, deletion/GC, remote write-back, automatic scientific identity verification, parsing/chunking/embeddings/RAG/maps, or new storage backend implementation.
