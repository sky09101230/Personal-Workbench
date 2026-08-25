## 1. Provider contract and configuration

- [x] 1.1 Extend `NewsSourcePort.fetch_items` minimally to receive the current Topics, update service/demo callers, and deduplicate validated items by stable id before persistence.
- [x] 1.2 Add optional backend `OPENALEX_API_KEY` settings support and document it in `.env.example` without exposing it to the frontend.

## 2. OpenAlex provider

- [x] 2.1 Implement `OpenAlexPaperProvider` with bounded per-Topic `/works` discovery over the recent 7-day publication window, optional API key, no deep pagination, and negative-keyword prefiltering.
- [x] 2.2 Implement OpenAlex work normalization for identity, title, abstract, authors, publication date, DOI/URL fallback, Topics/keywords, venue, citation count, open access, and work type metadata.
- [x] 2.3 Convert timeout, authentication, throttling, unavailable, and malformed-response failures to stable `NewsSourceError` values.

## 3. Composition and Papers UI

- [x] 3.1 Register OpenAlex as the default production News provider while retaining Demo Provider for tests/development and keeping existing Topics compatible.
- [x] 3.2 Extend the existing paper `FeedCard` to display available venue, DOI, matched Topic, and cited-by count without adding an endpoint or details page.

## 4. Verification

- [x] 4.1 Add mocked provider/service/API tests covering mapping, authors, DOI/link fallback, date, missing abstract, Topic metadata, multi-Topic dedup, recent query filter, 429/401/timeout, and cache preservation.
- [x] 4.2 Run the complete backend pytest command, frontend production build, OpenSpec validation, and `git diff --check`.
- [x] 4.3 Run one real OpenAlex refresh smoke test and verify a returned paper's title, authors, date, and DOI/URL against its OpenAlex record without persisting secrets or starting background services.
  - After configuring the API key and correcting the current sort syntax, the production provider/API pipeline refreshed 20 recent papers successfully.
  - A live sample's title, authors, publication date, DOI, and URL all matched its OpenAlex single-work record.
- [x] 4.4 Correct multi-keyword Topic discovery to use OpenAlex boolean OR syntax, add a mocked regression test, and verify a real D2NN refresh.
  - A real refresh returned fetched=9, stored=9, and topic_matches=3 for the 7-day D2NN Topic.
  - The filtered Feed returned three optical diffractive-network papers and excluded the observed smart-grid false positive.

## 5. Half-day cache and News reconciliation

- [x] 5.1 Persist OpenAlex successful refresh slots as Asia/Shanghai `YYYY-MM-DD-AM/PM`, skip same-slot upstream calls, and leave failed slots retryable.
- [x] 5.2 Reconcile successful refreshes to the current News Topic/Feed snapshot and perform the scoped one-time cleanup of prior Topics and residual Feed.
- [x] 5.3 Add tests for same-slot skip, AM-to-PM, next day, failure retry, successful slot persistence, and News-only cleanup.
- [x] 5.4 Run focused tests, complete backend pytest, frontend build, strict OpenSpec validation when executable, and `git diff --check`.
  - Focused News tests passed: 28 passed.
  - Complete backend tests passed: 66 passed; frontend production build and `git diff --check` passed.
  - Strict OpenSpec CLI validation remains blocked because the sandbox denies `openspec.cmd` and the escalation approval service returns a model-availability 404.

## 6. Optical computing Topic

- [x] 6.1 Add the production `optical-computing` Topic with a precise `optical computing` discovery keyword.
- [x] 6.2 Reuse persisted News Topics to invalidate a same-slot cache when Topic query configuration changes.
- [x] 6.3 Add regression tests for the new Topic and same-slot configuration invalidation, then run the focused and full verification stack.

## 7. Topic-matched Feed union

- [x] 7.1 Filter zero-Topic candidates before AI summarization and SQLite persistence so All topics is the matched union.
- [x] 7.2 Change the `optical-computing` display name to `Optical Computing` without changing its stable id or discovery keyword.
- [x] 7.3 Add regression coverage for unmatched exclusion, AI-call scope, matched counts, and English Topic presentation; run the full verification stack.

## 8. Metasurface Topic

- [x] 8.1 Add the production `metasurface` Topic named `Metasurface` with the precise `metasurface` discovery keyword.
- [x] 8.2 Add regression coverage for the third default Topic, its bounded OpenAlex request, and News cache reconciliation.
- [x] 8.3 Run focused tests, complete backend pytest, frontend production build, and `git diff --check`.

## 9. Type-scoped refresh controls

- [x] 9.1 Remove the cross-type All tab and move a type-specific refresh action into the active tab controls.
- [x] 9.2 Add FeedItem type capabilities to News Providers and scope refresh selection and SQLite reconciliation without deleting other tab caches.
- [x] 9.3 Add service, API, and SQLite regression coverage for type-scoped refresh behavior.
- [x] 9.4 Show and apply the Topic selector only within the Papers tab.
- [x] 9.5 Run focused tests, complete backend pytest, frontend production build, browser verification, and `git diff --check`.
  - Focused News tests passed: 33 passed; complete backend tests passed: 72 passed.
  - Frontend production build and `git diff --check` passed.
  - Automated browser access was denied by auto-review; the user completed visual verification and confirmed the page was correct.
