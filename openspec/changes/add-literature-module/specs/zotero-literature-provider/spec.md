## ADDED Requirements

### Requirement: Zotero credentials remain server-side
The system SHALL load `ZOTERO_USER_ID` and `ZOTERO_API_KEY` from server environment configuration and SHALL use them only in the Zotero Web API adapter.

#### Scenario: Browser requests Literature data
- **WHEN** the frontend requests a Literature endpoint
- **THEN** the response SHALL not contain the Zotero API key or an authenticated Zotero URL

#### Scenario: Credentials are absent
- **WHEN** a Zotero-backed endpoint is requested without valid configuration
- **THEN** the system SHALL return a stable `provider_not_configured` error without attempting an upstream request

### Requirement: Zotero records map to Literature domain models
The Zotero Web API adapter SHALL request Collections and top-level library items using API version 3, map supported metadata to Literature models, and retain provider/library/item identity in `ExternalReference`.

#### Scenario: Collections are retrieved
- **WHEN** the adapter reads Zotero Collections
- **THEN** it SHALL preserve collection name, hierarchy, and an opaque workbench collection identifier

#### Scenario: Top-level item is retrieved
- **WHEN** the adapter receives a Zotero bibliographic item
- **THEN** it SHALL map title, creators, abstract, year, venue, DOI, tags, and external identity into a `Paper`

#### Scenario: Non-paper record is returned
- **WHEN** a Zotero attachment, note, or annotation appears in an item response
- **THEN** the adapter SHALL NOT expose it as a `Paper`

### Requirement: Provider errors have stable workbench responses
The system SHALL translate Zotero authentication, transport, non-success HTTP, and invalid payload errors into stable Literature API error codes without exposing credentials or raw upstream payloads.

#### Scenario: Zotero rejects credentials
- **WHEN** Zotero returns HTTP 401 or 403
- **THEN** the Literature API SHALL return `provider_authentication_failed`

#### Scenario: Zotero is unavailable
- **WHEN** the adapter cannot reach Zotero or receives an unsupported response
- **THEN** the Literature API SHALL return `provider_unavailable`

### Requirement: Literature metadata is synchronized to SQLite
The system SHALL cache Literature metadata in SQLite and support user-initiated full synchronization followed by version-aware incremental synchronization.

#### Scenario: First synchronization
- **WHEN** the user initiates Sync without a local library version
- **THEN** the system SHALL page through the configured Zotero library and persist metadata, external references, and the resulting library version atomically

#### Scenario: Subsequent synchronization
- **WHEN** the user initiates Sync with a stored library version
- **THEN** the system SHALL request only relevant remote changes and update the cache without a full library scan
