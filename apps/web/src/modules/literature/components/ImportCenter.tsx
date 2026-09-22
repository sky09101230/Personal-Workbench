import { literatureLabel } from "../labels";
import { useEffect, useState } from "react";
import { getJson, postJson, uploadPdf, workflowError } from "../api";
import { patchJson } from "../../../core/api";
import type { Collection, UploadBatch, UploadItem, WorkflowResult, ZoteroItem } from "../types";
import { MetadataForm, metadataText } from "./MetadataForm";

const batchStorage = "workbench.literature.upload-batch";
export function ImportCenter({ providerReady, onImported }: { providerReady: boolean; onImported: (id: string) => void }) {
  const [mode, setMode] = useState<"pdf" | "zotero">("pdf");
  return <div className="wb-import"><h2>导入到文献库</h2><p>审核 PDF 或选择外部连接器中的文献。保存后的文献与研究记录由 Workbench 管理。</p>
    <nav className="wb-subtabs" aria-label="导入方式"><button aria-pressed={mode === "pdf"} onClick={() => setMode("pdf")}>上传 PDF</button><button aria-pressed={mode === "zotero"} onClick={() => setMode("zotero")}>Zotero 连接器</button></nav>
    <div hidden={mode !== "pdf"}><PdfBatch onImported={onImported} /></div>
    {mode === "zotero" && <ZoteroImport providerReady={providerReady} onImported={onImported} />}
  </div>;
}

