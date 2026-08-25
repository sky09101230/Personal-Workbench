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
The system SHALL deduplicate OpenAlex results by stable OpenAlex work id and persist only works that match at least one configured Topic.

#### Scenario: One work matches multiple Topics
- **WHEN** the same OpenAlex work is returned by more than one Topic query
- **THEN** refresh SHALL persist one FeedItem and associate all Topics that pass the existing Topic Match

#### Scenario: Candidate matches no Topic
- **WHEN** an OpenAlex candidate passes provider validation but has no final Topic association
- **THEN** refresh SHALL exclude it from AI summarization, SQLite persistence, and the All topics Feed

#### Scenario: All topics is requested
- **WHEN** the client requests the Feed without a Topic filter
- **THEN** the system SHALL return the deduplicated union of all Topic-matched FeedItems

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

### Requirement: Each News type tab refreshes only its matching sources
The system SHALL omit the cross-type All tab and scope each tab's refresh action to the tab's FeedItem type.

#### Scenario: Papers tab is refreshed
- **WHEN** the user refreshes the Papers tab
- **THEN** the client SHALL request `POST /api/news/refresh?type=paper` and the service SHALL call only Providers that declare paper support

#### Scenario: One type is reconciled
- **WHEN** a type-scoped refresh succeeds
- **THEN** SQLite SHALL reconcile only that FeedItem type and SHALL preserve cached items and Topic associations belonging to other types

#### Scenario: A tab has no configured Provider
- **WHEN** the selected FeedItem type has no matching configured Provider
- **THEN** refresh SHALL succeed without fetching or deleting its existing cached items

#### Scenario: A non-paper tab is selected
- **WHEN** the user selects GitHub, Skills, AI News, or X
- **THEN** the Topic selector SHALL be hidden and the Feed request SHALL NOT include a paper Topic filter

### Requirement: OpenAlex refresh is cached once per Shanghai half-day slot
The system SHALL persist the last successful OpenAlex refresh slot as `YYYY-MM-DD-AM` or `YYYY-MM-DD-PM` in the `Asia/Shanghai` timezone, without a scheduled reset flag.

#### Scenario: Refresh repeats in the same slot
- **WHEN** OpenAlex has already refreshed successfully in the current Shanghai AM or PM slot and the persisted Topic query configuration is unchanged
- **THEN** refresh SHALL NOT request OpenAlex and SHALL continue serving the existing SQLite Feed

#### Scenario: Topic query configuration changes
- **WHEN** the configured News Topics differ from the configuration persisted by the successful refresh in the current slot
- **THEN** refresh SHALL request OpenAlex again so the new Topic is effective immediately

#### Scenario: Refresh crosses a slot boundary
- **WHEN** the current slot changes from AM to PM or to the next day's AM
- **THEN** refresh SHALL request OpenAlex again and record the new slot only after the complete refresh transaction succeeds

#### Scenario: Refresh fails
- **WHEN** OpenAlex or downstream refresh processing fails
- **THEN** the current slot SHALL remain unrecorded and a retry in that same slot SHALL still be allowed

### Requirement: Successful refresh removes stale News-only data
The system SHALL reconcile the persisted News Topics and Feed to the current refresh snapshot without modifying non-News tables in the shared SQLite database.

#### Scenario: Old Topics and Feed rows exist
- **WHEN** a successful refresh persists the configured `Diffractive Neural Networks`, `Optical Computing`, and `Metasurface` Topics and their current matched items
- **THEN** old News Topics and Feed rows absent from that snapshot SHALL be removed while shared Literature data remains unchanged
