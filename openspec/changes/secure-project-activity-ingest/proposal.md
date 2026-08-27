## Why

ProjectActivity ingest endpoints currently accept observations without authenticating the independent Agent client, allowing unauthorised writes. The existing read-only health and project query APIs must remain publicly usable while writes fail closed when no server token is configured.

## What Changes

- Add a `WORKBENCH_AGENT_TOKEN`-backed setting for the Agent bearer token.
- Require `Authorization: Bearer <token>` on the four ProjectActivity ingest POST endpoints.
- Return `401` with `WWW-Authenticate: Bearer` for missing, malformed, or incorrect credentials; return `503` when the server token is unset.
- Compare tokens with `secrets.compare_digest` and never expose credentials in logs, errors, or responses.
- Keep health and ProjectActivity query GET endpoints public and leave domain, service semantics, repository, SQLite schema, and frontend unchanged.
- Add endpoint tests covering authentication success/failure, fail-closed configuration, public reads, and protection against invoking business writes on failed authentication.

## Capabilities

### New Capabilities
- `project-activity-ingest-auth`: Bearer-token authentication and fail-closed configuration for ProjectActivity Agent ingest HTTP endpoints.

### Modified Capabilities
- `project-activity-observation`: Ingest endpoint requirements now include authentication while public query behavior remains unchanged.

## Impact

Changes are limited to `apps/api/app/core/config.py`, ProjectActivity presentation ingress code, `.env.example`, the related API tests, and this OpenSpec change. No database migration, domain/service/repository, frontend, or external dependency changes are required.
