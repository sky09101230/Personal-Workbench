# Proposal

## Why

Strict ingestion and metadata review now prevent silent merges and overwrites, but unresolved identity records have no durable decision path and preprint relationships are not explicit. Radar also promotes a weak News grouping into multiple canonical origins without individual review.

## What Changes

- Persist rejected ingestion evidence and expose a recoverable conflict queue with reasoned, snapshot-checked decisions.
- Add explicit user identity confirmation and identifier correction, preserving canonical IDs and rejecting ownership theft.
- Link/retract preprint-to-publication relationships without merging papers or moving research data.
- **BREAKING**: Radar Save associates only the explicitly selected recommendation. Other grouped appearances remain unverified discovery evidence, not automatically saved origins.
- Show identity state, evidence, conflict/version decisions and Vault integrity in the existing Literature UI.

## Capabilities

### New Capabilities

- `literature-identity-review`: auditable conflict decisions, user identity confirmation/correction and explicit version relationships.
- `literature-radar-handoff`: recommendation-scoped, strong-identity-safe handoff from discovery to the canonical Library.

### Modified Capabilities

None in main specs. These augment the preceding foundation Changes and supersede V2's automatic all-appearance origin association. News discovery deduplication and external ingest contracts remain unchanged.

## Impact

Literature application ports/services, SQLite workflow upgrade, review APIs/UI and acceptance fixtures. Reuse the injected News export without reading News tables from Literature or changing other modules' storage. No external provider needed for decisions.

## Non-goals

No automatic/manual canonical merge or split, source deletion, identity inference from title/AI/hash, automatic registry verification, remote PDF acquisition or knowledge-base features. Reviewed quarantine is not a claim that unavailable source bytes have been recovered.
