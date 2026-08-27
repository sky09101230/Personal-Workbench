## Context

Personal Workbench 是 FastAPI + React/TypeScript 单体仓库，后端模块按 domain、application、infrastructure、presentation 分层，多个模块共用 `DATABASE_URL` 指向的 SQLite 文件，并在 `app/main.py` 完成组合。Todo 必须是新的同级模块，不能依赖 Literature 或 News 的内部实现；可复用的只有核心配置值、FastAPI/SQLite/httpx 等仓库级技术依赖和 Workbench Shell。

Todo v0.1 的关键不是功能数量，而是三个不可混淆的语义：`planned_date` 与 `due_date` 独立、Carryover 是不改写任务的查询、AI 先产出可审阅 proposal 且只有 Accept 才修改 Task。系统面向单个用户和约 4 至 6 个 active projects，不引入用户、权限或团队模型。

## Goals / Non-Goals

**Goals:**

- 用独立领域模型和稳定 API 支持 Project、Task、Inbox、Next Action 和五个基础视图。
- 让 Today 按调用时的本地日期确定 Carryover 和 Planned Today，并同时汇总所有 active projects。
- 通过原子仓储操作保证同项目最多一个 unfinished Next Action，以及 proposal 接受的一次性应用。
- 通过 `TodoPlannerPort` 隔离 AI Provider，并保存可审阅、可接受或拒绝的 proposal。
- 保持 Quick Capture 只要求标题，支持在后续编辑中补全项目和计划信息。

**Non-Goals:**

- Kanban、Gantt、子任务树、标签/GTD、四象限、番茄钟、习惯、积分、协作与权限。
- recurrence、日历双向同步、后台自动 carryover 写入和 AI 自动执行。
- 从 Literature 或 News 自动创建任务，或在 Todo 中导入其内部类型。
- 通用项目管理平台、跨设备同步和历史审计系统。

## Decisions

### 1. Todo 使用独立领域类型和应用端口

`Project`、`Task`、`PlanProposal`、`PlanProposalItem` 使用 Python dataclass 和 Enum 表达，日期/时间在领域边界分别使用 `date` 与带时区 `datetime`。Application 定义 `TodoRepository` 与 `TodoPlannerPort` Protocol，`TodoService` 只依赖这些端口。

选择这一方式而不是复用 News/Literature 模型，是为了让 Todo 的状态机、日期和事务语义独立演进。也不引入 ORM，因为仓库已有直接 SQLite 模式，v0.1 的关系简单且无需新增依赖。

### 2. Project 删除与 Task 生命周期保持轻量

Project 支持 create/read/update/delete；删除 Project 时通过外键 `ON DELETE SET NULL` 将其未删除任务移入 Inbox，避免隐式丢失个人待办。归档和暂停通过 `status` 更新完成。Task 支持 create/read/update/delete，完成/取消通过 `status` 更新；设置 `done` 时写入 `completed_at`，离开 `done` 时清空它。

相比把删除等同归档，显式 DELETE 更符合 CRUD 契约；相比级联删除任务，保留任务更符合“快速记住事情”的核心目标。

### 3. Next Action 唯一性由事务保证

“active Next Action”定义为 `is_next_action = true` 且 Task 状态为 `todo` 或 `doing`。将某任务设为 Next Action 时，repository 在同一写事务内先清除同项目其他任务的标志，再更新目标任务；Inbox 任务不能设为 Next Action。Task 完成、取消、移出项目或所属 Project 不再 active 时，该任务不再作为 overview 的 Next Action 展示。

仅靠前端取消旧标志会产生并发和多客户端不一致，因此唯一性必须在后端写入边界保证。

### 4. Today 与 Carryover 是纯查询

`TodoService` 注入可替换 clock，并按 `Asia/Shanghai` 计算当前日期。Carryover 查询条件是 unfinished 且 `planned_date < today`；Planned Today 是 unfinished 且 `planned_date = today`。查询绝不更新 `planned_date`。Active Projects Overview 只包含 active Project，返回 unfinished count 和当前 Next Action。

