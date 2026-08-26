## ADDED Requirements

### Requirement: Planner receives complete cross-project context
The system SHALL call a replaceable `TodoPlannerPort` with the current local date/time, active Projects, unfinished Tasks, Carryover, Planned Today, due dates, and current Next Actions.

#### Scenario: Generate a cross-project plan
- **WHEN** the user requests Plan My Day with unfinished work across multiple active Projects
- **THEN** the planner receives sufficient structured context to select work across Projects and to identify work it does not recommend today

### Requirement: Generated plan is an independent proposal
The system SHALL persist a generated Plan Proposal and proposal items separately from Tasks, with each item limited to a valid `task_id`, `suggested_planned_date`, optional `suggested_priority`, and optional `reason`.

#### Scenario: Generation does not mutate tasks
- **WHEN** the planner successfully generates a proposal
- **THEN** the system saves a pending proposal and leaves every Task field unchanged

#### Scenario: Invalid planner item is rejected
- **WHEN** planner output references a Task outside the supplied context or contains an invalid date or priority
- **THEN** the system rejects the output without persisting a proposal or changing Tasks

### Requirement: User review gates all task changes
The system SHALL apply proposal suggestions only after explicit Accept and SHALL allow a pending proposal to be rejected without Task changes.

#### Scenario: Accept applies whitelisted changes atomically
- **WHEN** the user accepts a pending proposal
- **THEN** the system atomically applies each suggested planned date and optional priority to the referenced Tasks and marks the proposal accepted

#### Scenario: Reject preserves tasks
- **WHEN** the user rejects a pending proposal
- **THEN** the system marks it rejected and leaves every Task unchanged

#### Scenario: Proposal decision is one-time
- **WHEN** the user tries to accept or reject a proposal that is no longer pending
- **THEN** the system returns a conflict and makes no additional Task changes

### Requirement: Planner failure is non-destructive
The system SHALL surface unavailable, HTTP, timeout, and invalid-response planner failures without deleting or modifying existing Projects or Tasks.

#### Scenario: Planner request fails
- **WHEN** the configured planner raises an error while generating a plan
- **THEN** the API reports a stable planner failure and all existing Todo data remains unchanged

### Requirement: Today UI supports proposal review
The Today view SHALL let the user generate a Plan My Day proposal, inspect each suggested Task change and reason, and explicitly Accept or Reject it.

#### Scenario: Review before accepting
- **WHEN** a proposal is generated in Today
- **THEN** the UI displays the proposal separately from actual Today Tasks until the user chooses Accept

#### Scenario: Refresh after decision
- **WHEN** the user accepts or rejects a proposal
- **THEN** the UI refreshes Today data and clearly reflects the proposal decision
