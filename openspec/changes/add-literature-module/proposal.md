## Why

个人科研工作台已经具备 Workbench Shell、Literature 领域边界，以及 Zotero Web API 的只读连接，但这些成果尚未作为一个可追溯的产品 change 记录。没有明确的 V0.1 契约与阶段任务，后续加入浏览、PDF、缓存和同步时容易让前端直接依赖 Zotero，或重复实现已有基础设施。

## What Changes

- 将 Literature 正式定义为工作台的首个独立模块，并保留 Provider 与领域模型之间的边界。
- 记录已完成的 Foundation 与 Zotero Web API 连接：后端凭据保护、Collections、顶层文献元数据、分页与基础错误处理。
- 完成剩余的文献库体验：Collections 导航、文献浏览、搜索、筛选、详情与 Notes。
- 为 SQLite metadata cache 增加首次全量同步和后续增量同步，避免每次打开页面都扫描 Zotero。
- 提供独立 PDF Reader、受后端保护的 PDF 流与下载操作。

## Capabilities

### New Capabilities

- `literature-library`: 在 Workbench 中浏览、筛选和查看工作台自身的文献与 Notes 模型。
- `zotero-literature-provider`: 通过后端安全地将 Zotero Web API 映射为 Literature 领域数据，并提供本地缓存同步。
- `literature-pdf-reader`: 提供独立的只读 PDF 浏览与下载体验，不引入自定义批注编辑器。

### Modified Capabilities

无。

## Impact

- 后端：`apps/api/app/modules/literature/`、`apps/api/app/core/config.py` 和 SQLite 配置。
- 前端：`apps/web/src/modules/literature/`、Workbench Shell 的模块注册与 API 调用。
- API：扩展 `/api/literature/*`，始终保持 Zotero API Key 不离开后端。
- 依赖：保留 FastAPI、httpx 与 SQLite；PDF Reader 使用 PDF.js，不增加 AI、向量数据库或后台调度依赖。
