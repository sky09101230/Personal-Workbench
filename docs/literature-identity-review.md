# Literature identity and version review

Workbench paper IDs remain the owner of Notes, AI history, reading state, collections and file associations. DOI/arXiv/OpenAlex are accepted scholarly claims, and PDF SHA-256 is only file identity. Neither a conflict decision nor a version relation merges canonical papers.

## Review a paper's identity

Open 元数据 → 文献身份与版本. The panel displays accepted identifiers and a separate identity state:

- `unresolved`: no accepted scholarly identifier; the paper can remain in the Library.
- `needs_review`: identifiers are present but no matching current human confirmation exists.
- `conflict`: canonical claims or recorded source conflicts need attention.
- `published_confirmed`, `preprint_confirmed`, `identifier_confirmed`: a user confirmed the current metadata/identity snapshot with supporting evidence and a rationale. These are explicitly human confirmations, not fabricated registry or scientific verification.

Select supporting source observations, supply a reason (10–4000 characters) and confirm. Evidence must belong to the reviewed paper; pending metadata proposals and applicable open conflicts must be handled first. Confirmation is tied to the displayed snapshot. Later metadata changes or identifier correction require review again.

更正已接受的学术标识 records a complete intended DOI/arXiv/OpenAlex set. Empty fields explicitly withdraw those current claims. The server normalizes the set, checks ownership and rejects a claim owned by another paper. Superseded current claims are released from lookup but remain in before/after evidence, together with prior field choices. Canonical ID, aliases, Notes, AI, collections, reading state and file associations stay in place. Correction is not confirmation and does not silently resolve other conflicts.

## Conflict queue

The Library includes 身份与来源冲突审核, with a paginated history. Public identity-rejected imports now commit an audit record after their canonical transaction rolls back; repeated identical rejection reuses that record. Original evidence is never deleted.

Available decisions require a current snapshot and reason:

- 保留当前身份 (`keep_current`): reject the incoming claim after checking the current canonical claims. Separate metadata proposals still need their own decisions. Exact reviewed source replay does not reintroduce the same conflict flag.
- 保留为不同论文 (`keep_separate`): for title-based weak collisions only, authorize an exact original-input retry to create an independent paper. This supports distinct no-DOI papers with similar bibliographic data. It never bypasses a strong identifier collision and never restores a removed paper. Changed input requires its own review.
- 待恢复来源证据 (`quarantine`): classify unassociated evidence such as an orphan attachment. The descriptor remains; no parent is guessed and no claim of PDF recovery is made.
- 重新审核 (`reopen`): append a new review state while retaining prior decisions. Related canonical records may require identity review again.

An existing canonical conflict marker clears only after applicable conflicts are closed and current claims are consistent. A separate-import decision cannot validate an inconsistent old identifier. If an identifier correction is required, correct it explicitly and then finish the conflict review.

## Preprint and publication relationships

From an independent preprint with an arXiv identifier, select a distinct published paper with a formal DOI. Select evidence on both sides and explain the relationship. Workbench records both current snapshots; both paper IDs and their Notes/files remain independent even if they reference identical PDF bytes.

The relation can be retracted with a reason; its original evidence and all decisions remain available. Active replay is idempotent. If either paper's metadata changes or becomes unavailable, the relation is flagged for review. Reload before another decision; retract/re-link if new evidence warrants it. A preprint that has already been promoted to a publication within the same canonical paper does not need a self-link.

## Radar handoff

Radar Save now associates only the selected recommendation. Other appearances from the same News group are retained under `unverified_related_appearances`, not promoted to canonical origins or automatically marked Saved. The source is explicitly the current discovery metadata snapshot, not an invented immutable historical identity. A later explicitly saved recommendation still uses the common strong resolver. Historical saved origins are retained unchanged.

## API and deployment

All paths are under `/api/literature`:

| Method/path | Purpose |
| --- | --- |
| GET `/papers/{id}/identity` | Current metadata, accepted identifiers, source evidence, conflicts, versions and snapshot token |
| POST `/papers/{id}/identity/confirm` | Snapshot, evidence IDs and reasoned human confirmation |
| POST `/papers/{id}/identity/correct` | Same proof plus complete nullable DOI/arXiv/OpenAlex correction |
| GET `/identity/conflicts?limit=25&offset=0` | Original conflict evidence and decision history |
| POST `/identity/conflicts/{id}/decisions` | Snapshot, decision and rationale |
| POST `/papers/{preprint_id}/versions` | Publication ID, both snapshots, supporting evidence IDs and rationale |
| POST `/versions/{id}/retract` | Current relation snapshot and rationale |

Opaque IDs/tokens must be taken from responses. Stale/ownership conflicts return 409 without partial decisions; invalid proof or fields return 422. File inspection remains available through `/papers/{id}/assets/integrity` and is now displayed in the Files view.

Workflow schema 4 adds `literature_conflict_reviews` and `literature_paper_versions`. Existing canonical startup makes an online backup before additive upgrade; legacy data migration remains separately gated. The existing migration CLI supports `--dry-run`. `manual_identity_review_acceptance.py` rehearses against a real online backup without changing the source or automatically reviewing its orphan records. Restart the API manually to load this implementation; no production service is restarted automatically.
