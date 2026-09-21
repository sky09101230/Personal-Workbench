# Literature V2 Backend Workflows — 上下文握手文档 (Context Handshake Document)

> **生成时间**: 2026-09-21 21:59 (Local)  
> **当前分支**: `claude/literature-v2-backend-workflows`  
> **基线分支**: `codex/literature-v2-canonical-library`  
> **目标范围**: Stage 1（Canonical backend hardening + API contract freeze）+ Stage 2（PLAB-style Literature workflow backend）  
> **禁止项**: 不做前端 UI、不重构非关联基础设施、不合并 main / codex 分支。

---

## 一、当前代码库状态与文件清单

### 1.1 Git 状态摘要 (`git status -s`)

```text
 M apps/api/app/modules/literature/application/ports.py
 M apps/api/app/modules/literature/domain/models.py
 M apps/api/app/modules/literature/infrastructure/cache/canonical.py
 M apps/api/app/modules/literature/infrastructure/files.py
 M apps/api/app/modules/literature/presentation/library_router.py
?? apps/api/app/modules/literature/application/extraction.py
?? apps/api/app/modules/literature/application/materialization.py
?? apps/api/app/modules/literature/application/review.py
?? apps/api/app/modules/literature/application/upload.py
?? apps/api/app/modules/literature/application/zotero_import.py
?? apps/api/app/modules/literature/domain/workflow.py
?? apps/api/app/modules/literature/presentation/review_router.py
?? apps/api/app/modules/literature/presentation/upload_router.py
```

---

## 二、已完成的实现进展 (Work Completed)

