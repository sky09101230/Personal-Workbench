## ADDED Requirements

### Requirement: News exposes a provider-independent feed
The system SHALL represent Papers, GitHub Repositories, GitHub Skills, AI News, and X Posts through one `FeedItem` contract without exposing provider-private response structures.

#### Scenario: Mixed item types are returned
- **WHEN** the user requests the News feed without a type filter
- **THEN** the API SHALL return supported item types through the same stable field structure

#### Scenario: A provider has extra metadata
- **WHEN** a source adapter receives fields that are not part of the stable News contract
- **THEN** the adapter SHALL expose only normalized fields and bounded generic metadata rather than its raw response

### Requirement: News persists metadata and user state separately from Literature
The system SHALL store News Feed metadata, Topic matches, and read/saved/hidden state in News-owned SQLite tables and SHALL NOT read or write Literature tables.

#### Scenario: Feed item is refreshed
- **WHEN** a normalized item is persisted again with the same stable id
- **THEN** its Feed metadata and Topic matches SHALL be updated without deleting its News user state

#### Scenario: Provider supplies article content
- **WHEN** a provider can access full webpage or document content
- **THEN** the News cache SHALL persist metadata only and SHALL NOT store the full content

### Requirement: User can filter the cached feed
The system SHALL expose `GET /api/news/feed` with `type`, `topic`, `limit`, and `offset` filters over the local News cache.

#### Scenario: Type and Topic are selected
- **WHEN** the user requests a supported type and Topic together
- **THEN** the API SHALL return only cached items matching both filters with pagination metadata

#### Scenario: No item matches
- **WHEN** the selected filters match no cached item
- **THEN** the API SHALL return a successful empty page rather than a provider-specific error

### Requirement: Topics use a simple portable configuration
The system SHALL represent each Topic with a name, positive keywords, negative keywords, and enabled sources, and SHALL expose configured Topics through `GET /api/news/topics`.

#### Scenario: Topic matching runs during refresh
- **WHEN** a normalized item contains a positive keyword, no negative keyword, and comes from an enabled source
- **THEN** the resulting Feed item SHALL be associated with that Topic

### Requirement: News is an independent Workbench module
The system SHALL register News beside Literature and provide type tabs, a Topic filter, a unified Feed list, and loading, empty, and error states.

#### Scenario: User opens News
- **WHEN** the user activates the News module
- **THEN** the Workbench SHALL display All, Papers, GitHub, Skills, AI News, and X tabs without requiring five separate pages

#### Scenario: Feed data is unavailable
- **WHEN** the News API is loading, empty, or returns an error
- **THEN** the page SHALL show the corresponding explicit state instead of an unlabelled blank area
