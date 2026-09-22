# Proposal

## Why

Literature V2 currently merges canonical papers on title/year/shared-author evidence. This can attach Notes, AI history and PDFs to the wrong scholarly identity, so it must be stopped before expanding local storage or metadata ingestion.

## What Changes

- **BREAKING**: new Literature imports no longer automatically associate canonical papers using title, author, year, similarity or AI judgments. Weak matches require review and expose candidate IDs.
- Retain normalization, stable canonical/source/origin replay and compatible DOI/arXiv/OpenAlex matching; reject disagreeing strong evidence transactionally.
- Treat upload checksum replay as an existing import/file association, never as proof that two canonical papers are the same.
- Provide a read-only historical identity audit and copied-real-data acceptance without reassigning canonical IDs or research relationships.

## Capabilities

### New Capabilities

- `literature-identity-evidence`: evidence required for automatic Literature association, review handling of weak matches, file/identity separation and non-destructive historical audit.

### Modified Capabilities

None in main specs. The completed but unarchived V2 Change contains `canonical-literature-library`; this stricter capability supersedes its title-fallback rule for future Literature ingestion. `paper-research-ingest` is News-owned and unchanged.

## Impact

Common canonical repository resolver, domain identity helpers, existing workflow error handling and Literature regression/acceptance tests. Reuse existing transactions and ports. No new external dependency, provider lookup, service restart or live data rewrite. See `docs/literature-foundation-roadmap.md` for the audited baseline and later Changes.

## Non-goals

No automatic historical split/merge, generic merge UI, authoritative DOI correction, new metadata enrichment, asset migration, storage redesign or knowledge-base features. Full review/version lifecycle belongs to the later evidence Change; this Change must at least retain candidates and block unsafe association through existing retry/review paths.
