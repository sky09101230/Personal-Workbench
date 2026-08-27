## 1. Domain and Application Contracts

- [x] 1.1 Create the ProjectActivity package structure and plain dataclass models for Device, ProjectSource, ActivityRun, and ActivityEvent.
- [x] 1.2 Define the typed ProjectActivity repository Protocol and the minimal stable application error hierarchy.
- [x] 1.3 Implement ProjectActivityService heartbeat, source/run observation, explicit event recording, project queries, validation, ID generation, and injected-clock behavior.

## 2. SQLite Persistence

- [x] 2.1 Implement independent schema version 1 migrations for the five `activity_*` tables with module-local foreign keys, stable identity constraints, and required query indexes.
- [x] 2.2 Implement device and project-source upserts/lookups/listing without accessing another module's tables.
- [x] 2.3 Implement run upserts/lookups/project listing with datetime and JSON round trips.
- [x] 2.4 Implement append-only event persistence and reverse-chronological project/source/kind/limit queries with stable error translation.

## 3. HTTP API and Composition

- [x] 3.1 Add Pydantic ingest/query contracts and the seven minimal `/api/project-activity` endpoints with stable application-error mapping.
- [x] 3.2 Compose the repository and service through `app/main.py`, initialize its schema, store it on app state, and register the independent router prefix.

## 4. Verification

- [x] 4.1 Add deterministic service and SQLite tests covering heartbeat/source/run upserts, identity rules, JSON round trips, all known activity kinds, nullable subjects, ordering, filtering, and limits.
- [x] 4.2 Add API tests using `override_service` for all ingest/query endpoints, JSON contracts, filters, limits, and error status codes.
- [x] 4.3 Add a reliable source/import boundary test proving ProjectActivity does not depend on Todo, News, or Literature and does not reference their SQLite tables.
- [x] 4.4 Run strict OpenSpec validation and the complete backend pytest suite, then inspect the final diff for unrelated Todo/frontend changes.
