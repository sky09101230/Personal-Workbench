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

### Requirement: Deferred work can be pulled into Today with one action
The Todo frontend SHALL offer a per-row action on Carryover and Upcoming Task rows that sets `planned_date` to the current local date, and SHALL offer a Carryover-level action that reschedules all displayed Carryover Tasks to today in one step. The Today query itself remains read-only; rescheduling is performed only through explicit Task updates.

#### Scenario: Pull a single deferred task into today
- **WHEN** the user activates the quick reschedule action on one Carryover or Upcoming row
- **THEN** that Task's `planned_date` becomes the current local date and the view reflects the change without any other Task being modified

#### Scenario: Bring all carryover forward
- **WHEN** the user triggers the Carryover bulk action
- **THEN** every displayed unfinished Carryover Task is rescheduled to today, each via its own explicit update, and per-task failures do not undo the tasks that already succeeded

#### Scenario: Carryover query stays read-only
- **WHEN** the user opens the Today view without triggering any reschedule action
- **THEN** past-planned Tasks are reported as Carryover with their stored `planned_date` unchanged

### Requirement: Optimistic task updates keep the workspace responsive
The Todo frontend SHALL reflect Task and Project mutations in the current view immediately, SHALL restore the prior value and surface an error next to existing content when the underlying request fails, SHALL disable only the control performing the mutation while its request is in flight rather than locking the whole page, and SHALL complete silent background reconciliation without clearing editing state.

#### Scenario: Work continues during in-flight requests
- **WHEN** the user completes a second Task while the first completion request is still pending
- **THEN** the interface updates immediately for both Tasks without queuing behind or being blocked by the first request

#### Scenario: Failure feedback keeps context
- **WHEN** a Task update request fails
- **THEN** the affected value reverts to its prior state, an error message appears alongside the current list content, and the rest of the workspace remains usable

#### Scenario: Editing survives background reconciliation
- **WHEN** a silent reconciliation response arrives while the user is typing into an edit field
- **THEN** the focused field keeps the in-progress text instead of being overwritten
