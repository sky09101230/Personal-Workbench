# Todo Project and Task Management Specification

## Purpose

Define the lightweight Project and Task lifecycle behind /api/todo, including Quick Capture, Inbox semantics, independent due and planned dates, and the single active Next Action per Project.

## Requirements

### Requirement: Lightweight project lifecycle
The system SHALL let the user create, read, update, archive, pause, reactivate, order, and delete lightweight Projects with `active`, `paused`, and `archived` statuses.

#### Scenario: Create and reorder an active project
- **WHEN** the user creates a Project with a name and later changes its order
- **THEN** the system persists the Project as active by default and returns it in the requested stable order

#### Scenario: Pause or archive a project
- **WHEN** the user changes a Project status to paused or archived
- **THEN** the system persists that status and excludes the Project from active-project queries

#### Scenario: Delete a project without deleting tasks
- **WHEN** the user deletes a Project that owns Tasks
- **THEN** the system removes the Project and preserves those Tasks with a null `project_id`

### Requirement: Task lifecycle and independent dates
The system SHALL let the user create, read, update, complete, cancel, reopen, and delete Tasks with `todo`, `doing`, `done`, and `cancelled` statuses, while preserving `due_date` and `planned_date` as independent optional fields.

#### Scenario: Planned date does not imply due date
- **WHEN** the user creates or updates a Task with only a `planned_date`
- **THEN** the system persists the requested `planned_date` and leaves `due_date` null

#### Scenario: Due date does not imply planned date
- **WHEN** the user creates or updates a Task with only a `due_date`
- **THEN** the system persists the requested `due_date` and leaves `planned_date` null

#### Scenario: Complete and reopen a task
- **WHEN** the user marks a Task done and later changes it back to todo or doing
- **THEN** the system sets `completed_at` on completion and clears it when reopened

### Requirement: Low-friction Quick Capture and Inbox
The system SHALL allow Task creation with only a non-empty title and SHALL define Inbox as unfinished Tasks whose `project_id` is null.

#### Scenario: Capture with title only
- **WHEN** the user submits Quick Capture with only a title
- **THEN** the system creates an unfinished Task without forcing priority, dates, tags, estimates, subtasks, description, or Project

#### Scenario: Assign an Inbox task
- **WHEN** the user assigns a valid Project to an Inbox Task
- **THEN** the Task leaves the Inbox and retains its other values

#### Scenario: Completed unassigned task is not in Inbox
- **WHEN** an unassigned Task is done or cancelled
- **THEN** the system excludes it from the Inbox query

### Requirement: One active Next Action per project
The system SHALL support at most one unfinished Next Action per Project and SHALL make setting a new one clear the previous active Next Action in the same Project atomically.

#### Scenario: Replace a project's Next Action
- **WHEN** the user marks a second unfinished Task as Next Action in the same Project
- **THEN** the system keeps the second Task marked and clears `is_next_action` from the first Task in one operation

#### Scenario: Reject an Inbox Next Action
- **WHEN** the user tries to mark a Task with null `project_id` as Next Action
- **THEN** the system rejects the update and leaves existing Tasks unchanged

#### Scenario: Completed Next Action is no longer active
- **WHEN** the user completes or cancels the current Next Action
- **THEN** active Project views no longer present that Task as the project's Next Action

### Requirement: Stable Todo resource API
The system SHALL expose Project and Task resource operations under `/api/todo` without exposing SQLite details or importing Literature or News internal contracts.

#### Scenario: API resource round trip
- **WHEN** an API client creates, updates, reads, and deletes Todo Projects or Tasks
- **THEN** the API returns stable JSON representations and appropriate success, validation, not-found, or conflict responses
