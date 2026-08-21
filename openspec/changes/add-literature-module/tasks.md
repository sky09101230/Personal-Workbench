## 1. 已完成的模块基础

- [x] 1.1 建立 Workbench Shell、模块注册表、Literature 目录边界、环境配置与基础健康检查。
- [x] 1.2 定义 Provider 无关的 Literature 领域模型和 Provider port，并实现 Zotero Web API v3 的 Collections、顶层 Papers、分页、映射和错误转换。
- [x] 1.3 提供 `/api/literature/status`、`/collections`、`/papers`，并以 mocked HTTP 与 API 契约测试验证当前连接层。

## 2. SQLite Metadata Cache 与同步

- [x] 2.1 为 Papers、Collections、Tags、Notes、Attachment metadata、ExternalReference 和 library version 定义 SQLite schema 与迁移策略。
- [x] 2.2 实现首次手动 full sync：分页读取 Zotero 元数据并以事务写入 cache。
- [x] 2.3 实现 version-aware incremental sync、同步结果状态和 `POST /api/literature/sync`。
- [x] 2.4 将 Collections 与 Papers 读取 API 切换为 cache，并覆盖空 cache、同步失败和增量变更测试。

## 3. Library 浏览与 Notes

- [x] 3.0 将 Literature 前端接入现有 Collections/Papers API，实现真实文库加载、Collection 筛选、刷新和基础 Metadata 展示。搜索、Notes 与 PDF 操作仍待后续任务完成。
- [ ] 3.1 添加缓存文献的搜索、基础筛选、详情、Notes 和 Attachments API 契约与端点测试。
- [ ] 3.2 将 Literature 首页接入 Collections、分页文献列表、搜索、筛选和加载/空/错误状态。
- [ ] 3.3 实现三栏布局中的文献选择、详情面板、Notes 展示和可用 PDF 操作。

## 4. PDF 阅读

- [ ] 4.1 实现 PDF attachment 发现、受保护的 PDF stream/download API，以及不可访问附件的明确状态。
- [ ] 4.2 集成 PDF.js，创建独立 `/literature/papers/:id/reader` 页面和翻页、跳页、缩放、页面适配、下载控制。
- [ ] 4.3 为 Reader 添加可开关的只读 Notes/annotation metadata 侧栏，不实现自定义批注编辑器。

## 5. 验证与文档

- [ ] 5.1 补充 SQLite 同步、Notes、Attachment、PDF 和 API 错误边界的后端测试。
- [ ] 5.2 运行后端测试、前端 production build，并在配置真实 Zotero 凭据后手动验证同步、浏览与 PDF 流程。
- [ ] 5.3 更新 README，记录同步行为、PDF 可用性限制和用户侧的真实 Zotero 配置步骤。
