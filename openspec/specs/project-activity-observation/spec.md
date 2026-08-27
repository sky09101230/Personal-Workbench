# Project Activity Observation Specification

## Purpose

Define the independent backend observation layer for device, project-source, compute-run, and activity-event facts linked to Todo Projects only by opaque `project_id` values.

## Requirements

### Requirement: ProjectActivity remains an independent bounded context
The system SHALL implement ProjectActivity as an independent backend module that treats `project_id` as an opaque external string and MUST NOT import another feature module or read, join, reference, or foreign-key another module's SQLite tables.

#### Scenario: Store an opaque project reference
- **WHEN** a caller observes a source or records an event with an arbitrary non-empty `project_id`
- **THEN** ProjectActivity stores the value without parsing it or querying Todo

#### Scenario: Own only activity tables
- **WHEN** the ProjectActivity schema and source imports are inspected
- **THEN** all owned tables use the `activity_` prefix and no dependency on Todo, News, or Literature exists

### Requirement: Devices are registered and refreshed by heartbeat
The system SHALL upsert a device by its stable caller-supplied ID, update its `last_seen_at` and optional `agent_version` on later heartbeats, and return devices without creating duplicates.

#### Scenario: First device heartbeat
- **WHEN** a previously unknown device sends a heartbeat
- **THEN** one device record is created with its name, observed time, and optional agent version

#### Scenario: Repeated device heartbeat
- **WHEN** the same device sends another heartbeat
- **THEN** the existing record is updated and the device count does not increase

### Requirement: Project sources have stable external identity
The system SHALL upsert project sources using a stable identity derived from `source_key` and optional `device_id`, preserve the internal source ID across repeat observations, and allow a project and device to participate in multiple sources.

#### Scenario: Repeat source observation
- **WHEN** the same device and source key are observed again with updated attributes
- **THEN** the existing source is updated instead of duplicated

#### Scenario: Same source key on different devices
- **WHEN** two devices observe sources with the same source key
- **THEN** each device has an independent project-source record

#### Scenario: Query sources for a project
- **WHEN** a caller requests sources for an opaque project ID
- **THEN** all and only source records carrying that exact project ID are returned

### Requirement: Run observations maintain current compute state
The system SHALL upsert `ActivityRun` observations by `(project_source_id, run_id)`, retain typed lifecycle fields and checkpoint state, and round-trip optional metrics, summary, and configuration dictionaries through persistence.

#### Scenario: Update a run observation
- **WHEN** a known source and run ID are observed again with a changed status and metrics
- **THEN** the existing run reflects the latest observation without adding a duplicate

#### Scenario: Reuse a run ID under another source
- **WHEN** two project sources each observe the same external run ID
- **THEN** both run observations coexist independently

#### Scenario: Query runs for a project
- **WHEN** a caller requests runs for a project
- **THEN** the system returns runs belonging to sources that carry that project ID without reading another module's project table

### Requirement: Activity events are explicit append-only facts
The system SHALL append an `ActivityEvent` only when explicitly requested, preserve open `activity_kind` and `event_type` strings, support nullable subject and source fields, and round-trip optional payload dictionaries.

#### Scenario: Record events across known activity kinds
- **WHEN** callers record development, experiment, knowledge, literature, and system events
- **THEN** each event is appended with its supplied classification, time, subject, and payload

#### Scenario: Record an event without a subject or source
- **WHEN** a system event has no specific subject or source
- **THEN** the event is accepted with nullable correlation fields

#### Scenario: Run observation does not synthesize history
- **WHEN** a run observation changes status or metrics
- **THEN** no activity event is created unless the caller separately records one

### Requirement: Recent activity queries are minimal and deterministic
The system SHALL list events for a project in descending `occurred_at` order, optionally filter by exact `activity_kind`, optionally scope repository queries by source, and enforce a bounded positive result limit.

#### Scenario: Filter recent events by kind and limit
- **WHEN** a caller requests project events with an activity-kind filter and limit
- **THEN** at most that many matching events are returned newest first

#### Scenario: Query events for a source
- **WHEN** the repository is asked for events belonging to a source
- **THEN** only events with that exact source ID are returned newest first

### Requirement: ProjectActivity exposes minimal ingest and query APIs
The system SHALL expose device heartbeat, source observation, run observation, and event recording through POST endpoints and project sources, runs, and events through GET endpoints under `/api/project-activity`.

#### Scenario: Ingest observations through the API
- **WHEN** valid JSON is posted to `/devices/heartbeat`, `/sources/observe`, `/runs/observe`, or `/events`
- **THEN** the corresponding application use case runs and a JSON representation of the resulting domain object is returned

#### Scenario: Query a project's activity through the API
- **WHEN** a caller gets `/projects/{project_id}/sources`, `/projects/{project_id}/runs`, or `/projects/{project_id}/events`
- **THEN** the API returns an `items` collection for that opaque project ID and supports `activity_kind` and `limit` on events

#### Scenario: Stable API error mapping
- **WHEN** an ingest request is invalid, conflicts with stable identity, or references a missing ProjectActivity-owned source or device
- **THEN** the API returns a stable 4xx error response rather than exposing a SQLite exception

### Requirement: The application composes ProjectActivity centrally
The system SHALL create the ProjectActivity repository and service in `app/main.py`, store the service on `app.state.project_activity_service`, and resolve it from request state in presentation code.

#### Scenario: Application startup exposes routes
- **WHEN** the FastAPI application is imported after schema initialization
- **THEN** the ProjectActivity routes use the centrally composed service and presentation code constructs no infrastructure implementation