function PdfBatch({ onImported }: { onImported: (id: string) => void }) {
  const [batch, setBatch] = useState<UploadBatch | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [progress, setProgress] = useState("");
  const [editing, setEditing] = useState<string | null>(null);
  const [results, setResults] = useState<WorkflowResult[]>([]);
  const [recoverId, setRecoverId] = useState(() => localStorage.getItem(batchStorage));
  const remember = (value: UploadBatch) => { setBatch(value); localStorage.setItem(batchStorage, value.id); setRecoverId(value.id); };
  const refresh = async (id: string) => { remember(await getJson<UploadBatch>(`/api/literature/uploads/batches/${encodeURIComponent(id)}`)); };
  const perform = async (action: () => Promise<void>) => {
    setBusy(true); setError("");
    try { await action(); } catch (e) { setError(workflowError(e)); } finally { setBusy(false); setProgress(""); }
  };
  const stage = async (files: File[]) => {
    if (!files.length) return;
    await perform(async () => {
      if (files.length + (batch?.items.length ?? 0) > 50) throw new Error("一个批次最多包含 50 个 PDF。");
      if (files.some((file) => file.size > 50 * 1024 * 1024 || !file.name.toLowerCase().endsWith(".pdf"))) throw new Error("请选择 PDF 文件，每个不超过 50 MiB。");
      const current = batch ?? await postJson<UploadBatch>("/api/literature/uploads/batches");
      remember(current);
      const failures: string[] = [];
      for (const [index, file] of files.entries()) {
        setProgress(`正在暂存 ${index + 1}/${files.length}：${file.name}`);
        try { await uploadPdf<UploadItem>(`/api/literature/uploads/batches/${encodeURIComponent(current.id)}/files?${new URLSearchParams({ filename: file.name })}`, file); }
        catch (e) { failures.push(`${file.name}: ${workflowError(e)}`); }
      }
      await refresh(current.id);
      if (failures.length) setError(failures.join("\n"));
    });
  };
  const closed = batch?.status === "confirmed" || batch?.status === "cancelled";
  return <section><h3>1. 暂存 PDF → 2. 审核元数据 → 3. 确认入库</h3><p>确认前不会写入正式文献库。系统提取 PDF 元数据和前三页内容，请核对候选信息。</p>
    {!batch && recoverId && <p>有一个上传批次可继续处理。 <button disabled={busy} onClick={() => void perform(() => refresh(recoverId))}>继续暂存批次</button><button disabled={busy} onClick={() => { localStorage.removeItem(batchStorage); setRecoverId(null); }}>忽略恢复入口</button></p>}
    {!closed && <label className="wb-upload">选择 PDF · 最多 50 个文件，每个不超过 50 MiB<input aria-label="PDF 文件" type="file" accept="application/pdf,.pdf" multiple disabled={busy || (!!recoverId && !batch)} onChange={(e) => { const files = Array.from(e.target.files ?? []); e.target.value = ""; void stage(files); }} /></label>}
    {progress && <p role="status">{progress}</p>}{error && <p className="wb-error" role="alert">{error}</p>}
    {batch && <><div className="wb-section-heading"><h3>批次 · {literatureLabel(batch.status)}</h3><span>{batch.items.length} 个文件</span></div>
      {batch.items.map((item) => <article className="wb-review-item" key={item.id}><div className="wb-section-heading"><h4>{item.filename}</h4><span className="wb-badge">{literatureLabel(item.status)}</span></div>
        <p>{item.candidate_metadata.title || "需要填写标题"}</p>
        <dl>{Object.entries(item.candidate_metadata).filter(([field]) => field !== "title").map(([field, value]) => <div key={field}><dt>{literatureLabel(field)}</dt><dd>{metadataText(value) || "未记录"}</dd></div>)}</dl>
        {!!item.warnings.length && <details><summary className="wb-warning">提取提示 · {item.warnings.length}</summary><p>以下为原始提取时的提示；上方显示的是审核后的信息。</p>{item.warnings.map((warning, i) => <p className="wb-warning" key={i}>{literatureLabel(warning)}</p>)}</details>}{item.error && <p role="alert">{item.error}</p>}
        <details><summary>原始提取依据</summary><dl>{Object.entries(item.extracted_metadata).map(([field, evidence]) => <div key={field}><dt>{field}</dt><dd>{metadataText(evidence.value)} <small>· {literatureLabel(evidence.source)} · 置信度：{literatureLabel(evidence.confidence)}</small></dd></div>)}</dl></details>
        {!closed && !["confirmed", "cancelled"].includes(item.status) && <><div className="wb-actions"><button disabled={busy} onClick={() => setEditing(item.id)}>审核 / 编辑元数据</button><button disabled={busy} onClick={() => void perform(async () => { await postJson(`/api/literature/uploads/batches/${encodeURIComponent(batch.id)}/items/${encodeURIComponent(item.id)}/cancel`); await refresh(batch.id); })}>取消此文件</button></div>
          {editing === item.id && <MetadataForm key={`${item.id}-${JSON.stringify(item.candidate_metadata)}`} initial={item.candidate_metadata} busy={busy} onCancel={() => setEditing(null)} onSave={(patch) => void perform(async () => { await patchJson(`/api/literature/uploads/batches/${encodeURIComponent(batch.id)}/items/${encodeURIComponent(item.id)}`, patch); await refresh(batch.id); setEditing(null); })} />}</>}
        {item.target_paper_id && <button onClick={() => onImported(item.target_paper_id!)}>打开正式文献</button>}
      </article>)}
      <WorkflowResults results={results} onImported={onImported} />
      {!closed ? <div className="wb-actions"><button disabled={busy || editing !== null || !batch.items.some((item) => !["confirmed", "cancelled"].includes(item.status))} onClick={() => void perform(async () => {
        const response = await postJson<{ results: WorkflowResult[] }>(`/api/literature/uploads/batches/${encodeURIComponent(batch.id)}/confirm`); setResults(response.results); await refresh(batch.id);
      })}>确认审核并入库</button><button disabled={busy} onClick={() => void perform(async () => { remember(await postJson<UploadBatch>(`/api/literature/uploads/batches/${encodeURIComponent(batch.id)}/cancel`)); setEditing(null); })}>取消批次中未入库的文件</button><small>已入库的文件会保留。冲突项可修改后重试。</small></div> : <button onClick={() => { setBatch(null); setResults([]); setRecoverId(null); localStorage.removeItem(batchStorage); }}>开始新批次</button>}
    </>}
  </section>;
}

