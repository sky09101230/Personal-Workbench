## 1. Frontend data flow and mutation handling

- [x] 1.1 Rework `TodoPage` mutation handling into optimistic write-through: apply the patch to local state first, reconcile from the response, roll back the previous snapshot on failure, and show errors inline without replacing list content
- [x] 1.2 Remove the global `mutating` lock; keep full-page loading only for initial render and view switches, and scope pending indicators to the control performing the mutation
- [x] 1.3 Add silent background reconciliation after successful mutations that refreshes derived views (Today grouping, project overviews) without a loading state, ignoring stale responses

## 2. Task card redesign

- [x] 2.1 Implement the collapsed row layout in `TaskCard`: completion checkbox, title text, and metadata badges (project, Next Action star, planned/due dates, priority, notes indicator)
- [x] 2.2 Implement the expanded editor containing title input, description textarea, Project/plan/due/priority fields, and Cancel / Make next / Delete actions with stable expand state across re-renders
- [x] 2.3 Apply field-level commit semantics: commit on blur or selection change everywhere, Enter commits the title, and remove the per-card Save button while keeping delete confirmation
- [x] 2.4 Ensure reconciliation never writes server data into a focused/uncommitted edit field on task cards and project inputs

## 3. One-action rescheduling

- [x] 3.1 Add the "→ 今天" quick action to collapsed Carryover and Upcoming rows that patches `planned_date` to today
- [x] 3.2 Add the Carryover section bulk "全部移到今天" action running sequential per-task patches so one failure neither blocks nor reverts the others
- [x] 3.3 Verify empty Carryover/Upcoming and all-unfinished edge cases leave no stray actions or broken states

## 4. Project info editing unification

- [x] 4.1 Commit the Project description on blur via direct PATCH and remove the staged whole-form save step
- [x] 4.2 Persist each manual completed-item add/remove immediately as its own project patch and drop the local staging array
- [x] 4.3 Update the Projects page copy (including the 已完成事项 source note) to match the new editing flow

## 5. Verification and handoff

- [x] 5.1 Run `npm.cmd --prefix apps\web run build` and resolve TypeScript/build failures
- [x] 5.2 Run the backend pytest suite to confirm no backend regressions
- [x] 5.3 Run OpenSpec strict validation and `git diff --check`
- [x] 5.4 Manually walk through every spec scenario against the running app (Vite + API restarted by the user), covering: list scanning without expansion, rename via Enter/blur, selection-field immediacy, back-to-back task completion during in-flight requests, failed-request rollback message, bulk and single carryover reschedule, description typing surviving refresh, per-item completed-item persistence