### 2.1 Stage 1: Canonical Backend Hardening
1. **Source / Origin 解耦 (§1.1)**
   - 修改 [models.py](file:///D:/PythonProject/Workbench/Personal-Workbench/apps/api/app/modules/literature/domain/models.py): `Paper` 增加 `origins: tuple[str, ...] = ()` 字段。
   - 修改 [canonical.py](file:///D:/PythonProject/Workbench/Personal-Workbench/apps/api/app/modules/literature/infrastructure/cache/canonical.py): `_read_paper()` 彻底解耦 `sources`（仅来自 `literature_source_references`，如 `zotero`）与 `origins`（来自 `literature_origins`，如 `radar`, `manual_pdf`, `zotero_import`）。
2. **Reading Status 迁移语义修复 (§1.2)**
   - 修改 [canonical.py](file:///D:/PythonProject/Workbench/Personal-Workbench/apps/api/app/modules/literature/infrastructure/cache/canonical.py): `_migrate()` 后将历史导入的存量文献由默认 `inbox` 批量置为 `saved`；新增 `reconcile_reading_status()` 供已迁移 DB 进行幂等校正。
   - 修改 [library_router.py](file:///D:/PythonProject/Workbench/Personal-Workbench/apps/api/app/modules/literature/presentation/library_router.py): 增加 `POST /api/literature/migration/reconcile-reading-status`。
3. **Canonical 迁移生命周期解耦 (§1.3)**
   - 修改 [canonical.py](file:///D:/PythonProject/Workbench/Personal-Workbench/apps/api/app/modules/literature/infrastructure/cache/canonical.py): `ensure_schema()` 剥离重型数据迁移，仅做 DDL 建表。若存量数据库未迁移，设置 `_migration_pending=True`，读取接口通过 `_require_canonical()` 抛出 `MigrationRequiredError`，杜绝任何 `GET` 请求隐式触发数据迁移。
   - 新增 `run_migration(dry_run=...)` 方法与 `migration_required` 属性。
   - 修改 [library_router.py](file:///D:/PythonProject/Workbench/Personal-Workbench/apps/api/app/modules/literature/presentation/library_router.py): 新增 `GET /api/literature/migration/status` 与 `POST /api/literature/migration/run` 路由。
4. **Local 文件生命周期加固 (§1.4)**
   - 修改 [files.py](file:///D:/PythonProject/Workbench/Personal-Workbench/apps/api/app/modules/literature/infrastructure/files.py): 划分 `staging/` 与 `originals/` 目录结构。实现 `stage_pdf()` (原子写入 `.pending`)、`finalize_pdf()` (硬链接并移除 staging)、`cleanup_staging()`。保持对旧 `data/literature-assets/` 的双向兼容回退。
   - 修改 [ports.py](file:///D:/PythonProject/Workbench/Personal-Workbench/apps/api/app/modules/literature/application/ports.py): `LiteratureFileStore` 协议补充 `stage_pdf` 与 `finalize_pdf`。

### 2.2 Stage 2: PLAB-style Literature Workflow Backend
1. **工作流领域模型 [workflow.py](file:///D:/PythonProject/Workbench/Personal-Workbench/apps/api/app/modules/literature/domain/workflow.py)**
   - 定义 `ExtractedField`, `ExtractedMetadata`, `UploadItem`, `UploadBatch`, `MetadataProposal`, `MaterializationResult`, `BatchMaterializationResult` 等全部 frozen dataclass 模型。
2. **Schema 扩展与数据表定义**
   - 修改 [canonical.py](file:///D:/PythonProject/Workbench/Personal-Workbench/apps/api/app/modules/literature/infrastructure/cache/canonical.py): `_SCHEMA` 新增 `literature_upload_batches`, `literature_upload_items`, `literature_metadata_proposals` 及其关联索引。
3. **PDF 元数据轻量提取服务 [extraction.py](file:///D:/PythonProject/Workbench/Personal-Workbench/apps/api/app/modules/literature/application/extraction.py)**
   - 实现 `extract_metadata(data: bytes)`：利用 `pypdf` 提取 PDF info（title, authors, year）、首三页 DOI / arXiv 正则匹配与归一化、首页标题回退，提供 confidence 与 warnings 结构。
4. **上传与评审工作流服务 [upload.py](file:///D:/PythonProject/Workbench/Personal-Workbench/apps/api/app/modules/literature/application/upload.py) & 路由 [upload_router.py](file:///D:/PythonProject/Workbench/Personal-Workbench/apps/api/app/modules/literature/presentation/upload_router.py)**
   - `UploadWorkflowService`：批次创建 (`create_batch`)、暂存并提取 (`stage_file`)、元数据补全/修改 (`update_item_metadata`)、确认入库 (`confirm_batch` 原子转存入 canonical document)、取消与孤儿文件清理 (`cancel_batch`, `cancel_item`)。
   - `upload_router`：提供 `/uploads/batches/*` 的完整 REST API。
5. **元数据修订提案服务 [review.py](file:///D:/PythonProject/Workbench/Personal-Workbench/apps/api/app/modules/literature/application/review.py) & 路由 [review_router.py](file:///D:/PythonProject/Workbench/Personal-Workbench/apps/api/app/modules/literature/presentation/review_router.py)**
   - `MetadataReviewService`：创建提案 (`create_proposal`，校验 formal DOI 冲突)、采纳 (`accept_proposal`)、驳回 (`reject_proposal`)、编辑后采纳 (`edit_and_accept`)，全量保留 provenance 审计轨迹。
   - `review_router`：提供 `/papers/{id}/metadata/proposals` 及相关端点。
6. **Zotero 选择性导入服务 [zotero_import.py](file:///D:/PythonProject/Workbench/Personal-Workbench/apps/api/app/modules/literature/application/zotero_import.py)**
   - `ZoteroImportService`：按条目选择导入 (`import_selected`)，独立建档、去重合并并绑定 `zotero_selective` origin，设置状态为 `saved`。
   - [library_router.py](file:///D:/PythonProject/Workbench/Personal-Workbench/apps/api/app/modules/literature/presentation/library_router.py) 增加 `/imports/zotero/collections`, `/imports/zotero/items`, `/imports/zotero/selective` 端点。
7. **Zotero PDF 本地物化服务 [materialization.py](file:///D:/PythonProject/Workbench/Personal-Workbench/apps/api/app/modules/literature/application/materialization.py)**
   - `PdfMaterializationService`：单篇物化 (`materialize_paper`)、受限批量物化 (`materialize_batch`)。流式下载 Zotero 附件至 local content-addressed 存储并绑定 canonical asset。
   - [library_router.py](file:///D:/PythonProject/Workbench/Personal-Workbench/apps/api/app/modules/literature/presentation/library_router.py) 增加 `/papers/{id}/materialize-pdf`, `/papers/materialize-pdfs` 端点。

---

## 三、待接续的工作项 (Pending Tasks)

1. **`apps/api/app/main.py` 依赖注入与路由装配**
   - 实例化 `UploadWorkflowService`, `MetadataReviewService`, `ZoteroImportService`, `PdfMaterializationService`。
   - 挂载 `upload_router` (prefix `/api/literature`) 与 `review_router` (prefix `/api/literature`)。
2. **测试集兼容性调整与修复**
   - 运行测试 `pytest apps/api/tests` 时，当前存量测试中有 5 个关于 legacy migration 的测试失败：
     - 原因：由于我们将 `ensure_schema()` 改成了 DDL-only（不再在 read 时隐式自动跑数据迁移），旧测试中直接初始化 `SQLiteCanonicalRepository` 并调用 `get_paper()` / `list_papers()` 的用例没有先调用 `run_migration()`。
     - 需兼容处理：在单测或迁移逻辑中，保持测试代码或迁移引导的兼容性（例如旧测试显式补上 `repo.run_migration()`，或保留对旧测试场景的适配）。
3. **新增测试套件 (`apps/api/tests/test_literature_workflows.py`)**
   - 覆盖 Stage 1：source/origin 分离验证、reading-status 校正、explicit migration 防护、staging/finalize 生命周期、孤儿文件清理。
   - 覆盖 Stage 2：批量上传工作流、PDF 元数据提取、元数据提案采纳/驳回/修改、Zotero 选择性导入、PDF 物化与历史批量物化、DOI 冲突拦截。
4. **API 规范冻结文档 (`docs/contracts/literature-v2-api.md`)**
   - 编写完整的 REST API Contract（涵盖 A: 文献列表与详情、B: 原生分类与状态、C: PDF 与附件访问、D: 上传工作流、E: Zotero 导入与物化、F: 元数据评审、G: 迁移控制）。
5. **OpenSpec 状态重开与更新**
   - `openspec/changes/upgrade-literature-canonical-library-v2/`：将 tasks.md 中已交付的第一阶段重新审视，追加 Stage 1/2 任务并同步规格规范。
6. **最终检查与提交**
   - 运行 pytest 全绿、compileall、git diff --check、敏感信息检查、git commit & push 到 `origin/claude/literature-v2-backend-workflows`。

---

## 四、关键代码决策与技术注意事项 (Gotchas & Design Notes)

1. **`ensure_schema()` 与 `_require_canonical()`**
   - 当前在 `canonical.py` 中，如果库中已存在 `literature_papers`（即老 Zotero 库）且尚未跑 canonical migration，`ensure_schema()` 会建表但置 `_migration_pending = True`。
   - `_require_canonical()` 会抛出 `MigrationRequiredError`。
   - **注意**：部分老用例直接针对老数据库做读取断言。若需向后兼容自动化脚本，应确保在执行读取前有明确的 `run_migration()` 触发点。
2. **`Paper.sources` vs `Paper.origins`**
   - `sources` 仅限真实 external reference providers（如 `zotero`, `openalex`）。
   - `origins` 包含发现渠道（如 `radar`, `manual_pdf`, `zotero_import`, `zotero_selective`）。
3. **文件存储路径结构**
   - 原 `data/literature-assets/` 作为只读 fallback。
   - 新增入库的 PDF 统一存放于 `data/literature-assets/originals/{sha256}.pdf`，中间暂存文件为 `data/literature-assets/staging/{uuid}.pending`。
4. **PowerShell 环境注意事项**
   - 系统为 Windows PowerShell，多命令链接切勿使用 `&&`，必须使用 `;` 或分行执行。
   - 测试执行推荐命令：
     ```powershell
     .\.venv\Scripts\python.exe -m pytest -q apps\api\tests --basetemp .venv\tmp\pytest -p no:cacheprovider
     ```
