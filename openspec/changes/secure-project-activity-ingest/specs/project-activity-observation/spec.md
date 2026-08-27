## MODIFIED Requirements

### Requirement: ProjectActivity exposes minimal ingest and query APIs
The system SHALL expose device heartbeat, source observation, run observation, and event recording through POST endpoints and project sources, runs, and events through GET endpoints under `/api/project-activity`. The four ingest POST endpoints SHALL require `Authorization: Bearer <token>` validated against the configured `WORKBENCH_AGENT_TOKEN`; the GET query endpoints remain public.

#### Scenario: Authenticated ingest observations through the API
- **WHEN** valid JSON is posted with the correct bearer token to `/devices/heartbeat`, `/sources/observe`, `/runs/observe`, or `/events`
- **THEN** the corresponding application use case runs and a JSON representation of the resulting domain object is returned

#### Scenario: Unauthenticated ingest is rejected
- **WHEN** an ingest POST is missing credentials, has a non-Bearer header, or has an incorrect bearer token
- **THEN** the API returns HTTP 401 with `WWW-Authenticate: Bearer` and does not invoke the application use case

#### Scenario: Query a project's activity through the API
- **WHEN** a caller gets `/projects/{project_id}/sources`, `/projects/{project_id}/runs`, or `/projects/{project_id}/events` without credentials
- **THEN** the API returns an `items` collection for that opaque project ID and supports `activity_kind` and `limit` on events

#### Scenario: Stable API error mapping
- **WHEN** an ingest request is invalid, conflicts with stable identity, or references a missing ProjectActivity-owned source or device after authentication succeeds
- **THEN** the API returns a stable 4xx error response rather than exposing a SQLite exception
