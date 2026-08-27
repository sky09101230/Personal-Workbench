## ADDED Requirements

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
