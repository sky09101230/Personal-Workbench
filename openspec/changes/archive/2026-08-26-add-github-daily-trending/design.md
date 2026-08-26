## Context

News already has a stable `FeedItem`, a provider port, a type-scoped refresh API, News-owned SQLite tables, and one real Papers source. GitHub Trending adds three ranked snapshots for the same FeedItem type, so repository identity alone cannot distinguish Daily, Weekly, and Monthly cache rows.

The implementation must preserve the dependency direction `presentation -> application -> domain`, with infrastructure implementing application ports. GitHub HTML structure and parsing must remain inside `infrastructure/providers/github/trending/`; the API and UI continue to consume the normalized Feed contract.

## Goals / Non-Goals

**Goals:**

- Fetch the official GitHub Daily, Weekly, and Monthly Trending views and normalize valid repository rows into `FeedItem(type=GITHUB_REPO)`.
- Keep the three cached rankings independently queryable inside the existing GitHub tab.
- Keep GitHub-only values in metadata and preserve the official rank through persistence and pagination.
- Give every GitHub result an AI summary when DeepSeek is configured without repeating the same repository request across periods.
- Make Topic participation a provider capability instead of an item-type conditional in `NewsService`.
- Skip only providers whose own refresh policy says their cache is current, and reconcile only the item types actually refreshed.
- Preserve cached Papers when GitHub refreshes, preserve cached GitHub rows when Papers refreshes, and keep OpenAlex half-day state independent.
- Reuse the existing Feed API, News page, GitHub tab, and Feed card.

**Non-Goals:**

- Yearly Trending, GitHub Search, README retrieval, OAuth, GitHub Skills, background scheduling, or a GitHub-specific API/page.
- A generalized ranking engine or a provider-policy framework beyond the two policies required now: Topic participation and the existing slot-limited source list.
- Mechanical parity between GitHub and OpenAlex internals.

## Decisions

### Parse all three official Trending periods in one infrastructure adapter

`GitHubTrendingProvider` will request `https://github.com/trending?since=daily|weekly|monthly` sequentially with a bounded timeout and a normal HTML `Accept` header. The existing standard-library parser will extract each period independently. One provider call returns the combined normalized snapshots; if any request or parse fails, `NewsService` performs no persistence, preserving all three previous rankings atomically.

The provider will fail with `NewsSourceError` when the request fails, the response is not HTML, or no valid rows can be normalized. This preserves the previous cache rather than replacing it with an empty snapshot after an upstream markup change. Adding BeautifulSoup was considered, but rejected because the bounded structure does not justify a new dependency.

### Represent repository identity through the stable Feed contract

Each item will use source `github_trending`, id `github_trending:<period>:<owner>/<repository>`, type `GITHUB_REPO`, title `<owner>/<repository>`, summary equal to the optional description, and the canonical repository URL. `owner`, `repository`, `language`, `stars`, `forks`, the upstream period-star value, one-based `rank`, and `period` remain in metadata; no GitHub field is added to the domain model.

### Filter normalized period metadata through the existing Feed query

`GET /api/news/feed` and the application/repository ports will accept an optional `period` string. SQLite applies it as an exact filter over normalized `metadata.period`, independent of FeedItem type. `NewsService` only forwards the query dimension and does not branch on GitHub. The API boundary validates the three supported UI values, and the frontend sends the parameter only for the GitHub tab.

Introducing a general facet engine was considered but rejected: one optional exact period filter solves the real pagination requirement without a new abstraction hierarchy.

### Let providers declare Topic participation

`NewsSourcePort` will add a stable boolean `uses_topics`. OpenAlex and the existing demo provider declare `True`; GitHub Trending declares `False`. `NewsService` will calculate Topic associations only for items from providers that opt in and will retain opt-out items with an empty Topic set. This is a source capability, not an `if paper` / `if github` branch, and accommodates future non-Topic sources without a type registry.

A richer provider policy object was considered, but rejected as premature: refresh cadence remains an application composition setting and only one additional policy bit is required for correctness.

### Let the summarizer declare supported FeedItem types

