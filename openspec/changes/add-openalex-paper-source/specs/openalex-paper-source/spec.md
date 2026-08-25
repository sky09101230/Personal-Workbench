## ADDED Requirements

### Requirement: OpenAlex works are normalized to the existing FeedItem contract
The system SHALL map OpenAlex Works API records to `FeedItem(type=paper, source=openalex)` without adding provider-specific top-level FeedItem fields.

#### Scenario: Complete work is mapped
- **WHEN** OpenAlex returns a work with identity, title, abstract index, authorships, publication date, DOI, topics, keywords, venue, citation count, open-access data, and work type
- **THEN** the provider SHALL return one namespaced FeedItem with the core values normalized and the additional values stored in bounded metadata

#### Scenario: Abstract is absent
- **WHEN** a valid OpenAlex work has no abstract inverted index
- **THEN** the normalized FeedItem SHALL use a null summary and remain valid

#### Scenario: Preferred link is unavailable
- **WHEN** a work has no DOI
- **THEN** its FeedItem URL SHALL use the primary landing page when present and otherwise the OpenAlex work page

### Requirement: Refresh performs bounded recent-paper discovery from current Topics
The system SHALL query only the official OpenAlex `/works` API for a fixed recent publication window using the current enabled News Topic keywords, a bounded per-Topic result count, and no deep pagination.

#### Scenario: Enabled Topic is refreshed
- **WHEN** an enabled OpenAlex Topic has positive keywords
- **THEN** the provider SHALL send one Works request combining alternative keywords with boolean OR, plus a from-publication-date boundary for the recent window, newest-first sorting, and a bounded page size

#### Scenario: Negative keyword is present
- **WHEN** a returned work contains a configured negative keyword
- **THEN** it SHALL not be associated with that Topic by the final existing Topic Match

#### Scenario: Topic cannot bound discovery
- **WHEN** a Topic has no positive keywords or does not enable OpenAlex
- **THEN** the provider SHALL not issue an unbounded Works request for that Topic

### Requirement: A work is stored once per refresh
The system SHALL deduplicate OpenAlex results by stable OpenAlex work id before writing the Feed.

#### Scenario: One work matches multiple Topics
- **WHEN** the same OpenAlex work is returned by more than one Topic query
- **THEN** refresh SHALL persist one FeedItem and associate all Topics that pass the existing Topic Match

### Requirement: OpenAlex authentication and failures stay behind the News source boundary
The system SHALL keep the optional OpenAlex API key on the backend, send it whenever configured, and convert upstream failures to the existing stable News source error without exposing raw exceptions.

#### Scenario: API key is configured
- **WHEN** `OPENALEX_API_KEY` is non-empty
- **THEN** every OpenAlex Works request SHALL include it and no Feed/API response SHALL expose it

#### Scenario: API key is absent
- **WHEN** `OPENALEX_API_KEY` is empty
- **THEN** the provider SHALL attempt the supported public basic request without an API key

#### Scenario: OpenAlex rejects or throttles a request
- **WHEN** OpenAlex returns 401, 403, or 429, times out, is unavailable, or returns a malformed response
- **THEN** refresh SHALL return the stable News source error and SHALL NOT modify the previously cached Feed

### Requirement: Existing Papers feed renders normalized OpenAlex metadata
The system SHALL expose OpenAlex papers through the existing News Feed API and existing Papers tab without a provider-specific endpoint or details page.

#### Scenario: User opens a refreshed paper
- **WHEN** a normalized OpenAlex paper is returned from `/api/news/feed?type=paper`
- **THEN** its card SHALL show the title, authors, publication date, matched Topic, and available venue, DOI, and citation count, and SHALL open the normalized original URL
