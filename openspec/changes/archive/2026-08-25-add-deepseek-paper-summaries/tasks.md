## 1. Contract and configuration

- [x] 1.1 Add backend-only DeepSeek key/base URL/model settings and document them in `.env.example`.
- [x] 1.2 Add the minimal News summarizer port and integrate it after Topic Match without changing Feed/API/SQLite schemas.

## 2. DeepSeek adapter

- [x] 2.1 Implement bounded batch `DeepSeekPaperSummarizer` requests with the configured model, Bearer auth, non-thinking JSON output, and prompt-injection-resistant instructions.
- [x] 2.2 Implement fail-open handling for missing configuration, timeout/network errors, 401/403, 429, other HTTP failures, malformed output, and partial id-matched summaries.

## 3. Composition and FeedCard

- [x] 3.1 Register the DeepSeek summarizer in production composition while keeping tests able to omit or inject it.
- [x] 3.2 Show a low-emphasis AI summary label and line-clamp all FeedCard summaries, including historical/fallback abstracts.

## 4. Verification

- [x] 4.1 Add mocked tests for request mapping, bounded input, summary replacement/metadata, missing key, failure fallback, malformed/partial responses, and Topic Match before summarization.
- [x] 4.2 Run complete backend pytest, frontend production build, strict OpenSpec validation, and `git diff --check`.
- [x] 4.3 After `DEEPSEEK_API_KEY` is configured, run one real refresh smoke test and confirm a Topic-matched paper card contains a concise AI summary without exposing the key.
  - The live Papers UI displayed concise Chinese AI summaries on Topic-matched OpenAlex cards, and no credential appeared in the browser response.

## 5. Matched-paper summary coverage

- [x] 5.1 Summarize every persisted paper with a source abstract after Topic Match; exclude papers with no Topic association.
- [x] 5.2 Process all matched candidates in bounded batches of at most 10 while preserving per-batch fail-open behavior.
- [x] 5.3 Add unmatched-exclusion and multi-batch regression tests and run the focused and full verification stack.
