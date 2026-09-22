# Literature V2 Stage 3 acceptance

Branch: `gemini/literature-v2-frontend`, based on `claude/literature-v2-backend-workflows` (`f2b5e9c`). Backend code and frozen API contract are unchanged.

## Validation

- `npm.cmd --prefix apps/web run build`: TypeScript and production build pass.
- Workflow/canonical/AI regression selection: 33 passed, one existing Starlette TestClient deprecation warning.
- `openspec validate upgrade-literature-canonical-library-v2 --strict`: pass.
- `git diff --check`: pass.

## Browser acceptance (2026-09-22)

Real local Library read: 69 papers, native collection filters, canonical detail; no real-library mutations. Mutation checks use the production API and built frontend through `apps/web/scripts/literature-acceptance-server.py`, with a disposable SQLite database and fixture Zotero/AI providers.

- Multi-file chooser uploads three PDFs; extracted evidence remains separate from reviewed candidates. Single-file cancellation, missing-title partial confirmation, metadata correction, retry with already-confirmed sibling, final confirmation, whole-batch cancellation and reload/resume pass.
- Zotero collection selection and single checked-item import pass; unselected item remains available. Materialization returns `materialized`, Files distinguishes local asset from source reference, Reader opens the local PDF, imported source note is visible.
- Metadata accept, reject, create correction, edit & accept pass. Accepted metadata updates the canonical paper; older pending snapshots become visibly stale with acceptance disabled. Backend conflict/concurrent-decision cases are covered by the regression tests.
- Native collection creation/membership, reading-state change and empty search pass.
- Sources and Origins are independent sections. Radar origin exposes recommendation reason, summary, rank and run evidence.
- Radar review to Interested, Save to Library, reload saved-state lookup and Saved link to canonical detail pass.
- Canonical manual note, AI overview/chat, Add to Notes and Reader source notes pass with fixture AI responses. No paid/live AI generation was performed.
- Desktop (1440 × 1000) and narrow (390 × 844) Library/detail/import checks pass; no horizontal overflow. Reader returns to the canonical detail. A render-cancellation promise timing issue found during resize/navigation was corrected by observing render and text promises together.
- Final Reader resize, zoom, fit and navigation regression: no warning/error console entries. Workflow browser runs also had no unexpected console errors.

External Zotero network import/AI generation were not exercised against the user's live accounts. The harness is an explicit local verification tool, not an application feature or backend contract extension.
