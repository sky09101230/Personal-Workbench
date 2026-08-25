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
