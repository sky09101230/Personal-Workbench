## Why

Paper Research Phase 1 already provides a durable News-owned boundary for externally produced paper recommendations, but its v1 contract and mixed Papers feed cannot preserve or review the richer Literature Radar V0.1 result. Literature Radar V0.2 needs a controlled manual path from validated result.json into Workbench without moving search, Zotero access, scheduling, or SQLite ownership across module boundaries.

## What Changes

- Extend the existing `/api/news/papers/research/ingest` contract with schema v2 for Literature Radar run metadata, selected recommendations, verified alternatives, diagnostic JSON, richer scores/evidence, and stable ingest identity.
- Reuse `news_papers`, `news_paper_research_runs`, and `news_paper_research_recommendations`; add only compatible columns and indexes through News schema v4.
- Make identical Radar payload replay a zero-write success, reject digest conflicts, and reuse Paper identity by DOI, arXiv, canonical title, then the existing OpenAlex compatibility fallback.
- Add a latest Radar Inbox query and a minimal persistent review status (`new`, `seen`, `interested`, `dismissed`).
- Separate Papers Feed and Radar presentation while leaving provider refresh, GitHub Trending, Literature, Todo, and ProjectActivity behavior unchanged.

## Capabilities

### Modified Capabilities

- `paper-research-ingest`: add Literature Radar schema v2 ingest, latest-run projection, verified alternatives, source diagnostics, and review state while preserving schema v1.

## Impact

- Backend: News research domain/application/router and the existing SQLite repository only.
- Frontend: existing News/Papers page, a Radar Inbox component, News API/types, and scoped News CSS.
- Data: News schema version 4 adds columns and indexes to the three existing Research tables; no parallel Radar tables.
- Boundaries: Workbench remains storage/UI/review only; no search, Codex execution, Zotero calls or writes, scheduler, daemon, or automation.
