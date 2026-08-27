## Why

Todo records intended work, but the workbench has no bounded context for recording what actually happened in external repositories, devices, and compute workspaces. A separate observation layer is needed so real activity can be ingested and queried without giving Todo ownership of external state or coupling modules through code or database tables.

## What Changes

- Add a backend-only ProjectActivity module with domain models for devices, project sources, append-only activity events, and current run observations.
- Add use-case-oriented service and repository contracts for device heartbeat, source observation, run observation, explicit event recording, and project-scoped queries.
- Add an independently versioned SQLite schema owning only `activity_*` tables, with stable upsert identities, JSON round trips, foreign keys inside the module, and minimal query indexes.
- Add ingest and query endpoints under `/api/project-activity`, composed through `app.state.project_activity_service`.
- Add service, SQLite, API, and module-boundary tests. No frontend, scanner, agent, scheduler, or automatic run-to-event diffing is included.

## Capabilities

### New Capabilities

- `project-activity-observation`: Ingest and query device, project-source, compute-run, and activity-event observations through an independent backend bounded context linked to Todo projects only by opaque `project_id` values.

### Modified Capabilities

None.

## Impact

- Adds `apps/api/app/modules/project_activity/` and dedicated backend tests.
- Updates `apps/api/app/main.py` to instantiate the SQLite repository and service and register `/api/project-activity` routes.
- Adds `activity_schema_migrations`, `activity_devices`, `activity_project_sources`, `activity_runs`, and `activity_events` to the shared SQLite database without reading, joining, or referencing tables owned by another module.
- Adds no external dependencies and does not change Todo, Literature, News, or frontend contracts.
