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

### Requirement: Compact task rows with expand-to-edit
The Todo frontend SHALL render each Task as a compact row by default showing completion, title, and concise scheduling context, and SHALL expose the full editing fields only when that row is expanded.

#### Scenario: Review a list without expanding editors
- **WHEN** the user opens any Todo task list
- **THEN** each Task renders as one compact row with a completion control, title, and metadata such as Project, Next Action marker, planned or due dates, priority, and a notes indicator, without persistent form fields

#### Scenario: Expand a single row to edit
- **WHEN** the user expands a Task row
- **THEN** the full editing fields for that Task appear while other rows remain compact

### Requirement: Field-level commit semantics
The Todo frontend SHALL commit each edited Task attribute when the user leaves the field or changes the selection, SHALL treat Enter as commit for the title field, and SHALL NOT require a separate per-card save action for ordinary field edits.

#### Scenario: Rename without pressing a save button
- **WHEN** the user edits a Task title and then leaves the field or presses Enter
- **THEN** the change is persisted without requiring any additional save click

#### Scenario: Selection fields follow the same rule
- **WHEN** the user changes a Task's Project, planned date, due date, or priority
- **THEN** the change persists immediately under the same leave-or-change rule as every other field

### Requirement: Project information edits persist safely
The Todo frontend SHALL let the user edit a Project description and its manual completed items directly, committing the description when the field is left and persisting each completed-item add or remove immediately, without a staged whole-form save step.

#### Scenario: Typing is not overwritten by background refreshes
- **WHEN** the user is editing a Project description and background data reconciliation occurs before the edit is committed
- **THEN** the in-progress text remains untouched until the user leaves the field

#### Scenario: Track a completed item one at a time
- **WHEN** the user adds or removes one manual completed item
- **THEN** that change is persisted individually without pressing a separate save button
