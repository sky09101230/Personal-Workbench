## Context

Literature 是个人科研工作台的第一个领域模块。当前仓库已完成 Workbench Shell、前端模块注册、Provider 无关的 `Paper`/`Collection`/`Note`/`Attachment` 模型，以及 Zotero Web API v3 的只读 Collections 和顶层文献读取。后端 API Key 由 `.env` 加载，仅在 API 进程中使用；已有 mocked HTTP 与 API 契约测试。

剩余 V0.1 工作是把这些基础能力变成可日常使用的文献库：本地 metadata cache、浏览与详情界面、Notes、PDF 附件代理和独立 Reader。该工作台只供个人使用，优先选择本机可维护性而非多用户扩展。

## Goals / Non-Goals

**Goals:**

- 让 Literature 保持自己的领域模型与 HTTP API，Zotero 仅作为当前 Provider。
- 为首次全量同步和后续增量同步建立 SQLite metadata cache，降低日常浏览的网络依赖。
- 提供 Collections、文献列表、搜索、基础筛选、详情、Notes、PDF 浏览和下载的完整个人工作流。
- 让 PDF Reader 独立于 Literature 首页，并保持浏览器不持有 Zotero 凭据。

**Non-Goals:**

- 不实现 AI 问答、RAG、Embedding、向量数据库、推荐、自动分类或知识图谱。
- 不实现多人协作、RBAC、多租户、后台定时同步或复杂插件框架。
- 不实现 PDF 自定义批注编辑器，也不永久复制 PDF 到工作台。
- 不在本 change 中实现 Zotero Local API；只保留通过 Provider port 增加该适配器的边界。

## Decisions

### Literature owns the domain contract

`Paper`、`Collection`、`Attachment` 与 `Note` 是 Literature 的通用模型；`ExternalReference` 保存 provider、library id 和 item key。Presentation 只依赖应用服务，应用服务只依赖 Provider port，Zotero JSON 字段、请求 URL 和认证 Header 仅存在于基础设施 Adapter。

这是为了允许未来新增 `ZoteroLocalAdapter` 或其他数据源，而不重写前端 API 或领域模型。直接让前端调用 Zotero 的方案更少代码，但会暴露凭据并把 UI 固定到单一 Provider，因此不采用。

### Zotero Web API is the Phase 1 provider

当前个人库通过 `ZOTERO_USER_ID` 和 `ZOTERO_API_KEY` 连接到 Zotero Web API v3。Adapter 使用版本 Header、API Key Header、`/collections` 和 `/items/top`，将 Provider 标识封装为不透明的工作台资源 id。所有上游认证、连接和响应格式问题在模块边界转换为稳定的工作台错误码。

不直接使用浏览器请求或 API Key 查询参数，前者泄露密钥且受跨域限制，后者会污染 URL 和日志。

### SQLite caches metadata, not PDF binaries

SQLite 保存 Papers、Collections、Tags、Notes、Attachment metadata、外部引用与 Zotero library version。首次同步分页读取全库；后续同步使用保存的 library version 请求已修改对象，并以事务写入本地 metadata。PDF 仍在用户请求时通过后端按需取得，不进入本地数据库。

对个人工具而言，SQLite 是零运维方案；每次页面加载都直接全库读取 Zotero 虽简单，但会带来明显延迟和 API 限流风险。

### Library and Reader are separate surfaces

Literature 首页固定为 Collections、文献列表和详情三栏。PDF 通过独立 `/literature/papers/:id/reader` 页面展示，Reader 使用 PDF.js 提供翻页、页码跳转、缩放、适配和下载。Notes 作为 Reader 可开关的侧栏，而不是嵌入首页的 PDF 预览。

这避免首页在浏览文献时被大型 PDF 画布占据，也避免在 V0.1 引入自定义 Annotation 编辑状态。

## Risks / Trade-offs

- [Zotero 附件可能是存储文件、链接文件或 WebDAV 文件] → 仅为可访问的 PDF attachment 暴露 Reader/下载；无法代理时返回明确的不可用状态，不伪造 PDF。
- [Web API 的分页、版本与限流是远端契约] → Adapter 集中处理请求 Header、分页和错误；同步保存 library version，并覆盖 mocked HTTP 测试。
- [缓存与远端内容短暂不一致] → UI 显示最后同步状态和手动 Sync；V0.1 不承诺实时推送。
- [SQLite schema 会随模块增长] → 将数据库访问限制在 Literature 基础设施层，并为同步/映射加入迁移与回归测试。
- [不同 Zotero item type 的元数据字段不同] → Mapper 优先保留通用字段，缺失字段为 `null` 或空集合，不用猜测填补。

## Migration Plan

1. 保持现有只读 API 与领域 ID 不变，先加入 SQLite schema 和 full sync。
2. 让 Collections 和 Papers API 从 cache 读取，并通过手动 Sync 更新 cache；无缓存时返回可操作的空/错误状态。
3. 接入 Library UI、详情和 Notes，再增加 Attachment/PDF proxy 与 Reader。
4. 每阶段执行后端测试、前端 build、API 契约检查和手动浏览器验证；部署失败时继续使用前一版本的 cache schema 和只读 API。

## Open Questions

- Zotero 中的 linked-file 与 WebDAV-only 附件在目标运行环境是否可通过 Web API 读取，需要真实个人库样本验证。
- V0.1 的全文搜索范围仅限 title/creator/year，还是要在缓存 metadata 上覆盖 journal、DOI 和 tags；默认先以基础 metadata 搜索为准。
