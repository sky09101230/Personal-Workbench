## ADDED Requirements

### Requirement: News sources implement one application port
The system SHALL define a `NewsSourcePort` whose implementations return normalized `FeedItem` values with stable source-namespaced identifiers.

#### Scenario: A new source is added
- **WHEN** a Papers, GitHub, GitHub Skills, AI News, or X adapter implements the port and is registered at the composition root
- **THEN** the News service, SQLite schema, public API, and Feed page structure SHALL not require source-specific changes

### Requirement: Refresh follows one stable pipeline
The system SHALL process News refreshes through Provider adapter normalization, Topic matching, and transactional Feed persistence.

#### Scenario: Demo provider refresh succeeds
- **WHEN** the user calls `POST /api/news/refresh` with the demo provider registered
- **THEN** normalized demo items SHALL be matched to configured Topics and become available from the cached Feed API

#### Scenario: A provider refresh fails
- **WHEN** any registered provider fails before persistence
- **THEN** the refresh SHALL return a stable News error and SHALL NOT partially replace the cached Feed for that refresh

### Requirement: Advanced ranking remains outside the framework
The system SHALL NOT require AI ranking, LLM summaries, embeddings, RAG, recommendations, or background scheduling to refresh and browse the News feed.

#### Scenario: Framework runs locally
- **WHEN** only the demo provider and SQLite are configured
- **THEN** refresh, Topic matching, filtering, and Feed browsing SHALL work without an AI service or external scheduler
