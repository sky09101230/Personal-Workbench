## Context

Personal Workbench 已有 FastAPI + React 的模块壳，以及按 `domain / application / infrastructure / presentation` 分层的 Literature。Literature 面向已进入个人文库的长期对象，Zotero 是其 source of truth；News 面向短生命周期的外部发现 Feed，必须拥有独立模型、表和 API，不能通过读取 Literature 数据库实现复用。

本 change 只证明统一 Feed 可以由可替换 Provider 写入 SQLite，再被稳定 API 和统一页面读取。真实 Papers、GitHub、GitHub Skills、AI News 与 X 适配器均留待后续 change。

## Goals / Non-Goals

**Goals:**

- 用一个 Provider 无关的 `FeedItem` 覆盖五类未来内容，同时只保留跨来源稳定字段。
- 让新增 Provider 只需实现一个 port 并在组合根注册，不改写 News service、SQLite schema、API 或页面结构。
- 建立 `Provider adapter normalization → topic match → SQLite feed → API` 的清晰边界。
- 在现有 SQLite 文件中保存 News metadata、Topic 匹配和用户状态，同时保持表与迁移命名独立。
- 提供可验证的 demo provider 和最小前端浏览壳。

**Non-Goals:**

- 不完整接入任何真实来源，不实现 OAuth、rate limit 策略、抓取器、RSS 聚合或后台定时任务。
- 不实现 AI ranking、LLM summary、Embedding、RAG、推荐、Daily Digest 或复杂规则引擎。
- 不实现 News 到 Zotero/Literature 的写入动作；未来该动作必须通过明确 application service 边界。
- 不保存网页正文、PDF、仓库内容或 X 帖子的完整远端载荷。

## Decisions

### FeedItem is the only public item contract

News domain 使用 `FeedItem`、`FeedItemType`、`Topic` 与分页结果。`FeedItem` 包含稳定展示字段、Topic 标识和 read/saved/hidden 状态；来源私有字段只能经过清理后放入有限的 `metadata` JSON。API 与前端不接收 Provider 原始响应。

Provider-specific DTO 和映射留在各自 adapter 内，比在 application 层建立一个可容纳所有远端字段的“万能 raw model”更能维持边界。Provider port 直接返回已标准化的 `FeedItem`，service 再负责 Topic Match 和持久化。

### Providers are composed as a collection

`NewsService` 依赖 `tuple[NewsSourcePort, ...]` 和 `NewsRepository`。`refresh()` 顺序调用已注册 Provider，将标准化 item 与配置的 Topics 进行简单关键词匹配，再统一 upsert。新增真实来源只增加 adapter 目录并在 `app/main.py` 注册，不增加按类型分支的 service。

本轮 matcher 仅做大小写不敏感的正向/负向关键词包含判断，并尊重 `enabled_sources`；不计算 relevance score。SQLite 主键 upsert 只保证同一稳定 item id 更新，不宣称跨来源语义去重。

### News owns isolated SQLite tables and migrations

News 继续使用 `DATABASE_URL` 指向的 SQLite 文件，但只访问：

- `news_feed_items`：统一 metadata，不含网页全文。
- `news_topics`：Topic 配置 JSON。
- `news_item_topics`：item/topic 多对多匹配。
- `news_user_state`：read/saved/hidden，和可替换的 feed metadata 分离。
- `news_schema_migrations`：避免与 Literature 当前的 `schema_migrations` 版本号冲突。

外键只在 `news_*` 表之间建立。News repository 不查询或写入 `literature_*` 表；Literature repository 也无需了解 News。

### Feed reads cache and refresh is explicit

`GET /api/news/feed` 只读本地 SQLite，并支持 `type`、`topic`、`limit`、`offset`。`GET /api/news/topics` 返回持久化的配置 Topics。`POST /api/news/refresh` 是唯一触发 Provider 读取的端点，返回按 Provider 汇总后的写入数量。

不在应用启动时或后台自动刷新，以免 demo 行为演变成隐式任务。新数据库可先显示明确 empty 状态；用户点击 Refresh 后，demo provider 验证完整流程。

### Frontend uses one shell with type-specific presentation hints

模块注册表增加 News 路径，顶层 `App` 根据路径选择 Literature 或 News，不引入路由依赖。News 页面固定提供类型 tabs、Topic select、刷新按钮和统一 `FeedCard`；卡片只对类型标签和少量 metadata 做展示差异，不拆成五套页面。

## Risks / Trade-offs

- [简单关键词匹配会有误报或漏报] → 明确作为框架验证器；后续可在 application 边界替换 matcher，不改变 Provider/API/UI 契约。
- [Provider 返回无效或不稳定 id 会影响 upsert] → port 要求来源 adapter 生成带来源命名空间的稳定 id，并以单元测试固定该契约。
- [多个 Provider 中途失败会造成不一致] → 本轮 refresh 先收集全部结果，再在单次 repository 事务中写入；任一 Provider 失败则不更新 Feed。
- [长期积累会扩大 SQLite] → 本轮不擅自加入保留期策略；后续 change 根据真实来源和使用量定义清理规则。
- [无前端测试 runner] → 以 TypeScript production build 验证类型与打包，交互行为不声称被自动化浏览器覆盖。

## Migration Plan

1. 新增 News 领域、ports、service、demo provider 与独立 SQLite repository，不改动 Literature 模型或表。
2. 在 FastAPI 组合根注册 News service/router，并用临时 SQLite API 测试验证 refresh、Topic 匹配和筛选。
3. 注册前端模块和 `/news` 页面；默认空状态可安全存在，手动 Refresh 后展示 demo Feed。
4. 运行完整后端测试、前端 production build 和 `git diff --check`。回滚只需移除 News 代码与注册；遗留 `news_*` 表不影响 Literature。

## Open Questions

- 真实 Provider 接入后，Feed 保留期和按来源清理策略需要基于实际流量单独设计。
- read/saved/hidden 的写 API 与“News Paper → Add to Zotero”动作留给后续 change 定义。
