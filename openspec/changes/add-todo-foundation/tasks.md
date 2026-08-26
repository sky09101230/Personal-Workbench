## 1. Todo domain and application contracts

- [x] 1.1 Create the independent Todo module package structure and domain models for Project, Task, PlanProposal, and view aggregates
- [x] 1.2 Define Todo repository and planner ports plus stable application errors
- [x] 1.3 Implement TodoService project/task lifecycle rules, Next Action uniqueness orchestration, and injected local-date semantics
- [x] 1.4 Implement Today, Inbox, Upcoming, Completed, and active-project overview application queries
- [x] 1.5 Implement proposal generation, validation, accept, and reject workflows without generation-time Task mutation

## 2. Infrastructure and API

- [x] 2.1 Implement the isolated versioned SQLite Todo schema and Project/Task CRUD repository operations
- [x] 2.2 Implement SQLite view queries, atomic Next Action replacement, and atomic proposal decision operations
- [x] 2.3 Implement DeepSeekTodoPlanner behind TodoPlannerPort with strict structured-output validation and stable failures
- [x] 2.4 Add Todo FastAPI request/response contracts and Project, Task, view, and proposal endpoints
- [x] 2.5 Wire the Todo repository, planner, service, and router in the composition root without cross-module imports

## 3. Backend verification

- [x] 3.1 Add domain/service/repository tests for Project and Task CRUD/status, date independence, Inbox, and Next Action uniqueness
- [x] 3.2 Add Today/Carryover/Upcoming/Completed/project-count tests including non-mutating Carryover behavior
- [x] 3.3 Add planner/proposal tests for non-mutation, accept/reject, invalid/failing planner safety, and atomic application
- [x] 3.4 Add Todo API integration tests for successful workflows and stable validation/error responses

## 4. Frontend Todo workbench

- [x] 4.1 Add Todo TypeScript contracts and API client for all v0.1 resources and views
- [x] 4.2 Register `/todo` as a sibling Workbench module and route it through the existing shell
- [x] 4.3 Implement Quick Capture plus Today, Inbox, Projects, Upcoming, and Completed views with loading/empty/error states
- [x] 4.4 Implement project/task editing, assignment, completion/cancellation/deletion, and unique Next Action controls
- [x] 4.5 Implement Plan My Day proposal generation, review, Accept, Reject, and post-decision refresh
- [x] 4.6 Add Todo-scoped responsive styling without altering unrelated module presentation

## 5. Full validation and handoff

- [x] 5.1 Run the full backend pytest suite and resolve all regressions
- [x] 5.2 Run the frontend production build and resolve TypeScript/build failures
- [x] 5.3 Run OpenSpec strict validation and `git diff --check`
- [x] 5.4 Review branch diff for module independence and scope, then create a focused implementation commit without archiving or merging