不建立每日快照或自动迁移任务，因为它们会引入重复状态并破坏用户原计划的证据。

### 5. Upcoming 合并 planned 与 due，但保留字段原义

Upcoming 返回 unfinished 且 `planned_date > today` 或 `due_date > today` 的任务，排序使用最近的未来日期后再按创建时间稳定排序。响应始终分别返回 `planned_date` 和 `due_date`，不生成统一“日期”字段。

### 6. Proposal 是独立持久化聚合并实行一次性接受

Planner 输入包含当前本地日期时间、active projects、所有 unfinished tasks、carryover、planned today、due dates 和 Next Actions。Planner 输出先映射为 `PlanProposal` 与 items；生成成功后只写 proposal 表，不更新 Task。proposal 状态为 `pending`、`accepted` 或 `rejected`。Accept 在一个事务中验证 proposal 仍 pending、任务仍存在，然后应用 `suggested_planned_date` 与可选 priority 并将 proposal 标为 accepted；Reject 只变更 proposal 状态。重复 Accept/Reject 返回冲突。

相比让 AI 返回任意 patch，这个白名单数据结构将可变更字段限制在 v0.1 明确允许的范围，也让 review UI 可准确展示差异。

### 7. DeepSeek 只在 infrastructure 解析结构化结果

`DeepSeekTodoPlanner` 使用现有 Settings 中的 DeepSeek key/base URL/model 和 httpx，向 Chat Completions 发送明确的 JSON 输入与不信任源文本的 system prompt，并只接受任务 ID 属于输入集合、日期/priority 合法的 JSON items。未配置、HTTP 失败或响应无效时抛出稳定的 Planner 错误；应用层不保存半成品 proposal，已有 Project/Task 不受影响。

不复用 `DeepSeekNewsSummarizer`，因为其提示词、失败策略和输出契约属于 News 内部实现。

### 8. API 与前端围绕工作流而不是表结构组织

API 使用 `/api/todo` 前缀：Projects/Tasks 提供资源操作，`/inbox`、`/today`、`/upcoming`、`/completed` 提供查询，`/plan-proposals` 提供 generate/get/accept/reject。Presentation 负责请求校验和 JSON 转换，不包含日期或唯一性规则。

前端以一个 `TodoPage` 提供 Today、Inbox、Projects、Upcoming、Completed tabs；Quick Capture 常驻模块顶部，只要求标题。Projects tab 内联选择项目详情；AI proposal 在 Today 中生成、审阅并 Accept/Reject。v0.1 不引入新的路由库或状态管理依赖。

## Risks / Trade-offs

- [直接 SQLite 在并发写入时可能短暂锁库] → 所有复合写操作保持短事务，沿用单用户本地工作台假设。
- [Project 硬删除把任务移入 Inbox 可能让用户意外失去分类] → API 明确返回成功结果，前端删除前确认，并优先提供 archive 状态操作。
- [AI 可能返回过多任务或无效 ID] → Infrastructure 严格白名单解析，Application 重新验证 proposal items，失败时不持久化。
- [Proposal 生成后 Task 可能被编辑] → Accept 时重新加载/验证任务；v0.1 只对白名单字段做最后写入，不覆盖 title、description、status 或 due date。
- [没有前端测试运行器] → 关键前端流程通过生产 TypeScript 构建验证，行为覆盖由 API 集成测试和手工可执行契约承担，不宣称 pytest 覆盖浏览器行为。

## Migration Plan

1. Todo repository 首次使用时在共享 SQLite 中建立独立 `todo_schema_migrations` 与 `todo_*` 表，不修改现有模块表。
2. 在 composition root 注册 Todo service/router；前端注册 Todo 模块与路由分支。
3. 部署后由用户手动重启 API 与 Vite；首次 Todo 请求惰性创建表。
4. 回滚代码不会删除 Todo 表和数据；重新部署本 change 可继续读取。若必须完全移除数据，应另行执行显式备份与迁移，不在应用启动时自动删除。

## Open Questions

无。v0.1 的日期时区固定为 `Asia/Shanghai`，单用户边界、删除语义和 proposal 可变更字段均在本 change 内确定。
