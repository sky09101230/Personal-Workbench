## ADDED Requirements

### Requirement: Literature Radar schema v2 is accepted through the existing Research boundary
The system SHALL accept a schema v2 Literature Radar payload through `POST /api/news/papers/research/ingest` while continuing to accept the existing schema v1 Paper Research payload.

#### Scenario: Valid Radar result is ingested
- **WHEN** the Agent submits a validator-passed schema v2 payload containing five recommendations and four verified alternatives
- **THEN** Workbench stores one Research Run, nine deduplicated Papers, and nine run-paper Recommendations in the existing News-owned tables

### Requirement: Radar run context and diagnostics are preserved
The system SHALL preserve profile, generated time, search window, candidate/verified/recommended counts, warnings, source status, a safe Zotero context summary, and diagnostic JSON for each Radar run.

#### Scenario: Latest Radar run is queried
- **WHEN** the client calls `GET /api/news/papers/research/radar/latest`
- **THEN** the response exposes the complete run summary, selected recommendations, verified alternatives, source health, warnings, and review-relevant evidence

### Requirement: Radar ingest identity is deterministic and conflict-safe
The system SHALL enforce unique Radar ingest identity, store a server-computed normalized payload digest, return exact replay as a successful zero-write operation, and reject identity reuse with changed content.

#### Scenario: Identical result is uploaded twice
- **WHEN** the Agent uploads the same validated result twice
- **THEN** both requests succeed with the same run id and the second request creates or updates no Paper or Recommendation rows

#### Scenario: Identity is reused with changed content
- **WHEN** a payload changes after an ingest but keeps the same ingest identity
- **THEN** Workbench returns a 409 identity conflict and performs no partial writes

### Requirement: Papers are reused across Radar runs
The system SHALL resolve paper identity by DOI, arXiv id, canonical title, and the existing OpenAlex compatibility fallback so new runs do not inflate objective Paper rows.

#### Scenario: Later run omits identifiers but keeps the canonical title
- **WHEN** a later Radar run contains a previously stored title without DOI or arXiv id
- **THEN** Workbench reuses the existing Paper and creates only a new run-paper Recommendation

### Requirement: Minimal review state is persistent
The system SHALL support `new`, `seen`, `interested`, and `dismissed` on each Research Recommendation and persist the value across service recreation.

#### Scenario: User marks a paper interested
- **WHEN** the UI PATCHes a Radar recommendation to `interested`
- **THEN** the latest Radar query returns `interested` after page reload or backend restart

### Requirement: Papers Feed and Radar Inbox are distinct views
The system SHALL provide a Feed/Radar switch inside Papers. Feed SHALL remain provider-backed; Radar SHALL display the latest Radar run, recommended papers, verified alternatives, source health, warnings, evidence, Zotero relationship, component scores, primary source, and review controls.

#### Scenario: User opens Radar
- **WHEN** the Papers Radar view is selected
- **THEN** no provider refresh or literature search is initiated and the persisted latest Radar run is rendered from the Workbench API

### Requirement: Final source status is distinguished from route diagnostics
The Radar Inbox SHALL display the source-level final status separately from route and environment diagnostics so a failed local CA route does not imply that verified arXiv evidence is untrustworthy.

#### Scenario: certifi route succeeds after default CA diagnostic fails
- **WHEN** an arXiv source record is `success` and includes a failed `default_ca_environment` diagnostic plus successful Atom and official-evidence routes
- **THEN** the card displays `SUCCESS`, while the failed environment diagnostic is available only in expandable route details

#### Scenario: optional source is degraded with fallback coverage
- **WHEN** a source is `degraded` but the run has usable fallback evidence
- **THEN** the card explains that evidence remains available and exposes the detailed warning/routes without labeling the recommended papers as unverified
