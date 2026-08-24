## Why

Personal Workbench 目前只有面向长期文献管理的 Literature，缺少一个用于发现、筛选和浏览外部信息的独立入口。现在先建立 Provider 无关的 News 骨架，可以让 Papers、GitHub、Skills、AI News 与 X 后续逐个接入，而不把来源协议或短期 Feed 状态混入 Literature。

## What Changes

- 新增独立 News 模块，以统一 `FeedItem` 表达五类未来内容，并保持 News 与 Literature 的领域和数据库表隔离。
- 定义 `NewsSourcePort`，建立 `Provider → Normalize → Topic Match → Feed` 的应用流程，并用极简 demo provider 验证端到端边界。
- 在现有 SQLite 数据库中新增 News 专属表，保存 Feed metadata、Topic 匹配和 read/saved/hidden 用户状态，不保存网页全文。
- 提供稳定的 `/api/news/feed`、`/api/news/topics` 和 `/api/news/refresh` API，不暴露 Provider 私有响应。
- 将 News 注册为 Workbench 独立前端模块，提供类型 tabs、Topic filter、统一 Feed Card，以及 loading、empty、error 状态。
- 明确排除真实五源完整接入、AI ranking/summary、Embedding、RAG、推荐、Digest 与后台定时任务。

## Capabilities

### New Capabilities

- `news-feed`: 统一 News Feed、Topic 配置、SQLite cache/state、稳定 API 和前端模块壳。
- `news-source-framework`: Provider 插件端口、标准化刷新流程和可替换的 demo provider。

### Modified Capabilities

无。

## Impact

- 后端：新增 `apps/api/app/modules/news/`，并在 `app/main.py` 组合 News repository、provider、service 与 router。
- 数据库：继续使用 `DATABASE_URL` 指向的 SQLite，新增仅由 News 基础设施层管理的 `news_*` 表。
- API：新增 `/api/news/*`；现有 `/api/literature/*` 契约保持不变，News 不依赖 Zotero。
- 前端：新增 `apps/web/src/modules/news/`，扩展模块注册与顶层模块路由，复用现有 Workbench Shell。
- 依赖：不增加运行时依赖，不引入外部数据源凭据或后台进程。
