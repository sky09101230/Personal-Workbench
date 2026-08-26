## Why

The News module already defines GitHub as a first-class feed type but has no real source behind its tab. Adding the three official GitHub Trending periods validates that the shared News pipeline can support ranked, non-Topic feed variants without coupling provider-specific behavior to the application layer.

## What Changes

- Add a backend GitHub Trending provider that normalizes the official Daily, Weekly, and Monthly rankings into `FeedItem(type=github_repo)` values.
- Persist repository identity, description, language, stars, forks, stars for the selected period, rank, and period through the existing News SQLite feed while keeping GitHub-only fields in bounded metadata.
- Register the provider at the composition root and expose it through the existing type-scoped refresh and Feed APIs.
- Preserve provider ranking in cached GitHub results and isolate GitHub refresh/cache behavior from Papers/OpenAlex Topic matching and refresh slots.
- Enhance the existing News GitHub tab with a Daily / Weekly / Monthly period switch and repository-specific card metadata without adding a separate page or endpoint.
- Enrich every refreshed GitHub repository row with a concise DeepSeek summary when configured, while deduplicating the same repository across Trending periods and preserving fail-open behavior.
- Add focused provider, service, SQLite, API, and frontend build verification for the new flow and the cross-type isolation rules it exercises.

## Capabilities

### New Capabilities

- `github-trending-source`: Official Daily/Weekly/Monthly Trending retrieval, normalization, period-isolated ranked persistence, type-scoped refresh, failure behavior, and existing GitHub-tab presentation.

### Modified Capabilities

- `deepseek-paper-summaries`: Extend the existing bounded, backend-only DeepSeek enrichment to GitHub repository FeedItems without adding item-type branches to `NewsService`.

## Impact

- Backend: News domain/application ports and orchestration only where generic source/summarizer capabilities are required; a new provider under `news/infrastructure/providers/github/trending/`; generalized DeepSeek Feed summarization; News SQLite implementation; composition-root registration; existing News API behavior.
- Frontend: existing News API types, `NewsPage`, and `FeedCard` GitHub presentation.
- Data: News-owned SQLite rows and refresh state only; Literature tables and existing Papers/OpenAlex cache entries remain untouched.
- External system: anonymous requests to the official `github.com/trending` Daily, Weekly, and Monthly views; no yearly aggregation, OAuth, GitHub Search API, README retrieval, or new background scheduler.
