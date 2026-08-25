## Context

News refresh 当前先由 Provider 生成标准化 `FeedItem`，再由 `NewsService` 做 Topic Match，最后事务性写入 SQLite。OpenAlex 将完整 abstract 放入 `FeedItem.summary`，因此 FeedCard 会显示很长的原文。DeepSeek 是一个独立外部依赖；它不能获得前端环境、API key 或超出标题和摘要的本地数据，也不能让摘要失败破坏真实论文刷新。

## Goals / Non-Goals

**Goals:**

- 对通过现有 Topic Match 的 paper 生成 2–3 句简洁中文摘要。
- 使用 DeepSeek 官方 `/chat/completions`，默认 `deepseek-v4-flash`、非 thinking 模式，并允许后端环境变量覆盖 model/base URL。
- 用一次 bounded batch request 摘要本次 refresh 中的相关论文，限制每篇输入长度和输出长度。
- 在 DeepSeek 未配置或任何预期上游失败时保留原摘要并继续 SQLite refresh。
- 标记成功的 AI summary，并让 FeedCard 对 AI 或 fallback summary 都保持紧凑。

**Non-Goals:**

- 摘要历史 cache 的后台回填、定时任务、队列、流式输出或用户自定义 prompt。
- LLM ranking、recommendation、Topic Match、embedding、全文/PDF 摘要或通用聊天。
- 将 DeepSeek key、prompt、原始异常或 reasoning content 暴露到浏览器。
- 改变 Feed API/SQLite schema 或新增详情页。

## Decisions

### 1. 在 application service 的 Topic Match 后调用独立 summarizer port

新增最小 `NewsSummarizerPort.summarize(items)`。`NewsService` 仍用 OpenAlex 原始标题/abstract 完成 Topic Match，只将至少命中一个 Topic、类型为 paper 且有 summary 的 items 交给 summarizer；返回结果按稳定 id 合并后再写 SQLite。这样 AI 文本不会改变 discovery/匹配结果，也避免对未关联噪声论文付费。

备选是让 `OpenAlexPaperProvider` 直接调用 DeepSeek。该方案会混合两个外部系统的错误边界，并在最终 Topic Match 前摘要所有候选，因此不采用。

### 2. 单次 batch Chat Completions 请求

DeepSeek adapter 将本次相关 papers 组成一个 JSON 输入，每篇仅发送 id、title 与截断后的 abstract；system prompt 要求忽略 source text 中的指令，只基于给定内容生成简体中文、2–3 句、无 Markdown 的忠实摘要。请求使用 `response_format=json_object`、`thinking.type=disabled`、bounded `max_tokens`，响应按 id 校验后以 `dataclasses.replace` 更新 `FeedItem.summary`。

相比逐篇调用，batch 将每次 refresh 的网络往返压缩为一次，并保持当前每 Topic 小结果上限下的成本可控。部分响应缺失或无效时只保留对应 item 的原摘要。

### 3. DeepSeek 是 fail-open enrichment

未配置 `DEEPSEEK_API_KEY` 时 adapter 不发请求并原样返回。timeout、401/403、429、其他非成功状态、无效 JSON 或 response shape 不抛到 News source 边界，而是原样返回全部/对应 items。论文发现和 SQLite 事务仍由现有稳定路径完成。

成功摘要在现有 metadata 中写入通用 `summary_kind=ai` 与 `summary_provider=deepseek`，不添加顶层字段，也不保存 key、prompt 或原始 DeepSeek response。

### 4. 后端配置与前端呈现

Settings 增加 `DEEPSEEK_API_KEY`、`DEEPSEEK_BASE_URL`、`DEEPSEEK_MODEL`；默认 base URL 为 `https://api.deepseek.com`，默认 model 为 `deepseek-v4-flash`。composition 注入一个 `DeepSeekPaperSummarizer`，前端继续读取同一个 `summary`，成功时显示低调的 `AI summary` 标签，并用 CSS line clamp 限制摘要高度。历史 raw abstract 与降级内容因此也不会撑高卡片。

## Risks / Trade-offs

- [模型可能产生不准确摘要] → prompt 限定只用 title/abstract、禁猜测；保留原始论文链接，AI 标签明确来源。
- [batch 中一条恶意 abstract 试图 prompt injection] → system prompt 明确 source text 非指令，输入结构化为 JSON，且不提供 secrets 或本地上下文。
- [DeepSeek 失败不可见] → Feed 保持可用，成功项有 AI 标签；本轮不扩展 refresh API 状态，避免框架/API 变化。
- [历史 cache 仍含 raw abstract] → FeedCard 统一 line clamp；不做破坏性 cache 重写或后台回填。
- [模型名称随官方 API 更新] → model/base URL 可由后端环境变量覆盖。

## Migration Plan

1. 部署代码并在 `.env` 设置 `DEEPSEEK_API_KEY`；可选覆盖 base URL/model。
2. 手动重启 API 使环境变量生效；前端若已由 Vite 开发服务运行会加载样式变化。
3. 手动 refresh Papers；成功摘要写入现有 `summary`/`metadata_json`，无需 SQLite migration。
4. 回滚时移除 summarizer composition；已存 AI summary 仍符合现有 Feed schema。

## Open Questions

- None. 默认输出简体中文 2–3 句；后续若需要语言/长度偏好，单独配置化。
