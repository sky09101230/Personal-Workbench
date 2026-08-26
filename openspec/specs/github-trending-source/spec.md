# GitHub Trending Source Specification

## Purpose

Define how official GitHub Trending periods are normalized, refreshed, persisted, and presented through the existing News module while preserving provider and content-type boundaries.

## Requirements

### Requirement: Official GitHub Trending periods are normalized behind the News source port
The system SHALL request the official GitHub Daily, Weekly, and Monthly Trending views and normalize each valid ranked repository into `FeedItem(type=github_repo, source=github_trending)` without exposing HTML or adding GitHub-specific top-level Feed fields.

#### Scenario: Ranked repository is returned for each period
- **WHEN** the official Daily, Weekly, or Monthly Trending view contains a repository with owner, name, description, language, total stars, forks, and stars for that period
- **THEN** the provider SHALL return a period-namespaced FeedItem whose canonical URL targets that repository and whose bounded metadata contains `owner`, `repository`, `language`, `stars`, `forks`, `stars_period`, one-based `rank`, and `period`

#### Scenario: Optional text is absent
- **WHEN** a ranked repository has no description or language
- **THEN** the provider SHALL keep the repository valid with a null summary or language metadata value while preserving its identity, counts, and rank

#### Scenario: Unsupported Trending periods remain excluded
- **WHEN** the provider refreshes in V1
- **THEN** it SHALL request exactly Daily, Weekly, and Monthly and SHALL NOT synthesize yearly Trending or use Search, README, OAuth, or Skills behavior

### Requirement: GitHub Trending refresh is independent of Paper Topics and provider cache slots
The system SHALL retain normalized items from sources that do not participate in Topic matching and SHALL evaluate each selected provider's refresh eligibility independently.

#### Scenario: GitHub item matches no Paper Topic
- **WHEN** GitHub Trending returns a valid repository and configured Topics enable only OpenAlex or contain unrelated paper keywords
- **THEN** the repository SHALL remain in the GitHub Feed with no Topic associations

#### Scenario: OpenAlex already refreshed in the current slot
- **WHEN** an untyped refresh selects both a current slot-limited OpenAlex provider and a due GitHub Trending provider
- **THEN** the service SHALL skip only OpenAlex, refresh GitHub, and preserve the cached Papers Feed

#### Scenario: GitHub tab is refreshed
- **WHEN** the client calls `POST /api/news/refresh?type=github_repo`
- **THEN** the service SHALL call only providers declaring GitHub repository support, refresh all three official periods atomically, and SHALL NOT change the OpenAlex refresh slot

### Requirement: GitHub reconciliation preserves other News types and official rank
The system SHALL transactionally replace only the FeedItem types actually refreshed and SHALL return ranked GitHub repositories in official ascending rank order.

#### Scenario: GitHub snapshots succeed
- **WHEN** Daily, Weekly, and Monthly Trending refreshes return new ranked snapshots
- **THEN** SQLite SHALL replace stale `github_repo` rows with all three period snapshots while preserving Papers and their Topic associations

#### Scenario: Papers snapshot succeeds later
- **WHEN** a subsequent Papers refresh reconciles `paper` items
- **THEN** SQLite SHALL preserve the cached GitHub snapshot and its rank metadata

#### Scenario: Ranked page is read
- **WHEN** the client requests `/api/news/feed?type=github_repo&period=daily`, `weekly`, or `monthly`
- **THEN** only repositories from that period SHALL be returned in ascending numeric rank order with stable pagination

### Requirement: GitHub upstream failures preserve the cached Feed
The system SHALL convert GitHub request, status, content-type, and malformed-markup failures into the existing stable News source error before persistence.

#### Scenario: GitHub is unavailable or throttled
- **WHEN** any official period times out, is unavailable, rate-limits the request, or returns a non-success response
- **THEN** refresh SHALL return `news_source_unavailable` and SHALL NOT modify any cached GitHub period or Papers items

#### Scenario: Trending markup yields no valid repositories
- **WHEN** a successful HTML response cannot produce any valid normalized Trending repository
- **THEN** refresh SHALL fail and preserve the previous GitHub snapshot instead of treating the response as an empty ranking

### Requirement: Existing GitHub tab presents repository-specific metadata
The system SHALL use the existing News GitHub tab and Feed card to switch among Daily, Weekly, and Monthly results without a provider-specific endpoint, page, or Topic selector.

#### Scenario: User opens the GitHub tab
- **WHEN** cached GitHub Trending items are loaded
- **THEN** Daily SHALL be selected by default and each card SHALL show the repository name and available rank, language, total stars, forks, and period-star values and SHALL open the canonical GitHub repository URL

#### Scenario: User changes the Trending period
- **WHEN** the user selects Daily, Weekly, or Monthly in the existing GitHub tab
- **THEN** the client SHALL reset pagination and load the corresponding cached period through the existing Feed endpoint

#### Scenario: GitHub tab refreshes
- **WHEN** the user activates the existing GitHub refresh action
- **THEN** the client SHALL request the type-scoped News refresh and reload the existing Feed list without sending a Paper Topic filter

### Requirement: Every GitHub Trending result participates in AI summary enrichment
The system SHALL submit every normalized GitHub repository to the configured supported News summarizer before SQLite persistence, including repositories without a source description.

#### Scenario: Repository has a description
- **WHEN** DeepSeek is configured and a normalized GitHub repository contains a source description
- **THEN** the persisted FeedItem SHALL contain a faithful concise Chinese AI summary derived from the repository name, description, and bounded normalized repository metadata

#### Scenario: Repository has no description
- **WHEN** DeepSeek is configured and a normalized GitHub repository has no source description
- **THEN** it SHALL still be submitted using its repository name and bounded language/star/fork metadata so a valid response can populate its summary

#### Scenario: Repository appears in multiple periods
- **WHEN** the same canonical repository URL appears in Daily, Weekly, and Monthly snapshots
- **THEN** the summarizer SHALL request one repository-level summary and apply it to every matching period FeedItem
