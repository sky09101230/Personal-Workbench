# Identity and version acceptance

Date: 2026-09-23. Branch: `codex/literature-foundation`. Previous checkpoint: `546a557`.

## Delivered

Snapshot/evidence/rationale-checked human identity confirmation and explicit identifier correction; append-only conflict decisions with keep-current/separate/quarantine/reopen; recoverable preprint/publication links; durable rejected-intake records; selected-recommendation-only Radar origins; identity/conflict/version controls and Vault inspection in the existing UI. No canonical merge/split or ownership transfer.

Correction preserves canonical IDs and all research relationships. Strong collisions cannot be overridden with a weak separate decision. Exact reviewed weak replay supports independent no-DOI papers, including when an older candidate was removed. Rejected source replay retains its prior decision. Changing either version's metadata flags the existing relation for review; retraction retains its original proof.

## Verification

- Full backend **253 passed**, one existing Starlette/httpx deprecation warning (`.venv/tmp/pytest-identity-review-final`). A parent-process fingerprint comparison verified no real DB change across the isolated complete suite.
- Ten new integration tests cover human confirmation, stale/evidence validation, identifier collision and correction with Notes/files preserved, metadata invalidation, durable exact weak replay, orphan quarantine/reopen, strong-collision protection, version/retraction history with separate Notes and shared-byte assets, Radar grouping isolation, rejected source replay, concurrent correction, stale relation snapshots and removed-record protection.
- Final TypeScript and Vite production build passed. Whitespace and strict OpenSpec validation passed.
- Real-copy acceptance: `PYTHONPATH=apps/api python apps/api/tests/manual_identity_review_acceptance.py`. It compared **56 historical tables**, performed version-4 dry-run and backed-up upgrade/replay only on copies, and found all **8** historical orphan conflicts still unassociated. A copied orphan could be classified and reopened without changing its payload. A copied identity confirmation preserved canonical/Notes/AI/assets/collection/state rows. Source fingerprints stayed identical; integrity `ok`, no foreign-key errors.
- Prior identity acceptance was updated to distinguish intended conflict-audit writes from forbidden canonical writes and passed against the **58-table** upgraded copy. There were 69 canonical papers, zero detected index/owner mismatches and no recorded historical weak aliases. This is structural evidence, not scientific verification.

## Browser acceptance

Ran the built frontend and production API in the isolated fixture server on port 8014. Verified:

- Global weak-match review records 保留为不同论文 and displays the explicit retry instruction.
- Orphan source evidence can be classified then reopened, retaining two review entries and no inferred parent.
- Selecting an arXiv source observation and entering a rationale confirms the preprint with a clearly human-review label.
- Selecting independent preprint/publication observations creates a visible relationship; retraction preserves both snapshots and the original and new rationales.
- Explicit arXiv correction changes the accepted identifier and returns identity to review-needed state while keeping the same canonical page URL and history.
- File view reports verified local bytes, length and SHA-256; layout screenshot inspected.
- Reloading the final build preserves the independent published paper and retracted relation. Browser warning/error log was empty. One automation selector was corrected from label to the visible combobox role; no product failure resulted.

All mutations used disposable DB/Vault data and fixture providers. The tab was closed; the exact known acceptance Python parent/child processes were terminated after Ctrl+C left them alive. No production API/Vite restart, live identity decision or live schema-4 apply occurred.

## Remaining Goal work

The real library still has 105 source attachment descriptors and no acquired local PDF assets at this checkpoint. Next is planned, resumable acquisition of the available 87 PDF descriptors with per-file verification, source/version provenance, backup and preservation checks. The eight orphan descriptors remain explicit unresolved source evidence; this Change did not decide their real meaning or recover their bytes. Final Goal closure must include live owned-asset inventory/offline behavior and an honest exception report, not just these fixture results.

Operator behavior and API details: `docs/literature-identity-review.md`. Existing user `AGENTS.md` edits are excluded from the commit.
