## ADDED Requirements

### Requirement: Literature module preserves a provider-neutral boundary
The system SHALL expose Literature as a Workbench module whose public API and UI use `Paper`, `Collection`, `Attachment`, `Note`, and opaque workbench identifiers rather than Zotero-specific models or routes.

#### Scenario: Workbench loads Literature
- **WHEN** a user opens the Literature module
- **THEN** the frontend SHALL call only `/api/literature/*` endpoints and SHALL NOT receive a Zotero API key

#### Scenario: A future provider is introduced
- **WHEN** an additional Literature provider is added
- **THEN** the existing Literature UI and domain models SHALL not require Provider-specific field names

### Requirement: User can browse cached collections and papers
The system SHALL present Literature as a three-column view with Collections and basic filters on the left, a paginated paper list in the center, and the selected paper's metadata and actions on the right.

#### Scenario: Collection selection filters the library
- **WHEN** a user selects a Collection
- **THEN** the paper list SHALL show only papers in that Collection and retain the selected Collection state

#### Scenario: Empty library is displayed
- **WHEN** no paper metadata is available locally
- **THEN** the module SHALL display an empty state with a manual sync action instead of an empty unlabelled list

### Requirement: User can search and inspect literature metadata
The system SHALL allow a user to search cached paper metadata and inspect title, authors, abstract, year, venue, DOI, tags, and available actions for a selected paper.

#### Scenario: Metadata search returns matching papers
- **WHEN** a user enters a query
- **THEN** the paper list SHALL return matching cached metadata without sending the browser directly to Zotero

#### Scenario: Paper detail is selected
- **WHEN** a user selects a paper from the list
- **THEN** the details panel SHALL show the paper metadata and actions for Notes, PDF reading, and PDF download when available

### Requirement: User can view item notes
The system SHALL expose notes associated with a selected paper through the Literature API and display them in the paper detail or Reader context.

#### Scenario: Paper has notes
- **WHEN** a selected paper has synced notes
- **THEN** the system SHALL display the notes without treating them as standalone papers

#### Scenario: Paper has no notes
- **WHEN** a selected paper has no notes
- **THEN** the system SHALL present an explicit empty Notes state
