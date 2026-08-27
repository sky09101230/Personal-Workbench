## ADDED Requirements

### Requirement: Agent ingest requires configured bearer authentication
The system SHALL require `Authorization: Bearer <token>` on `POST /api/project-activity/devices/heartbeat`, `/sources/observe`, `/runs/observe`, and `/events`. When `WORKBENCH_AGENT_TOKEN` is unset or empty, each protected endpoint MUST return HTTP 503 without invoking its business operation.

#### Scenario: Correct token permits ingest
- **WHEN** a protected ingest request includes a bearer token equal to the configured server token
- **THEN** the corresponding ProjectActivity operation executes normally

#### Scenario: Missing or malformed credentials are rejected
- **WHEN** a protected ingest request omits `Authorization` or uses a non-Bearer authorization value
- **THEN** the API returns HTTP 401 with `WWW-Authenticate: Bearer` and does not invoke the business operation

#### Scenario: Incorrect token is rejected without disclosure
- **WHEN** a protected ingest request includes a Bearer token different from the configured token
- **THEN** the API returns HTTP 401 with `WWW-Authenticate: Bearer`, and neither the token nor credential details appear in logs, errors, or response data

#### Scenario: Server token is not configured
- **WHEN** a protected ingest request arrives while `WORKBENCH_AGENT_TOKEN` is empty
- **THEN** the API returns HTTP 503 without invoking the business operation

### Requirement: Public endpoints remain unauthenticated
The system SHALL keep `GET /api/health`, `/api/project-activity/projects/{project_id}/sources`, `/runs`, and `/events` accessible without an Authorization header and preserve their existing responses.

#### Scenario: Public health check
- **WHEN** a caller requests `/api/health` without credentials
- **THEN** the API returns HTTP 200

#### Scenario: Public project queries
- **WHEN** a caller requests any ProjectActivity project query GET endpoint without credentials
- **THEN** the API executes the existing query behavior without requiring a token