function ZoteroImport({ providerReady, onImported }: { providerReady: boolean; onImported: (id: string) => void }) {
  const [collections, setCollections] = useState<Collection[]>([]);
  const [collection, setCollection] = useState("");
  const [items, setItems] = useState<ZoteroItem[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [offset, setOffset] = useState(0);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [results, setResults] = useState<WorkflowResult[]>([]);
  const [localResults, setLocalResults] = useState<WorkflowResult[]>([]);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    if (!providerReady) return;
    let active = true; setLoading(true); setError("");
    const query = new URLSearchParams({ limit: "25", offset: String(offset) });
    if (collection) query.set("collection_id", collection);
    Promise.all([getJson<{ collections: Collection[] }>("/api/literature/imports/zotero/collections"), getJson<{ items: ZoteroItem[]; total: number }>(`/api/literature/imports/zotero/items?${query}`)])
      .then(([folders, papers]) => { if (active) { setCollections(folders.collections); setItems(papers.items); setTotal(papers.total); } })
      .catch((e) => { if (active) { setError(workflowError(e)); setItems([]); } }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [providerReady, collection, offset, revision]);
  const importedIds = [...new Set(results.filter((item) => ["imported", "already_exists"].includes(item.status) && item.paper_id).map((item) => item.paper_id!))];
  if (!providerReady) return <p>尚未配置 Zotero 连接器。请在后端配置后浏览来源集合并选择条目。</p>;
  return <section><h3>Zotero 选择性导入</h3><p>选择要导入的条目，带入元数据、来源笔记和文件引用；随后可将 PDF 保存为 Workbench 本地文件。</p>
    <label>来源集合<select disabled={busy} value={collection} onChange={(e) => { setCollection(e.target.value); setOffset(0); setSelected([]); }}><option value="">全部 Zotero 条目</option>{collections.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label>
    {error && <p role="alert" className="wb-error">{error} <button onClick={() => setRevision((n) => n + 1)}>重试</button></p>}
    {loading ? <p role="status">正在加载连接器条目…</p> : <><div className="wb-actions"><button disabled={busy || !items.length} onClick={() => setSelected(items.map((item) => item.id))}>选择本页</button><button disabled={busy} onClick={() => setSelected([])}>清空选择</button><span>已选择 {selected.length} 项</span></div>
      {!items.length && !error && <p>此来源集合中没有条目。</p>}
      {items.map((item) => <label className="wb-source-item" key={item.id}><input type="checkbox" disabled={busy} checked={selected.includes(item.id)} onChange={(e) => setSelected((current) => e.target.checked ? [...current, item.id] : current.filter((id) => id !== item.id))} /><span><strong>{item.title}</strong><small>{item.authors.join(", ")} · {item.year || "年份未知"} · {literatureLabel(item.import_status)}</small></span></label>)}
      <div className="wb-actions"><button disabled={busy || offset === 0} onClick={() => { setOffset(offset - 25); setSelected([]); }}>上一页</button><span>{total ? offset + 1 : 0}–{Math.min(offset + 25, total)} / {total}</span><button disabled={busy || offset + 25 >= total} onClick={() => { setOffset(offset + 25); setSelected([]); }}>下一页</button></div></>}
    <button disabled={busy || loading || !selected.length} onClick={() => {
      setBusy(true); setError(""); setLocalResults([]);
      void postJson<{ results: WorkflowResult[] }>("/api/literature/imports/zotero/selective", { item_keys: selected })
        .then((response) => { setResults(response.results); setSelected([]); setRevision((n) => n + 1); }).catch((e) => setError(workflowError(e))).finally(() => setBusy(false));
    }}>{busy ? "正在处理…" : "导入所选条目"}</button>
    <WorkflowResults results={results} onImported={onImported} />
    {!!importedIds.length && <button disabled={busy} onClick={() => {
      setBusy(true); setError("");
      void postJson<{ results: WorkflowResult[] }>("/api/literature/papers/materialize-pdfs", { paper_ids: importedIds })
        .then((response) => setLocalResults(response.results)).catch((e) => setError(workflowError(e))).finally(() => setBusy(false));
    }}>将已导入文献的 PDF 保存到本地</button>}
    <WorkflowResults results={localResults} onImported={onImported} />
  </section>;
}

function WorkflowResults({ results, onImported }: { results: WorkflowResult[]; onImported: (id: string) => void }) {
  if (!results.length) return null;
  return <div className="wb-results" role="status"><h4>逐项处理结果</h4>{results.map((result, index) => <p key={index}><strong>{literatureLabel(result.status)}</strong> · {result.item_key || result.item_id || result.paper_id}{result.error && ` · ${result.error}`} {result.paper_id && <button onClick={() => onImported(result.paper_id!)}>打开文献</button>}</p>)}</div>;
}
