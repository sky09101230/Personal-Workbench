# Design

## Context

Canonical IDs, unique scholarly identifiers, source aliases and metadata evidence already exist. Identity conflicts are append-only payloads; V2/protected ingestion leaves conflicting source records intact. The injected Radar export contains current grouped News metadata plus recommendation appearances, not immutable per-appearance identity snapshots. Do not infer scientific identity from that grouping.

## Goals / Non-Goals

Make unresolved evidence actionable without moving canonical ownership, and distinguish user-confirmed identities from unreviewed identifiers. Preserve every original conflict and decision. Full merge/split and external verification are excluded; a user assertion is labeled as user confirmation, not registry proof.

## Decisions

- Use an identity repository extending the existing workflow repository and an application Protocol/service, composed in main.py. Add only `literature_conflict_reviews` (append-only decision history) and `literature_paper_versions` (relation plus preserved decision history) in backed-up workflow schema version 4. Reuse metadata evidence for identity confirmation/correction records. No historical data backfill.
- Identity context returns accepted identifier ownership, relevant metadata evidence IDs, conflicts and a digest of current metadata/index/review context. Confirm/correct and relation creation require these exact snapshots. No client-supplied canonical IDs, paths or arbitrary fields may be rewritten.
- Confirmation requires at least one accepted scholarly identifier, user rationale and paper-owned evidence. All current identifiers must belong to the current paper; unresolved applicable conflicts and pending identity proposals block confirmation. Record the full metadata snapshot and evidence IDs. Identity state is `unresolved`, `needs_review`, `conflict`, or user-confirmed published/preprint/identifier; metadata changes invalidate the confirmation snapshot.
- Dedicated identifier correction accepts a complete DOI/arXiv/OpenAlex set, explicit rationale and supporting evidence. It normalizes and checks all owners under the same write transaction, releases only superseded current claims owned by this paper, retains historical observations and writes before/after/field-choice evidence. It never steals an identifier from another canonical document or changes Notes/AI/aliases/collections/assets. Correction itself is not identity confirmation and does not silently close source conflicts.
- Conflict queue joins only Literature aliases, canonical IDs, recorded origins and candidate IDs. Snapshot-checked decisions are `keep_current` (reject the conflicting claim after validating current ownership), `keep_separate` (license exact weak-only input replay as an independent paper), `quarantine` (retain unresolved unassociated evidence; no recovery claim), and `reopen`. Every action requires a reason and appends a review row. Only when all applicable conflicts are closed and current identifiers are consistent can an existing canonical conflict marker clear. Quarantine cannot clear a paper's identity conflict. Separate replay never overrides a strong match/collision and cannot license changed incoming evidence.
- Persist public ingestion/asset/selective-import identity rejections in a separate committed conflict record after the failed canonical transaction rolls back. Staged upload already retains conflict evidence. Durable rejection is intentional: canonical/research rows remain unchanged, while the conflict audit gains evidence. Replay is deterministic.
- Preprint/publication links require two distinct canonical papers, a preprint identifier on the preprint side and formal DOI on the publication side, both current snapshots, evidence for both papers and a rationale. They do not merge or share identifiers. Retraction keeps the relation and original decision history; active replay is idempotent. No automatic title-based linking.
- Radar Save uses only the selected recommendation's origin. Store the exported grouped appearances as `unverified_related_appearances` in that origin's evidence, clearly marking metadata as the current discovery snapshot. No other recommendation is marked saved. Existing origins remain historical; later saves use the shared strong resolver.
- Integrate an identity panel and global conflict queue into the existing Literature views. Display current owned/remote/missing/corrupt asset inspection from the Vault endpoint. Do not build a separate workflow platform.

## Risks / Trade-offs

- User confirmation can still be mistaken → require rationale/evidence, retain snapshots and use explicit human-review labels, never fabricated external verification.
- Historical orphan attachments cannot be assigned scientifically → expose quarantine and evidence; do not guess a parent or delete their payload.
- Stricter accepted-ID correction can block duplicate historical documents → retain both and report the owner; no merge engine is included.
- Public failed imports now add audit rows → preservation assertions must distinguish intended audit writes from forbidden canonical/research mutations.

## Migration Plan

Version-4 DDL and ledger writes use the existing online-backup/transaction mechanism; dry-run is on a copy. Test original rows and IDs, concurrent/stale decisions, owner collision, reversible relationships and replay. Audit the actual eight historical orphan records on a copy; do not automatically review them. Run backend/build/browser acceptance and strict OpenSpec validation, commit, then begin remote asset acquisition. Pytest and browser fixtures remain fully isolated. No production service restart.
