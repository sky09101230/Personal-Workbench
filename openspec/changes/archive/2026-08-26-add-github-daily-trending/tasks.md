## 1. Provider-independent refresh rules

- [x] 1.1 Add provider-declared Topic participation to the News source port and current provider implementations.
- [x] 1.2 Refactor `NewsService` to skip cached providers independently, retain non-Topic items, and reconcile only actually refreshed FeedItem types.
- [x] 1.3 Add service regressions for non-Topic GitHub retention, OpenAlex-slot independence, type isolation, and failure-before-write behavior.

## 2. GitHub Trending infrastructure

- [x] 2.1 Create `news/infrastructure/providers/github/trending/` and implement bounded official Daily Trending retrieval and normalization.
- [x] 2.2 Add representative HTML parser/provider tests for complete and optional metadata, daily request parameters, stable errors, and malformed-page rejection.
- [x] 2.3 Register GitHub Trending beside OpenAlex at the composition root without adding a presentation dependency on the provider.

## 3. Ranked persistence and API integration

- [x] 3.1 Add generic numeric metadata-rank ordering to the News SQLite feed query while preserving the existing time fallback.
- [x] 3.2 Add SQLite regressions proving GitHub rank order and bidirectional Papers/GitHub refresh isolation.
- [x] 3.3 Add API coverage for type-scoped GitHub refresh and normalized Feed output through the existing endpoints.

## 4. Existing GitHub tab and verification

- [x] 4.1 Enhance the existing `FeedCard` GitHub detail display with rank, language, stars, forks, and period stars without adding a new page.
- [x] 4.2 Review changed dependencies for domain/application/infrastructure/presentation direction and remove any avoidable item-type branching.
- [x] 4.3 Run the full backend tests, production frontend build, strict OpenSpec validation, and diff hygiene checks.

## 5. Daily, Weekly, and Monthly Trending

- [x] 5.1 Fetch and normalize all three official periods with period-namespaced ids, metadata, and atomic failure behavior.
- [x] 5.2 Add optional period filtering through the existing Feed API, application port, and SQLite repository with ranked pagination tests.
- [x] 5.3 Add a Daily / Weekly / Monthly selector to the existing GitHub tab and verify the production frontend build.
- [x] 5.4 Run provider/API regressions, the full backend suite, live three-period smoke verification, strict OpenSpec validation, and diff hygiene checks.

## 6. GitHub AI summaries

- [x] 6.1 Add summarizer-declared FeedItem type support and remove Paper/GitHub candidate branching from `NewsService`.
- [x] 6.2 Generalize the DeepSeek prompt/adapter for Papers and GitHub, including repositories without descriptions and cross-period URL deduplication.
- [x] 6.3 Add service and DeepSeek tests for every GitHub result, summary propagation, bounded input, and fail-open preservation.
- [x] 6.4 Run focused and full backend tests, frontend build, strict OpenSpec validation, architecture review, and diff hygiene checks.
