## Context

Personal Workbench currently separates Literature, News, and Todo into independent backend modules sharing one SQLite database while owning disjoint table prefixes. Todo owns planned work (`Project`, `Task`, Next Action, Today, and Planner), but it must not acquire infrastructure concerns for observing devices, repositories, or compute experiments. ProjectActivity therefore needs its own domain, application, infrastructure, and presentation layers and may correlate observations to an existing project only through an opaque string supplied by callers.

The first delivery is a backend foundation. External agents and scanners will call explicit ingest endpoints later; this change neither discovers activity nor derives historical events from run-state changes.

## Goals / Non-Goals

**Goals:**

- Persist devices, stable project sources, current compute-run observations, and append-only activity events in independently migrated `activity_*` tables.
- Keep activity and event taxonomies open to future string values while providing stable fields for identity, time, subject, and project/source correlation.
- Expose minimal application use cases and HTTP ingest/query contracts with deterministic clock injection and stable application errors.
- Enforce module isolation in code imports and SQLite ownership through tests.

**Non-Goals:**

- Redefining or validating Todo projects, tasks, next actions, Today, or planner state.
- A ProjectActivity frontend or project dashboard.
- Real device agents, Git/filesystem/experiment/Zotero scanners, watchers, scheduling, background polling, WebSockets, AI summaries, or recommendations.
- Automatic event generation by diffing successive run observations.
- Generic CRUD, event sourcing, a closed activity taxonomy, or a source-key URI standard.

## Decisions

### Independent bounded context with an opaque project reference

`project_id: str` is stored verbatim on sources and events. ProjectActivity does not parse, generate, validate against, import from, query, join, or foreign-key to Todo. This preserves module ownership and allows the composition/application layer outside the module to correlate contexts. Importing Todo models or adding a cross-table foreign key was rejected because it makes availability and schema evolution of ProjectActivity depend on Todo.

### Four plain dataclass models with open string classifications

The domain contains `Device`, `ProjectSource`, `ActivityEvent`, and `ActivityRun`. `source_type`, `activity_kind`, `event_type`, and run `status` remain strings without Enum or SQLite CHECK constraints. Known values document interoperability but do not prevent future activity types. Event identity and correlation fields remain first-class columns; only optional ancillary data uses `dict[str, object] | None` payloads.

### One focused repository Protocol and use-case service

`ProjectActivityRepository` exposes typed operations for device/source/run upserts and lookups plus event append/list. `ProjectActivityService` exposes heartbeat, observe, record, and project query use cases. It owns ID creation, input validation, not-found/conflict translation, and an injected UTC clock; the repository owns SQLite representation and constraint/error translation. A generic entity repository or separate repository per table would add abstraction without a second implementation or independent lifecycle.

### Stable caller identities and explicit upserts

Devices are upserted by caller-supplied `id`. Sources are upserted by `(device_id, source_key)`, with SQLite normalizing a missing device through a partial unique index so repeated scans do not duplicate sources. Runs are upserted by `(project_source_id, run_id)`. A source keeps its original internal `id` on repeat observations, while mutable attributes and `last_seen_at` are refreshed. This is the smallest identity scheme that permits the same run ID under different sources and the same source key on different devices.

### Current run state and event history remain separate

`activity_runs` stores the latest observation for each external run. `activity_events` stores explicit append-only facts and has insert-only repository behavior. `observe_run` never calls `append_event`; callers must separately invoke `record_event`. This avoids inventing diff semantics before a real agent synchronization protocol exists.

### Module-owned SQLite schema version 1

`SQLiteProjectActivityRepository.ensure_schema()` manages `activity_schema_migrations` and creates version 1 tables, foreign keys only among `activity_*` tables, JSON text columns, and indexes supporting the required project/source/kind reverse-chronological queries. Connections enable `PRAGMA foreign_keys = ON`. Datetimes are ISO text and JSON conversion occurs only in infrastructure.

### Presentation contracts and composition

Pydantic request/response models live in `project_activity.presentation.router`; response conversion uses domain dataclasses and JSON-compatible datetime serialization. The router resolves the service from `request.app.state.project_activity_service`. `app/main.py` alone constructs the SQLite repository, ensures its schema, creates the service, and registers the `/api/project-activity` prefix.

## Risks / Trade-offs

- [An opaque `project_id` can reference a missing/deleted Todo project] → Preserve bounded-context isolation; callers orchestrating both modules own referential checks and cleanup.
- [Open string classifications permit typos] → Validate only required non-empty strings in the service and document known values; future protocol/version negotiation can add stronger ingestion validation without database lock-in.
- [Nullable `device_id` complicates source uniqueness] → Use two minimal unique indexes: `(device_id, source_key)` when device is present and `source_key` when it is absent.
- [Append-only is an application contract rather than immutable SQLite storage] → Expose no update/delete event operation and cover the repository/API behavior; database triggers are unnecessary for a local single-user first version.
- [Shared database migrations can run during application import] → Follow the repository's existing composition pattern and keep migration idempotent, additive, and isolated to `activity_*` names.

## Migration Plan

1. On application composition, run the idempotent ProjectActivity schema migration after existing module repositories are created.
2. Register the service and router; existing API contracts remain unchanged.
3. Deploy/restart the API manually so the new schema and routes become active.
4. Rollback code by removing the router/service composition. The additive `activity_*` tables can remain without affecting other modules; no destructive down migration is required.

## Open Questions

None for this bounded first version. Agent authentication, ingestion idempotency beyond stable entity identities, source-key conventions, and run-diff event generation belong to later changes.
