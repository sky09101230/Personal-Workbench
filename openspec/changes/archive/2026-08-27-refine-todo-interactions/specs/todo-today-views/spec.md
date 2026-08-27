## ADDED Requirements

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
