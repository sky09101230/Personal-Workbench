# Todo Today Views Specification

## Purpose

Define the stable Today, Carryover, Active Projects Overview, Upcoming, and Completed queries plus the frontend views that present them without rewriting stored scheduling data.

## Requirements

### Requirement: Today separates carryover and planned work
The system SHALL return unfinished Tasks with `planned_date < today` as Carryover and unfinished Tasks with `planned_date = today` as Planned Today, using the configured local date.

#### Scenario: Yesterday's unfinished task carries over
- **WHEN** an unfinished Task has a `planned_date` before the current local date
- **THEN** the Today query returns it in Carryover and does not change its stored `planned_date`

#### Scenario: Today's planned task is separate
- **WHEN** an unfinished Task has a `planned_date` equal to the current local date
- **THEN** the Today query returns it in Planned Today and not in Carryover

#### Scenario: Finished task is excluded from Today work
- **WHEN** a Task planned on or before today is done or cancelled
- **THEN** the Today query excludes it from Carryover and Planned Today

### Requirement: Active Projects Overview shows actionable state
The system SHALL include every active Project in Today with its unfinished Task count and current unfinished Next Action, including active Projects with zero Tasks.

#### Scenario: Overview across multiple projects
- **WHEN** the user has multiple active Projects with different Task counts and Next Actions
- **THEN** Today returns one ordered overview entry per active Project with the correct count and Next Action

#### Scenario: Paused and archived projects are omitted
- **WHEN** a Project is paused or archived
- **THEN** the Active Projects Overview does not include that Project

### Requirement: Upcoming preserves both scheduling meanings
The system SHALL return unfinished Tasks whose `planned_date` or `due_date` is after today and SHALL preserve both fields separately in every response.

#### Scenario: Future planned or due task appears
- **WHEN** an unfinished Task has a future planned date, a future due date, or both
- **THEN** Upcoming includes it once and returns the two date fields without coalescing them

#### Scenario: Past due alone is not future work
- **WHEN** a Task has no future planned date and its due date is on or before today
- **THEN** Upcoming excludes it

### Requirement: Completed view is explicit
The system SHALL provide a Completed query containing Tasks whose status is `done`, ordered with the most recently completed first.

#### Scenario: Completed list excludes cancelled tasks
- **WHEN** Tasks exist in done and cancelled states
- **THEN** Completed returns the done Tasks and excludes cancelled Tasks

### Requirement: Todo frontend provides the five core views
The Workbench SHALL register a Todo module with Today, Inbox, Projects, Upcoming, and Completed views, plus low-friction Quick Capture available without entering a project form.

#### Scenario: Navigate core Todo views
- **WHEN** the user opens `/todo` and selects each Todo navigation item
- **THEN** the frontend loads the corresponding API data and renders loading, empty, error, and populated states

#### Scenario: Manage project work from Projects
- **WHEN** the user selects a Project
- **THEN** the frontend shows its Next Action, unfinished Tasks, completed Tasks, and an add-Task action
