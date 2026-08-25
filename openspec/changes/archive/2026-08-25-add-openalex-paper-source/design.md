## Context

News Framework 已有稳定的 `FeedItem`、Provider port、Topic Match、事务性 SQLite 写入、Feed API 与统一前端卡片。当前 composition 只注册 Demo Provider，因此正式刷新无法发现真实论文。OpenAlex 是本轮唯一外部来源；实现必须保持 Provider-private 字段位于 `metadata`，且外部失败不能修改已有 cache。

OpenAlex `/works` 支持 `search`、publication date filter、`sort`、单页大小与可选 API key。abstract 以 inverted index 返回，需要在 adapter 内还原为纯文本。官方公共 API 可在无 Key 时试用；配置 Key 后应以 `api_key` query parameter 发送。

## Goals / Non-Goals

**Goals:**

- 以单一 OpenAlex provider 完成真实 paper discovery，并复用现有 News 流水线。
- 用当前 Topic keywords 生成最近 7 天、小批量、无深分页的查询。
- 完整标准化 work id、标题、摘要、作者、日期、链接及 bounded metadata。
- 对同一 OpenAlex work 的多 Topic 命中去重，并保持最终 Topic Match 由现有 service 决定。
- 将上游失败转换为稳定 News source error，且失败 refresh 不写 SQLite。
- 让现有 Papers tab 在不改变 Feed API schema 的前提下显示 paper metadata。

**Non-Goals:**

- arXiv、Crossref、Semantic Scholar 或跨来源 DOI 去重。
- 通用学术搜索、深分页、全量同步、付费增量 filter 或后台调度。
- Zotero、PDF、AI summary/ranking、embedding、recommendation 或 citation graph。
- News Framework 重构、SQLite migration 或 paper 详情页。

## Decisions

### 1. 最小扩展 `NewsSourcePort.fetch_items`

将签名扩展为 `fetch_items(*, topics: tuple[Topic, ...])`，由 `NewsService.refresh()` 传入其唯一 Topics 配置。原因是 discovery 查询必须使用当前 Topic keywords；若在 composition 中把 Topics 另行注入 OpenAlex provider，会复制 service 已持有的配置并产生漂移。Demo Provider 接收但忽略该参数，repository、API 与领域 schema 不变。

备选方案是保持 port 无参、让 provider 构造器持有 Topics；该方案改动表面更少，但形成两个配置入口，无法保证“查询 Topics”和“最终匹配 Topics”一致，因此不采用。

### 2. 每 Topic 一次受限 `/works` 请求

OpenAlex provider 只处理启用 `openalex` 的 Topics。每个 Topic 将非空 keywords 去重；单个关键词原样作为 `search`，多个同义关键词以带引号的布尔 `OR` 表达式组合，附加 `filter=from_publication_date:<UTC today-7 days>,to_publication_date:<UTC today>`、`sort=publication_date:desc`、固定小 `per_page`，且不请求后续页。negative keywords 不发给 OpenAlex，而是在 adapter 结果和现有 `_matches_topic` 中过滤，避免依赖 provider-specific query syntax。

没有可用关键词的 Topic 不触发无边界请求；这比抓取整个近期 corpus 更符合 discovery 范围。

### 3. Adapter 内标准化，service 再做稳定 id 去重

每个 work 映射为 `id=openalex:<W...>`、`type=paper`、`source=openalex`。DOI 优先作为 URL，其次 primary landing page，最后 OpenAlex work 页面。abstract inverted index 按位置还原；缺失或畸形时 summary 为 `None`。authors 来自 authorships；venue、DOI、topics、keywords、cited count、open access 与 work type 进入 bounded `metadata`。

Provider 在多 Topic 查询结果合并时按 OpenAlex work id 保留一份；`NewsService` 在验证后也按 FeedItem id 去重，作为写入前的通用不变量。DOI 只保留为 metadata，不在本轮承担跨来源身份合并。

### 4. 复用事务边界和稳定错误

Provider 对 `httpx.TimeoutException`、HTTP 429、401/403、其他非成功响应、JSON/shape 错误统一抛出 `NewsSourceError`，消息只描述稳定 source failure。`NewsService` 在全部 provider fetch/validate/dedup/topic-match 完成后才调用单次 `save_refresh`，因此任何 fetch 失败都不会触碰 SQLite。

### 5. 可选后端 Key 与 composition

`Settings` 增加 `openalex_api_key`，从 `OPENALEX_API_KEY` 读取；空值不发送参数，非空时每个请求都发送。Key 不进入 Feed metadata、API 响应或前端。正式 composition 只注册 `OpenAlexPaperProvider`；Demo class 和 fixtures 保留供测试/显式开发使用。

### 6. Feed schema 不变，前端解释 metadata

