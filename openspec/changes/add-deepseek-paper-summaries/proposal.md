## Why

OpenAlex abstract 直接显示在 FeedCard 中过长，降低 Papers Feed 的扫读效率。现在需要一个后端 AI 摘要步骤，把论文摘要压缩为简洁中文要点，同时让未配置或暂时不可用的 DeepSeek 不影响真实论文刷新。

## What Changes

- 新增 DeepSeek paper summarizer，通过官方 Chat Completions API 将 paper abstract 转换为 2–3 句简洁中文摘要。
- 增加仅后端可见的 `DEEPSEEK_API_KEY`、base URL 与 model 配置；默认使用 `deepseek-v4-flash`，Key 不进入前端或 Feed metadata。
- 在 Topic Match 完成后、SQLite 写入前替换 paper `FeedItem.summary`，保持匹配依据来自原始 OpenAlex 内容。
- DeepSeek 未配置、timeout、认证失败、限流、不可用或响应畸形时保留原摘要并继续 refresh。
- 限制 FeedCard 摘要显示行数，避免历史 cache 或降级摘要继续撑高卡片。

## Capabilities

### New Capabilities

- `deepseek-paper-summaries`: DeepSeek 后端摘要配置、生成时机、降级边界、数据安全与 FeedCard 呈现。

### Modified Capabilities

- None.

## Impact

- Backend: Settings、News application port/service、DeepSeek summarizer adapter、composition root 与 mocked HTTP tests。
- Frontend: 仅调整现有 `FeedCard` summary 的语义标记和行数限制。
- Storage/API: 复用现有 `FeedItem.summary` 与 SQLite/API schema，无 migration、无新 endpoint。
- External system: DeepSeek `POST /chat/completions`；不新增 OpenAI SDK，复用 `httpx`。
