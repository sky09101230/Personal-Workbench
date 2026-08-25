## 1. News 核心边界

- [x] 1.1 建立 `apps/api/app/modules/news/` 分层目录，定义 `FeedItem`、类型、Topic、分页与刷新结果领域模型。
- [x] 1.2 定义 `NewsSourcePort` 与 News repository port，并实现 Provider 集合驱动的 refresh、简单 Topic Match 和缓存 Feed 查询 service。

## 2. SQLite 与 Demo Provider

- [x] 2.1 实现 News 独立 SQLite schema/migration，以及 Feed metadata、Topic 匹配、用户状态的事务写入和筛选读取。
- [x] 2.2 实现返回标准化示例项的极简 demo provider，用于验证 port 和统一 Feed，不接入真实外部来源。

## 3. API 与组合

- [x] 3.1 实现 `/api/news/feed`、`/api/news/topics`、`/api/news/refresh`，包含参数验证和稳定错误响应。
- [x] 3.2 在 `app/main.py` 组合并注册 News repository、demo provider、service 和 router，保持 Literature 组合不变。

## 4. 前端模块壳

- [x] 4.1 将 News 注册到 Workbench，并增加不依赖路由库的独立 `/news` 模块入口和正确导航状态。
- [x] 4.2 实现类型 tabs、Topic filter、统一 Feed Card、手动刷新，以及 loading、empty、error 状态。

## 5. 验证与文档

- [x] 5.1 补充领域/service、SQLite 和 API 测试，覆盖 refresh、Topic 匹配、类型/Topic 分页筛选、状态保留与失败不部分写入。
- [x] 5.2 更新 README 的模块结构/API/范围说明，并运行完整 pytest、前端 production build、OpenSpec validation 和 `git diff --check`。
  - 原 `.venv\tmp\pytest` 因 Windows ACL 异常不可用；验收改用新的 repo-local `.venv\tmp\pytest-news-validation`。测试范围与其余 pytest 参数未变，结果为 35 passed；前端 build、OpenSpec strict validation 和 `git diff --check` 均通过。
