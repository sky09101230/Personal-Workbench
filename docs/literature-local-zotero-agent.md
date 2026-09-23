# 本机 Zotero 代理

本机代理用于从存有 PDF 的电脑恢复已有 Literature 来源。它只读取 Zotero，不写 Zotero 数据库，也不读取任意路径。

## 启动

在存有 PDF 的电脑上打开 PowerShell，从 Workbench 发布目录运行：

```powershell
python apps/zotero-agent/agent.py `
  --zotero-dir 'C:/Users/<用户名>/Zotero' `
  --origin 'https://desktop-itv0kct.tailbfd988.ts.net'
```

代理会显示一次性配对码，有效 5 分钟。Workbench 页面输入配对码后，会话最长 30 分钟；关闭代理会立即撤销会话。

## 页面操作

在 Literature 的“导入”页选择“当前电脑 Zotero（本机代理）”，连接代理后选择条目并导入。已有文献也可以在“文件”页打开“从当前电脑的 Zotero 补充 PDF”，逐个恢复附件。

当前浏览器中转限制为每个 PDF 50 MiB。代理只绑定 `127.0.0.1`，要求页面 Origin 与启动参数完全一致。浏览器拒绝本地访问、附件不存在、链接文件或来源发生变化时，页面会分别报告原因；这些情况不会把来源误标为已拥有。

恢复成功后，Workbench 会独立计算 PDF 的 SHA-256、校验 PDF 结构，并将副本保存到 Vault。它保留原论文、Zotero 来源键、角色、笔记和其他关联；重复恢复会复用已有副本。

不要把 Zotero 数据库复制到服务器，也不要把 `--zotero-dir` 指向任意共享目录。无法使用代理时，可在文献文件页用“上传 PDF”走人工替代版本流程。
