# Personal Workbench

Personal Workbench 是一个面向个人科研流程的本地工作台。当前版本提供 Literature 模块：通过后端连接 Zotero Web API v3，在浏览器中浏览文献集合、论文列表与元数据，并使用 SQLite 保存可增量更新的本地元数据缓存。

## 当前功能

- React 工作台界面：集合树、论文列表、作者/期刊/年份/DOI/标签详情。
- Zotero 只读接入：凭据仅保留在 FastAPI 后端，不发送到浏览器。
- 本地 SQLite 缓存：首次同步保存完整快照，后续同步按 Zotero library version 增量合并更新和删除。
- 缓存优先读取：完成首次同步后，集合和论文查询直接读取本地缓存。
- 明确的连接状态和错误反馈：未配置凭据、鉴权失败和上游不可用均由 Workbench API 统一返回。

> 当前边界：PDF 阅读和笔记按钮仅为界面占位，尚不可用；Web 界面的“Refresh”会重新读取当前数据，但不会触发 `POST /api/literature/sync`。

## News Framework

- 独立模块入口：/news 提供 All、Papers、GitHub、Skills、AI News 与 X tabs，以及 Topic filter。
- 统一 Feed：五类未来来源都映射为 Provider 无关的 FeedItem，API 和页面不接收来源私有响应。
- 插件式来源：NewsSourcePort 允许 Provider 逐个注册；本轮仅有不访问外网的 demo provider。
- 显式刷新：POST /api/news/refresh 执行 Provider -> Normalize -> Topic Match -> Feed，页面不会启动后台任务。
- 独立缓存：news_* 表保存 Feed metadata、Topic 匹配和 read/saved/hidden 状态，不读取 literature_* 表，也不保存网页全文。

真实 Papers、GitHub、GitHub Skills、AI News 与 X Provider，以及 AI ranking、summary、Embedding、RAG、推荐、Digest 和定时任务均属于后续 change。

## 技术栈

- Backend: Python、FastAPI、HTTPX、SQLite
- Frontend: React 19、TypeScript、Vite 7
- Tests: pytest

## 项目结构

```text
apps/
├── api/
│   ├── app/core/                       # 配置等共享基础设施
│   ├── app/modules/literature/
│   │   ├── domain/                     # 通用文献领域模型
│   │   ├── application/                # 用例、端口与同步逻辑
│   │   ├── infrastructure/
│   │   │   ├── cache/                  # SQLite 元数据缓存
│   │   │   └── providers/zotero/       # Zotero Web API v3 适配器
│   │   └── presentation/               # FastAPI 路由
│   ├── app/modules/news/
│   │   ├── domain/
│   │   ├── application/
│   │   ├── infrastructure/cache/
│   │   ├── infrastructure/providers/demo/
│   │   └── presentation/
│   └── tests/
└── web/
    └── src/
        ├── app/                         # 应用组合
        ├── core/                        # 工作台外壳与模块注册
        ├── modules/literature/          # Literature 界面
        └── modules/news/                # News framework 界面
```

浏览器只调用 `/api/literature/*` 和 `/api/news/*`；Zotero URL、请求 Header 和 API Key 只存在于 Literature 的后端 provider。News 不依赖 Zotero。

## 本地运行

### 1. 准备环境

需要 Windows、Python 3.10+、Node.js（满足 Vite 7 的运行要求）和 npm。

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r apps\api\requirements.txt
npm.cmd --prefix apps\web install
Copy-Item .env.example .env
```

编辑 `.env`，填写 Zotero 凭据：

```dotenv
DATABASE_URL=sqlite:///./data/workbench.db
CORS_ORIGINS=http://localhost:5173
ZOTERO_USER_ID=你的数字用户 ID
ZOTERO_API_KEY=你的 API Key
```

`ZOTERO_USER_ID` 是 Zotero API Keys 页面显示的数字 user ID，不是用户名。`.env` 已被 Git 忽略，请勿提交凭据。

### 2. 启动服务

最简方式是在仓库根目录双击 `start-workbench.cmd`。脚本会在 Windows Terminal 中分别启动 API 和 Web，并打开 `http://localhost:5173`。

也可以在两个 PowerShell 窗口中手动运行：

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir apps\api --reload --env-file .env
```

```powershell
npm.cmd --prefix apps\web run dev -- --open
```

- Web: `http://localhost:5173`
- API: `http://localhost:8000`
- API 文档: `http://localhost:8000/docs`

Vite 会把浏览器发出的 `/api` 请求代理到 `http://localhost:8000`。

## 同步 Zotero

服务启动后，在另一个 PowerShell 窗口执行：

```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/literature/sync
```

- 本地还没有同步状态时执行完整同步。
- 已保存 `library_version` 时执行增量同步。
- 同步失败时保留上一份可读缓存，并将同步状态标记为失败。

不执行同步也可以浏览 Zotero：当本地缓存为空时，查询会回退到 Zotero Web API 的实时只读请求。

News framework 只支持手动刷新 demo feed：

~~~powershell
Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/news/refresh
~~~

## API

| Method | Path | 说明 |
| --- | --- | --- |
| `GET` | `/api/health` | API 健康检查 |
| `GET` | `/api/literature/status` | Provider 配置与同步状态 |
| `POST` | `/api/literature/sync` | 执行首次或增量同步 |
| `GET` | `/api/literature/collections` | 获取集合列表 |
| `GET` | `/api/literature/papers?collection_id=<opaque-id>&limit=50&offset=0` | 分页获取论文 |
| `GET` | `/api/news/feed` | 分页读取缓存 Feed；参数为 type、topic、limit、offset |
| `GET` | `/api/news/topics` | 读取当前简单 Topic 配置 |
| `POST` | `/api/news/refresh` | 通过已注册 Provider 刷新 News cache；本轮仅 demo provider |

`collection_id` 是 Workbench 返回的不透明标识，请勿自行拼接。

## 验证

运行后端测试：

```powershell
.\.venv\Scripts\python.exe -m pytest -q apps\api\tests --basetemp .venv\tmp\pytest -p no:cacheprovider
```

验证前端生产构建：

```powershell
npm.cmd --prefix apps\web run build
git diff --check
```

## 安全说明

- Zotero API Key 仅通过后端环境变量读取。
- `.env`、SQLite 数据库、虚拟环境、依赖目录和构建输出不会提交到 Git。
- 当前 Zotero Provider 只实现读取与同步，不会修改 Zotero 云端文献库。
- News SQLite 只保存 Feed metadata、Topic 匹配和用户状态，不保存网页全文，也不直接访问 Literature 内部表。
