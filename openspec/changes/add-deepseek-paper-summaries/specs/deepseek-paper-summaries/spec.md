## ADDED Requirements

### Requirement: Relevant papers receive concise DeepSeek summaries
The system SHALL use the configured backend DeepSeek Chat Completions API to replace the summary of Topic-matched paper FeedItems with a faithful, concise Simplified Chinese summary before SQLite persistence.

#### Scenario: Relevant paper has an abstract
- **WHEN** a refreshed paper matches at least one News Topic, has a source summary, and DeepSeek is configured
- **THEN** the system SHALL include its bounded id, title, and abstract in one batch summarization request and persist a 2–3 sentence Chinese summary for the same FeedItem id

#### Scenario: Candidate does not match a Topic
- **WHEN** a fetched paper has no final Topic match
- **THEN** the system SHALL NOT send that paper to DeepSeek and SHALL preserve the Provider-normalized item

#### Scenario: Topic matching uses source content
- **WHEN** a paper is summarized successfully
- **THEN** its Topic associations SHALL have been determined from the Provider-normalized title and abstract before AI replacement

### Requirement: DeepSeek credentials and requests remain backend-only and bounded
The system SHALL read DeepSeek credentials, base URL, and model from backend settings, SHALL never expose the API key to Feed/API/browser data, and SHALL bound prompt input and completion output.

#### Scenario: API key is configured
- **WHEN** `DEEPSEEK_API_KEY` is non-empty
- **THEN** the adapter SHALL authenticate with a Bearer header and use the configured model without placing the key in request content, Feed metadata, or browser responses

#### Scenario: API key is absent
- **WHEN** `DEEPSEEK_API_KEY` is empty
- **THEN** the adapter SHALL make no DeepSeek HTTP request and SHALL return the original FeedItems

#### Scenario: Source abstract contains instructions
- **WHEN** a title or abstract contains instruction-like text
- **THEN** the prompt SHALL treat it only as untrusted source content and SHALL provide no local secrets or unrelated context to the model

### Requirement: AI summarization is fail-open enrichment
The system SHALL preserve the existing News refresh and SQLite feed when DeepSeek times out, rejects authentication, rate-limits, is unavailable, or returns malformed or partial output.

#### Scenario: DeepSeek request fails
- **WHEN** DeepSeek returns 401, 403, 429, another non-success response, or a timeout/network error
- **THEN** refresh SHALL continue with each original Provider summary and SHALL NOT expose the upstream exception to the browser

#### Scenario: Batch response is partial
- **WHEN** DeepSeek returns a valid summary for only some requested FeedItem ids
- **THEN** the system SHALL apply only valid id-matched summaries and SHALL preserve original summaries for all other items

#### Scenario: DeepSeek response is malformed
- **WHEN** the response is invalid JSON or has an unexpected Chat Completions/content shape
- **THEN** refresh SHALL continue with the original FeedItems

### Requirement: FeedCard presents summaries compactly
The system SHALL display successful AI summaries through the existing FeedItem summary field with an AI label and SHALL constrain all summary text to a compact fixed number of visual lines.

#### Scenario: AI summary is available
- **WHEN** a FeedItem has AI-summary metadata and a non-empty summary
- **THEN** FeedCard SHALL show a low-emphasis `AI summary` label and the concise summary without adding a details page

#### Scenario: Original summary is used as fallback
- **WHEN** a cached or refreshed FeedItem contains an original non-AI summary
- **THEN** FeedCard SHALL line-clamp it so the card cannot expand to the full abstract height
