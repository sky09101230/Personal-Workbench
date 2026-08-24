# Personal Workbench

Personal Workbench 是一个面向个人科研流程的本地工作台。当前包含 Literature V0.1 与 News framework：Literature 面向进入个人文库后的长期浏览和阅读，News 面向外部信息的发现、筛选与浏览，两者保持独立领域边界。

## Literature V0.1

- 三栏文库：首页包含 Collections、分页论文列表和详情区域。
- 缓存搜索与筛选：支持标题/作者搜索，以及年份、Journal / Venue、Tags、Collection 筛选。
- 完整详情：显示 Title、Authors、Abstract、Year、Journal / Venue、DOI、Tags 与所属 Collections。
- Zotero Notes：同步 item Notes 和可映射到论文的 PDF annotation metadata，只读展示，不在 Workbench 创建或编辑 Note。
- Attachments：区分可读取的 Zotero 存储 PDF、linked file、非 PDF 和 provider 当前无法访问的附件。
- PDF Reader：独立 `/literature/papers/:id/reader` 页面，使用 PDF.js，支持翻页、页码跳转、缩放、页面适配和下载，并提供可开关的只读 Notes 侧栏。
- 手动同步：页面显示最后同步时间和 syncing/success/failed 状态；失败时继续读取上一份 SQLite cache。

不在 Literature V0.1 范围内：全文 PDF 搜索、AI/RAG/Embedding、知识图谱、推荐、自定义 PDF 批注编辑、多用户权限和后台定时同步。

## News Framework

- 独立模块入口：/news 提供 All、Papers、GitHub、Skills、AI News 与 X tabs，以及 Topic filter。
- 统一 Feed：五类未来来源都映射为 Provider 无关的 FeedItem，API 和页面不接收来源私有响应。
- 插件式来源：NewsSourcePort 允许 Provider 逐个注册；本轮仅有不访问外网的 demo provider。
- 显式刷新：POST /api/news/refresh 执行 Provider -> Normalize -> Topic Match -> Feed，页面不会启动后台任务。
- 独立缓存：news_* 表保存 Feed metadata、Topic 匹配和 read/saved/hidden 状态，不读取 literature_* 表，也不保存网页全文。

真实 Papers、GitHub、GitHub Skills、AI News 与 X Provider，以及 AI ranking、summary、Embedding、RAG、推荐、Digest 和定时任务均属于后续 change。

## 技术栈与结构

- Backend：Python、FastAPI、HTTPX、SQLite
- Frontend：React 19、TypeScript、Vite 7、PDF.js
- Tests：pytest

```text
apps/
├── api/
│   ├── app/core/
│   ├── app/modules/literature/
│   │   ├── domain/
│   │   ├── application/
│   │   ├── infrastructure/cache/
│   │   ├── infrastructure/providers/zotero/
│   │   └── presentation/
│   ├── app/modules/news/
│   │   ├── domain/
│   │   ├── application/
│   │   ├── infrastructure/cache/
│   │   ├── infrastructure/providers/demo/
│   │   └── presentation/
│   └── tests/
└── web/src/
    ├── app/
    ├── core/
    ├── modules/literature/
    └── modules/news/
```

