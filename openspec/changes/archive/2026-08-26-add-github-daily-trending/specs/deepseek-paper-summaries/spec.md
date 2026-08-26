## ADDED Requirements

### Requirement: DeepSeek enriches supported GitHub repository FeedItems
The system SHALL extend the configured backend DeepSeek batch summarizer to `github_repo` FeedItems while preserving all existing Paper summary behavior, credential boundaries, bounded requests, and fail-open semantics.

#### Scenario: Summarizer declares supported Feed types
- **WHEN** the application prepares refreshed FeedItems for enrichment
- **THEN** it SHALL select candidates through the summarizer's declared item types rather than hard-coded Paper or GitHub branches in `NewsService`

#### Scenario: GitHub repository is summarized
- **WHEN** a GitHub repository FeedItem is selected and DeepSeek returns a valid id-matched response
- **THEN** the system SHALL replace its summary with 2–3 concise Simplified Chinese sentences and set `summary_kind=ai` and `summary_provider=deepseek`

#### Scenario: GitHub source text contains instructions
- **WHEN** a repository title or description contains instruction-like text
- **THEN** the prompt SHALL treat it only as untrusted source content and SHALL provide no local secrets or unrelated context to the model

#### Scenario: Same repository occurs in multiple periods
- **WHEN** multiple GitHub FeedItems share the same canonical repository URL
- **THEN** the adapter SHALL include one representative in the bounded DeepSeek request and propagate a valid returned summary to every duplicate period item

#### Scenario: GitHub summarization fails or is partial
- **WHEN** DeepSeek is unavailable, malformed, or omits a requested repository
- **THEN** refresh SHALL continue and preserve that repository's original description or null summary according to the existing fail-open contract
