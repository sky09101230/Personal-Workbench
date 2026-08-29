## Context

The News module currently normalizes external providers into `FeedItem` values, refreshes them through `NewsService`, and transactionally reconciles `news_feed_items` in `SQLiteNewsRepository`. OpenAlex Papers and GitHub Trending share that display cache, while the React `/news` page reads `/api/news/feed` and renders `FeedCard` components.

External Codex research differs from a refresh snapshot: a submission has run-level provenance, objective paper identity, and run-specific judgments that must remain historical. Research execution is outside Workbench; this repository owns only the HTTP trust boundary, validation, persistence, querying, projection, and display.

## Goals / Non-Goals

**Goals:**

- Accept only an explicit schema-versioned Research payload through the News router.
- Store Paper, Research Run, and Recommendation separately in News-owned SQLite tables.
- Normalize identifiers, deduplicate papers, and make `(task_key, run_key)` submissions idempotent in a single transaction.
- Query the latest recommendation per paper while retaining older run recommendations.
- Project Research results into the existing `FeedItem` display model and render them in the Papers area with clear AI Research provenance.
- Preserve all existing News, Literature, Todo, and ProjectActivity behavior.

**Non-Goals:**

- Running Codex, calling Zotero, scheduling, polling, feedback, recommendation learning, or saving papers to Literature.
- Replacing `FeedItem`, reworking provider refresh, changing GitHub Trending, or introducing authentication beyond the repository's current pattern.

## Decisions

### Keep research provenance outside the refresh cache

Add `news_papers`, `news_paper_research_runs`, and `news_paper_research_recommendations`. `news_feed_items` remains the provider refresh cache, so an OpenAlex refresh cannot delete Research Runs or Recommendations. The repository projects the latest recommendation into a `FeedItem(source="research")` only when queried.

Alternative considered: persist AI fields in `news_feed_items`. Rejected because refresh reconciliation would erase history and permanently bind a run-specific judgment to a paper display row.

### Put the trust boundary in Pydantic and pass domain values to the service

The router defines nested request models with forbidden extra fields, score bounds, required nonblank text, supported schema version, and a paper-level rule requiring a URL or supported identifier. The client cannot submit internal ids or timestamps. The service receives explicit domain input and the repository binds SQL parameters.

Alternative considered: accept arbitrary JSON and validate in SQLite. Rejected because it weakens error reporting and allows accidental persistence of unreviewed fields.

### Normalize and resolve identity inside one repository transaction

The application normalizes task/run keys and paper identifiers before calling the repository. DOI normalization removes recognized DOI URL/prefix forms, lowercases the value, and validates a `10.<registrant>/<suffix>` shape. arXiv and OpenAlex identifiers receive bounded canonical forms. SQLite has nullable unique indexes for DOI, arXiv id, and OpenAlex id plus a canonical title/year fallback key.

For each input paper, lookup follows DOI, arXiv, OpenAlex, then canonical title/year. Existing rows receive only supplied, non-empty metadata updates; otherwise a server-generated id is inserted. Conflicting identities fail the transaction instead of silently merging two established papers.

Alternative considered: use a single hash of the first available identifier. Rejected because a later payload with a stronger identifier could create a duplicate of a previously title-matched paper.

### Make run replay an upsert, not a new historical event

`(task_key, run_key)` is unique and `(run_id, paper_id)` is unique. A replay updates permitted run metadata, paper metadata, and the existing recommendation for that run; it never creates a second run or recommendation. A different run key creates a new Recommendation for an existing Paper. All writes use one `BEGIN IMMEDIATE` transaction and roll back on any failure.

### Provide a dedicated research query and merge only in the Papers UI

`GET /api/news/papers/research` returns a normal paged Feed projection with Research fields in optional metadata. The existing `/api/news/feed` contract and provider cache remain unchanged. When the Papers tab has no OpenAlex Topic filter, the frontend fetches both feeds, merges and sorts the page, and visually marks research cards. With an OpenAlex Topic selected, it preserves the existing topic-filter semantics and requests only the OpenAlex feed.

Alternative considered: change `/api/news/feed?type=paper` to SQL-union both stores. Rejected for phase one because it couples provider refresh pagination/filtering to provenance storage and enlarges the regression surface.

### Ship a checked real-paper fixture and a repeatable local acceptance test

A five-paper JSON fixture contains verified titles and DOI or canonical URLs. API tests post it twice against a temporary on-disk SQLite database, assert stable counts and query output, then recreate the repository/service against the same file to prove persistence without starting background services.

Manual browser confirmation remains separate because the repository has no frontend test runner and the task forbids leaving API or Vite background processes running.

## Risks / Trade-offs

- [A paper's identifiers conflict with rows already established as different papers] → Reject and roll back the entire ingest; do not guess a merge.
- [Fallback title/year can conflate genuinely distinct works] → Use it only after DOI, arXiv, and OpenAlex lookup; retain all normalized identifiers so stronger future matches win.
- [Two independently paged feeds can produce a page larger than the nominal OpenAlex page size] → Bound both requests to the existing maximum and merge deterministically; defer unified pagination until a requirement needs it.
- [No new endpoint authentication exists] → Reuse the current local API boundary, apply strict validation and parameterized SQL, and avoid claiming internet-safe authentication.
- [Research metadata may be updated on same-run replay] → Treat `(task_key, run_key)` as the event identity; changed content is a correction to that event, while different run keys preserve history.

## Migration Plan

1. Increment the News schema version and create only new `news_*` tables/indexes with idempotent DDL.
2. Deploy backend and restart it so schema initialization occurs on first News repository use.
3. Deploy/restart the frontend after the backend API is available.
4. POST the five-paper fixture twice and verify stable table counts and GET output.

Rollback is code-only: the existing feed tables and APIs are unchanged. The new tables can remain unused without affecting prior behavior; destructive table removal is intentionally excluded.

## Open Questions

None for phase one. Authentication, unified feed pagination, scheduling, Zotero integration, feedback, and research execution belong to later changes.