`NewsSummarizerPort` will declare `item_types`. `NewsService` selects items whose normalized type is supported and passes them to the adapter without Paper/GitHub branches. The DeepSeek adapter supports `PAPER` and `GITHUB_REPO`; it keeps Paper abstract eligibility and owns GitHub-specific prompt shaping inside infrastructure.

The adapter will build bounded type-tagged `items` rather than a paper-only prompt. GitHub input uses title, optional description, language, total stars, and forks. Repositories without descriptions remain candidates. Paper inputs without abstracts remain unchanged, preserving the existing Paper contract.

### Deduplicate GitHub summaries by canonical repository URL

Daily, Weekly, and Monthly rows for the same repository need the same repository-level summary. The DeepSeek adapter selects the first URL representative, requests one summary, and propagates it to all matching period IDs. Paper identity remains its stable FeedItem id. This keeps period ranking metadata distinct while avoiding duplicate tokens and cost.

A new summary cache table was considered but rejected: deduplication within one atomic refresh solves the current duplication, while persisted period rows already retain the resulting summary.

### Select due providers independently and reconcile their declared item types

The service will first select providers by the requested Feed type, then remove only slot-limited providers whose current slot and Topic configuration are already persisted. Other selected providers continue refreshing. The repository write scope will be the union of `item_types` declared by providers actually fetched, even for an untyped refresh. If all selected providers are current, the service returns the matching cached count without writing.

This prevents OpenAlex cache state from blocking GitHub and prevents a partial multi-provider refresh from deleting cached types that were not fetched. Provider failure remains fail-before-write for the whole attempted refresh.

### Treat optional numeric metadata rank as a generic cached-feed order hint

For a type-scoped, period-filtered query, SQLite will sort rows with a numeric `metadata.rank` ascending before the existing publication/fetch timestamp and id fallback. The rank stays in metadata and no GitHub-specific column or table is introduced. Existing Papers and an untyped mixed Feed retain their original time ordering.

### Enhance the existing FeedCard only

For `github_repo`, the existing card will display rank plus available language, stars, forks, and period-star values from metadata. `NewsPage` adds a compact Daily/Weekly/Monthly selector, requests `/api/news/feed?type=github_repo&period=<period>`, and continues to refresh through `/api/news/refresh?type=github_repo`. No GitHub-specific endpoint or component tree is added.

## Risks / Trade-offs

- [GitHub changes undocumented Trending HTML] -> Keep parsing selectors localized, validate that at least one complete repository row exists, cover representative HTML fixtures, and preserve the old cache on failure.
- [Anonymous GitHub requests are throttled or blocked] -> Use a bounded request and stable source error; do not add OAuth in V1.
- [SQLite JSON functions vary by runtime] -> Use only the JSON1 functions bundled with supported Python SQLite and cover ordering in repository tests.
- [A future provider mixes Topic and non-Topic types] -> `uses_topics` is provider-scoped; split that source into focused providers or evolve the port only when a real mixed requirement exists.
- [Untyped refresh has multiple due providers and one fails] -> Retain the existing atomic all-or-nothing refresh behavior to avoid a partially advanced snapshot.
- [Three anonymous requests increase latency and throttling exposure] -> Keep requests bounded and sequential, fail before persistence, and defer scheduling/OAuth until required.
- [DeepSeek cost grows with Trending size] -> Deduplicate repositories across periods, retain bounded batches/content/output, and keep enrichment disabled when no backend key is configured.

## Migration Plan

1. Add the provider capability and update all current adapters/test doubles.
2. Correct service due-provider selection and type-scoped reconciliation with regression tests.
3. Add the GitHub Trending adapter, register it beside OpenAlex, and add provider/API tests.
4. Add generic rank-aware SQLite ordering and GitHub card metadata rendering.
5. Run the full backend suite, production frontend build, and strict OpenSpec validation.
6. Extend the provider and existing GitHub tab with Daily/Weekly/Monthly snapshots and period-filtered pagination.
7. Generalize summarizer eligibility and extend DeepSeek enrichment to every GitHub repository result with cross-period deduplication.

Rollback is code-only: remove the GitHub provider registration and revert the generic orchestration/order changes. No schema migration or non-News data change is introduced.

## Open Questions

None for V1. An automated schedule and explicit stale-age display are deferred until a background refresh requirement exists.