现有 `FeedItem.metadata_json` 足以持久化 OpenAlex 扩展信息。`GET /api/news/feed?type=paper` 保持原合约，`POST /api/news/refresh` 不带 `type` 时保留原有全量刷新行为，并允许用可选 `type` query 缩小刷新范围。`FeedCard` 仅在 item type 为 paper 时读取可选 metadata 并显示 venue、DOI 与 cited count，链接仍使用顶层 `url`。

### 7. 用本地日期 AM/PM 槽位限制成功抓取

production composition 将 OpenAlex 标记为半日槽位来源。`NewsService` 用 `Asia/Shanghai` 将当前时刻转换为 `YYYY-MM-DD-AM` 或 `YYYY-MM-DD-PM`：同一槽位已有成功记录且 SQLite 中的 Topic 查询配置与当前配置一致时，不调用任何上游 Provider，直接保留并使用现有 SQLite Feed；进入 PM、次日 AM 或 Topic 配置变化后可再次抓取。

槽位不使用需要定时重置的 Bool。SQLite schema version 2 新增 News-only source state 表。只有 Provider fetch、Topic Match、可选摘要和 Feed 写入全部成功后，才在同一事务中写入当前槽位；任何上游或写入失败均不占用槽位。

### 8. 成功 refresh 对账 News 快照

`save_refresh` 在单一事务内将 Topics 替换为当前配置，并删除不在本次结果中的旧 `news_feed_items`。仍在结果中的条目继续 upsert，因此其 `news_user_state` 保留；被移除条目的 News user state 由外键级联清除。该操作只使用 `news_*` 表，不读取、删除或改写共享数据库中的 `literature_*` 表。

### 9. Topic Match 是摘要与入库门槛

OpenAlex `search` 结果只是 bounded candidates。`NewsService` 仍先用 Provider-normalized title、abstract 与 authors 计算所有 Topic 关联，然后删除没有任何关联的候选；只有至少命中一个 Topic 的 work id 去重并集进入 DeepSeek enrichment 和 `save_refresh`。因此不带 `topic` 参数的 All topics Feed 等于各 Topic Feed 的并集，而不是 OpenAlex 原始候选集。

### 10. 类型 tab 约束刷新作用域

News 页面不再提供跨类型 `All` tab，默认进入 Papers。每个 tab 的刷新按钮将其 `FeedItemType` 作为 `POST /api/news/refresh?type=...` 传入；`NewsSourcePort` 声明支持的 `item_types`，service 只调用匹配 Provider。SQLite 对账也以该类型为边界，只删除该类型中不再返回的条目，同时保留其他类型的 Feed、用户状态和 Topic 关联。没有匹配 Provider 的类型返回成功空操作，不删除已有缓存。Topic 筛选属于 paper discovery，只在 Papers tab 呈现并参与 Feed 请求；切换到其他 tab 时保留其选择但不发送 `topic` query。

## Risks / Trade-offs

- [同义词或短关键词导致低相关性] → 仍执行现有 Topic Match、negative keyword 过滤和每 Topic 小结果上限。
- [publication date 不等于 OpenAlex ingestion time] → 本轮目标是近期发表 discovery，接受该边界；不使用需要付费能力的 updated/created filters。
- [同一 work 被多个查询返回] → Provider 与 service 两层按 OpenAlex namespaced id 去重。
- [OpenAlex 无 Key 公共访问策略变化] → 支持配置 Key，401/403 稳定失败且不污染 cache；部署可只修改环境变量后重启 API。
- [部分 work 字段缺失或 shape 不一致] → required envelope/identity/title 失败视为 malformed response；可选 abstract/metadata 缺失则安全降级。
- [同槽重复点击 Refresh] → service 在调用 Provider 前读取成功槽位并直接返回缓存结果；不依赖后台任务或定时重置。
- [成功刷新误删非 News 数据] → 快照对账 SQL 严格限定为 `news_*` 表，并以共享数据库中的非 News 哨兵测试验证边界。
- [OpenAlex search 召回明显大于本地匹配] → 将 search 结果视为候选集；零 Topic 匹配项既不调用 AI，也不持久化。
- [局部刷新误删其他 tab 数据] → Provider 选择和 SQLite 删除都使用同一个 `FeedItemType` 作用域，并以跨类型缓存保留测试覆盖。

## Migration Plan

1. 部署后端代码与可选 `OPENALEX_API_KEY` 环境配置。
2. 手动重启 API；News schema version 2 会创建 source slot 状态表，无需前端 secret 配置。
3. 手动调用 News refresh，将现有 News cache 对账为 D2NN、Optical Computing 与 Metasurface 匹配并集，再从 Papers tab 或 Feed API 验证真实 `source=openalex` 条目。
4. 回滚时恢复此前 composition；已有 OpenAlex feed rows 可留在相同 schema 中，不影响 Demo 或未来 provider。

## Open Questions

- None for this change. 每 Topic 数量和 7 天窗口保持 provider 常量，后续只有出现实际噪声/覆盖证据时再单独配置化。
