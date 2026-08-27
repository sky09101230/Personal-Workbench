## Why

Personal Workbench 已能管理文献和外部信息，但缺少一个低摩擦、跨项目的行动工作台。个人同时推进 4 至 6 个项目时，需要可靠地记住每个项目的下一步、让过期未完成计划自然回到视野，并在用户确认后才应用 AI 的跨项目日程建议。

## What Changes

- 新增与 Literature、News 平级且互不依赖的 Todo 模块，管理轻量 Project、Task、状态和日期语义。
- 提供 Quick Capture 与 Inbox，让任务可以只凭标题快速创建，随后再归入项目。
- 为每个 active Project 突出唯一的 active Next Action，并在设置新项时自动取消同项目旧项。
- 提供 Today、Inbox、Projects、Upcoming、Completed 查询与页面；Today 明确区分 Carryover、Planned Today 和 Active Projects Overview，且查询 Carryover 时不改写原始 `planned_date`。
- 定义可替换的 `TodoPlannerPort` 和 DeepSeek 基础设施实现，生成跨项目的 Plan Proposal。
- 将 AI Proposal 与 Task 严格分离；生成或拒绝 proposal 不修改 Task，只有用户明确接受后才应用建议。
- 为领域语义、SQLite repository、应用服务、API 和关键前端流程补齐验证。
- 明确排除 Kanban、Gantt、复杂子任务/标签/GTD、团队协作、日历同步、recurrence、跨模块自动建任务与 AI 自动执行。

## Capabilities

### New Capabilities

- `todo-project-task-management`: 轻量 Project/Task 生命周期、Quick Capture、Inbox、独立 due/planned 日期和唯一 Next Action。
- `todo-today-views`: Today、Carryover、Active Projects Overview、Upcoming 与 Completed 的稳定查询和前端工作流。
- `todo-ai-day-planner`: 可替换 Planner 端口、跨项目日计划 proposal、review/accept/reject，以及接受后才修改 Task 的安全边界。

### Modified Capabilities

无。

## Impact

- 后端：新增 `apps/api/app/modules/todo/` 四层结构，并在 `app/main.py` 组合 repository、planner、service 与 router。
- 数据库：继续使用 `DATABASE_URL` 指向的 SQLite，新增仅由 Todo 基础设施层管理的 `todo_*` 表。
- API：新增 `/api/todo/*`；现有 `/api/literature/*` 和 `/api/news/*` 契约保持不变。
- 前端：新增 `apps/web/src/modules/todo/`，扩展模块注册与顶层路由，复用现有 Workbench Shell。
- 配置：复用后端 DeepSeek 凭据与 HTTP 基础设施边界，但 Todo 不导入 News 或 Literature 的内部代码。
