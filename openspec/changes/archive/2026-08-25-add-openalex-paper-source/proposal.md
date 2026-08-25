## Why

News 目前只有确定性的 Demo Provider，无法完成“发现近期真实论文”的核心用途。OpenAlex Works API 能以一个受控、可测试的真实来源验证现有 Provider → Topic Match → SQLite → Feed 流水线，而无需扩展为通用学术搜索或同时引入多个来源。

## What Changes

- 新增后端 `OpenAlexPaperProvider`，将 OpenAlex Works 规范化为现有 `FeedItem(type=paper)`。
- Refresh 使用当前 News Topics 的正向关键词查询最近 7 天的论文，每个 Topic 仅抓取一页有限结果，并在现有 Topic Match 前按 OpenAlex work id 去重。
- 对 timeout、429、401/403、服务不可用和畸形响应返回现有稳定 `NewsSourceError`，失败时不触碰既有 SQLite Feed。
- 增加可选后端 `OPENALEX_API_KEY` 配置；配置后每次请求必须携带，未配置时允许公共基础访问。
- production composition 默认注册 OpenAlex；保留 Demo Provider 供测试与显式开发使用。
- production Topics 包含 `Diffractive Neural Networks`、`Optical Computing` 与精确关键词驱动的 `Metasurface`。
- OpenAlex 返回值先作为候选集；只有最终命中至少一个 Topic 的去重并集进入 AI 摘要、SQLite 与 All topics Feed。
- OpenAlex 在 Asia/Shanghai 的每个自然日 AM/PM 时段、每份 Topic 查询配置最多成功抓取一次；同槽且配置未变时复用 SQLite Feed，失败不占用时段。
- 成功 refresh 将 News Feed 对账为当前快照，清除旧 Topic 和不在本次结果中的残留 News 条目，同时不触碰共享数据库中的 Literature 数据。
- 现有 Papers tab 继续消费不变的 Feed API，并低调显示作者、日期、venue、DOI、Topic 与引用数等已有 metadata。
- News 页面移除跨类型 `All` tab；每个类型 tab 提供自己的刷新按钮，并只调用声明支持该类型的 Provider、只对账该类型的缓存；Topic 筛选只在 Papers tab 显示和生效。

## Capabilities

### New Capabilities

- `openalex-paper-source`: OpenAlex 近期论文 discovery、标准化映射、查询约束、去重、错误边界和 Papers Feed 呈现。

### Modified Capabilities

- None.

## Impact

- Backend: News source port/service、OpenAlex provider、composition root、Settings 与 `.env.example`。
- Frontend: 扩展现有 `FeedCard` 对 paper metadata 的呈现，并将刷新控制放入当前类型 tab 的控制栏。
- Storage/API: `/api/news/feed` 不变；`/api/news/refresh` 增加可选 `type` query；News SQLite 增加 source refresh slot 状态表，不增加 provider-specific FeedItem 顶层字段。
- Dependencies: 复用已安装的 `httpx`；不增加 arXiv、Crossref、Semantic Scholar、AI、PDF 或后台任务依赖。
