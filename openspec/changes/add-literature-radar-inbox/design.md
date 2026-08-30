## Context

The existing News research design separates objective Paper rows from Research Runs and run-specific Recommendations. It already provides transactional `(task_key, run_key)` upsert and latest-per-paper Feed projection. Literature Radar V0.1 emits a richer result contract: profile/search-window context, candidate and verification counts, source degradation, Zotero context summary, five selected recommendations, verified-not-selected alternatives, component scores, evidence depth, and date evidence.

## Goals / Non-Goals

**Goals:** preserve the complete review-relevant Radar result, make manual replay deterministic and idempotent, deduplicate Papers across Radar runs, expose a latest-run reading view, and persist a four-value review state.

**Non-Goals:** run Radar in Workbench, access Zotero from Workbench, modify Zotero, schedule or automate ingest, learn from review state, create tasks, or refactor provider feeds.

## Decisions

### Extend the Phase 1 model instead of adding Radar tables

Run-level first-class counts and frequently displayed metadata receive columns; future-facing or diagnostic structures use JSON columns. Recommendation rows gain selection kind/rank, additional component scores, evidence/date/Zotero JSON, and review state. Verified alternatives are run-paper relationships and therefore use the same recommendation table with `selection_kind = verified_not_selected`.

### Use raw-result identity plus normalized payload digest

The Agent computes `ingest_identity = sha256:<canonical V0.1 result digest>` and a deterministic run key containing profile, generated timestamp, and a digest prefix. Workbench enforces unique non-null ingest identity and stores a server-computed digest of the normalized ingest payload. Exact replay returns the existing run without writes. Reusing the identity with changed normalized content returns a 409 conflict.

### Keep paper identity aligned with Radar while retaining compatibility

Resolution gathers DOI, arXiv id, canonical title, existing OpenAlex id, and the legacy canonical-title-year key. Multiple matches are a conflict. Canonical title is Unicode NFKC/casefold/alphanumeric normalization. An arXiv repository DOI may be upgraded to a formal DOI for the same resolved paper; conflicting formal DOIs remain errors.

### Add a run-oriented query rather than overloading Feed

`GET /api/news/papers/research/radar/latest` returns one latest Literature Radar run with run metadata, five recommended items, and verified alternatives. The legacy research Feed endpoint remains available for Phase 1 compatibility. The Papers UI no longer merges Research cards into ordinary OpenAlex results; it offers a local Feed/Radar switch.

### Store review state on the run-paper recommendation

Review is specific to what the user saw in one Radar run, so it belongs on `news_paper_research_recommendations`. `PATCH /api/news/papers/research/recommendations/{id}/review` accepts only `new`, `seen`, `interested`, or `dismissed`. It never writes Zotero or changes ranking.

## Migration

News schema v4 creates the current table definitions for new databases and conditionally adds missing columns for existing v3 databases in one transaction. Existing recommendations default to `recommended` and `new`; existing runs default to `paper_research`. Existing paper titles are backfilled into the new canonical-title column before indexes are created.

## Risks / Mitigations

- **Large diagnostics payloads:** bounded request arrays/strings and JSON columns avoid table proliferation.
- **Identity spoofing:** unique ingest identity alone is insufficient, so Workbench also compares a server-computed normalized payload digest on replay.
- **Provider feed regression:** the legacy schema v1 endpoint and Feed query remain covered by existing tests; Radar has a separate query/component.
- **Sensitive local context:** Agent maps only an allowlist of Zotero context fields and omits the V0.1 executable path.