浏览器只调用 /api/literature/* 和 /api/news/*；Zotero URL、请求 Header 和 API Key 只存在于 Literature 的后端 provider。News 不依赖 Zotero。

## 本地运行

需要 Windows、Python 3.10+、Node.js 和 npm。

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r apps\api\requirements.txt
npm.cmd --prefix apps\web install
Copy-Item .env.example .env
```

在 `.env` 中配置：

```dotenv
DATABASE_URL=sqlite:///./data/workbench.db
CORS_ORIGINS=http://localhost:5173
ZOTERO_USER_ID=你的数字用户 ID
ZOTERO_API_KEY=具有目标个人文库读取权限的 API Key
```

`ZOTERO_USER_ID` 是 Zotero API Keys 页面显示的数字 user ID，不是用户名。`.env` 已被 Git 忽略，不要提交凭据。

在两个 PowerShell 窗口分别运行：

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir apps\api --reload --env-file .env
```

```powershell
npm.cmd --prefix apps\web run dev -- --open
```

也可以在仓库根目录双击 `start-workbench.cmd`。Web 默认位于 `http://localhost:5173`，API 位于 `http://localhost:8000`，Vite 将 `/api` 代理到后端。

## 同步行为

在 Literature 页点击 **Sync Zotero**：

- 新数据库或 schema v2 升级后的第一次同步执行 full sync，分页读取 Collections、顶层文献和 Note/Attachment/annotation 子项，并在同一 SQLite 事务中替换 metadata 快照。
- 后续同步使用保存的 Zotero `library_version` 请求增量变更和删除记录。
- 同步成功后页面重新加载当前 Collections、筛选项、论文和详情。
- 同步失败时状态标为 failed，但上一份 Papers/Collections/Notes/Attachment metadata cache 保持可读。

也可以直接调用：

```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/literature/sync
```


News framework 只支持手动刷新 demo feed：

```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/news/refresh
```

## API

| Method | Path | 说明 |
| --- | --- | --- |
| `GET` | `/api/health` | API 健康检查 |
| `GET` | `/api/literature/status` | Provider 配置、同步状态、最后同步时间和 library version |
| `POST` | `/api/literature/sync` | 执行 full 或 incremental sync |
| `GET` | `/api/literature/collections` | 读取缓存 Collections |
| `GET` | `/api/literature/filters` | 读取缓存年份、Journal / Venue 和 Tags 选项 |
| `GET` | `/api/literature/papers` | 分页搜索/筛选缓存论文；参数为 `query`、`author`、`year`、`journal`、`tag`、`collection_id`、`limit`、`offset` |
| `GET` | `/api/literature/papers/{id}` | 读取论文详情、所属 Collections 和 PDF availability |
| `GET` | `/api/literature/papers/{id}/notes` | 读取同步后的只读 Notes/annotation metadata |
| `GET` | `/api/literature/papers/{id}/attachments` | 读取 Attachment metadata 和 availability |
| `GET` | `/api/literature/papers/{id}/pdf` | 后端保护的 PDF stream，支持 Range 请求 |
| `GET` | `/api/literature/papers/{id}/pdf/download` | 下载 PDF |
| `GET` | `/api/news/feed` | 分页读取缓存 Feed；参数为 type、topic、limit、offset |
| `GET` | `/api/news/topics` | 读取当前简单 Topic 配置 |
| `POST` | `/api/news/refresh` | 通过已注册 Provider 刷新 News cache；本轮仅 demo provider |

所有 Literature id、collection_id 与 News FeedItem.id 都是 Workbench 返回的不透明标识，不要自行拼接。

## PDF 可用性限制

- `imported_file` / `imported_url` 且 `contentType=application/pdf` 的 Zotero 存储附件可尝试通过 Web API `/file` 读取。
- `linked_file` 指向运行 Zotero Desktop 的本地路径，Zotero Web API 不提供该文件，Workbench 会明确显示不可用。
- 使用 WebDAV 同步时，附件 metadata 可能存在，但最新 binary 只在 WebDAV；若 Zotero `/file` 无法返回文件，Reader/下载会显示 `pdf_unavailable`。
- PDF binary 按需从 Zotero 代理，不写入 SQLite；浏览器不会接触 Zotero API Key。

## 验证

```powershell
.\.venv\Scripts\python.exe -m pytest -q apps\api\tests --basetemp .venv\tmp\pytest -p no:cacheprovider
npm.cmd --prefix apps\web run build
git diff --check
```

后端测试覆盖 Literature cache/sync/PDF 边界，以及 News service、独立 schema、Topic 匹配、筛选和 API。前端当前没有测试 runner；production build 只验证类型和打包，不等同于浏览器交互测试。

## 安全边界

- `.env`、Zotero credentials、SQLite 数据库、虚拟环境、依赖目录和 build 输出不得提交。
- Provider 只读访问 Zotero；Workbench V0.1 不创建或修改 Zotero 文献、Notes、annotations 或附件。
- Literature SQLite 只保存 metadata 与 Note 内容，不保存 PDF binary，也不是第二套文献 source of truth。
- News SQLite 只保存 Feed metadata、Topic 匹配和用户状态，不保存网页全文，也不直接访问 Literature 内部表。
