import { literatureLabel } from "../labels";
import { useEffect, useState } from "react";
import { deleteJson, patchJson } from "../../../core/api";
import { getJson, postJson, workflowError } from "../api";
import type { AttachmentsResponse, CollectionsResponse, LiteratureUserNote, MetadataProvenance, NotesResponse, PaperDetailResponse, UserNoteListResponse, WorkflowResult } from "../types";
import { ImportPanel } from "./ImportPanel";
import { LiteratureAIAssistant } from "./LiteratureAIAssistant";
import { MetadataReview } from "./MetadataReview";
import { IdentityReview } from "./IdentityReview";
import { AssetIntegrity } from "./AssetIntegrity";

type Provenance = MetadataProvenance & { references: Record<string, unknown>[]; origins: Record<string, unknown>[]; source_collections: unknown[]; conflicts: unknown[]; identifiers: unknown[] };
function OriginEvidence({ evidence }: { evidence: unknown }) {
  const values = evidence && typeof evidence === "object" ? evidence as Record<string, unknown> : {};
  return <><dl>{["recommendation_reason", "ai_summary", "selection_rank", "overall_score", "run_key", "method", "filename"].filter((field) => values[field] != null).map((field) => <div key={field}><dt>{literatureLabel(field)}</dt><dd>{String(values[field])}</dd></div>)}</dl><details><summary>完整入库依据</summary><pre>{JSON.stringify(evidence, null, 2)}</pre></details></>;
}
export function PaperDetail({ paperId, onBack, onChanged }: { paperId: string; onBack: () => void; onChanged: () => void }) {
  const [detail, setDetail] = useState<PaperDetailResponse | null>(null);
  const [files, setFiles] = useState<AttachmentsResponse["items"]>([]);
  const [sourceNotes, setSourceNotes] = useState<NotesResponse["items"]>([]);
  const [notes, setNotes] = useState<LiteratureUserNote[]>([]);
  const [collections, setCollections] = useState<CollectionsResponse["items"]>([]);
  const [provenance, setProvenance] = useState<Provenance | null>(null);
  const [tab, setTab] = useState("元数据");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [revision, setRevision] = useState(0);
  const [tags, setTags] = useState("");
  const [note, setNote] = useState("");
  const [removing, setRemoving] = useState(false);
  const [message, setMessage] = useState("");
  const base = `/api/literature/papers/${encodeURIComponent(paperId)}`;
  const refresh = () => { setRevision((n) => n + 1); onChanged(); };
  useEffect(() => {
    let active = true; setLoading(true);
    Promise.all([getJson<PaperDetailResponse>(base), getJson<AttachmentsResponse>(`${base}/attachments`), getJson<NotesResponse>(`${base}/notes`), getJson<UserNoteListResponse>(`${base}/user-notes`), getJson<CollectionsResponse>("/api/literature/collections"), getJson<Provenance>(`${base}/provenance`)])
      .then(([d, f, s, n, c, p]) => { if (active) { setDetail(d); setFiles(f.items); setSourceNotes(s.items); setNotes(n.items); setCollections(c.items); setProvenance(p); setTags(d.paper.tags.join(", ")); setError(""); } })
      .catch((e) => { if (active) setError(workflowError(e)); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [base, revision]);
  const act = async (action: () => Promise<void>) => { setBusy(true); setError(""); try { await action(); } catch (e) { setError(workflowError(e)); } finally { setBusy(false); } };
  return <article className="wb-detail"><button onClick={onBack}>← 返回文献库</button>
    {error && <p role="alert" className="wb-error">{error} <button onClick={refresh}>重新加载文献</button></p>}
    {loading && !detail ? <p role="status">正在加载正式文献…</p> : detail && <>
      <header className="wb-detail-heading"><span className="wb-eyebrow">正式文献</span><h2>{detail.paper.title}</h2><p>{detail.paper.authors.join(", ") || "未记录作者"}</p><small>{[detail.paper.journal, detail.paper.year].filter(Boolean).join(" · ")}</small><div className="wb-actions">{detail.pdf_available && <a href={`/literature/papers/${encodeURIComponent(detail.paper.id)}/reader`}>阅读 PDF</a>}<span className="wb-badge">元数据：{literatureLabel(detail.paper.metadata_status)}</span></div></header>
      <nav className="wb-subtabs" aria-label="文献详情分区">{["元数据", "文件", "外部来源", "入库途径", "笔记", "AI"].map((value) => <button key={value} aria-pressed={tab === value} onClick={() => setTab(value)}>{value}</button>)}</nav>
      {tab === "文件" && <AssetIntegrity paperId={detail.paper.id} files={files} />}
      {tab === "元数据" && <>
        <dl className="wb-metadata">{["doi", "arxiv_id", "openalex_id", "abstract"].map((field) => <div key={field}><dt>{literatureLabel(field)}</dt><dd>{String(detail.paper[field as "doi"] || "未记录")}</dd></div>)}</dl>
        <div className="wb-filters"><label>阅读状态<select disabled={busy} value={detail.paper.reading_status} onChange={(e) => void act(async () => { await patchJson(`${base}/state`, { reading_status: e.target.value }); refresh(); })}>{["inbox", "saved", "reading", "read", "archived"].map((value) => <option key={value} value={value}>{literatureLabel(String(value))}</option>)}</select></label><label>标签（使用英文逗号分隔）<input value={tags} onChange={(e) => setTags(e.target.value)} /></label><button disabled={busy} onClick={() => void act(async () => { await patchJson(`${base}/state`, { tags: tags.split(",").map((value) => value.trim()).filter(Boolean) }); refresh(); })}>保存标签</button></div>
        <details><summary>本地集合归属</summary>{!collections.length && <p>可在文献库的筛选区域创建集合。</p>}{collections.map((collection) => <label className="wb-check" key={collection.id}><input type="checkbox" disabled={busy} checked={detail.collections.some((c) => c.id === collection.id)} onChange={(e) => void act(async () => { await patchJson(`${base}/collections/${encodeURIComponent(collection.id)}`, { present: e.target.checked }); refresh(); })} />{collection.name}</label>)}</details>
        <MetadataReview paper={detail.paper} provenance={provenance} onChanged={refresh} />
        <IdentityReview paper={detail.paper} onChanged={refresh} />
        <details><summary>元数据依据与冲突</summary><pre>{JSON.stringify({ selected_fields: provenance?.selected_fields, metadata_evidence: provenance?.metadata_evidence, conflicts: provenance?.conflicts, identifiers: provenance?.identifiers }, null, 2)}</pre></details>
        <div className="wb-actions">{removing ? <><span>从文献库移除？保留的数据仍可恢复。</span><button disabled={busy} onClick={() => void act(async () => { await deleteJson(base); onChanged(); onBack(); })}>确认移除</button><button onClick={() => setRemoving(false)}>取消</button></> : <button onClick={() => setRemoving(true)}>从文献库移除</button>}</div>
      </>}
      {tab === "文件" && <section><h3>文件与本地资产</h3><p>本地文件不依赖 Zotero 连接器，可独立访问。</p>{!files.length && <p>暂无文件。可在下方添加 PDF。</p>}{files.map((file) => <article className="wb-review-item" key={file.id}><h4>{file.filename}</h4><p>{literatureLabel(file.role)} · {file.storage_kind === "local" ? "Workbench 本地文件" : "Zotero 文件引用"} · {literatureLabel(file.active ? file.availability : "detached")}</p>{file.downloadable && <div className="wb-actions"><a target="_blank" rel="noreferrer" href={`${base}/pdf?asset_id=${encodeURIComponent(file.id)}`}>打开文件</a><a href={`${base}/pdf/download?asset_id=${encodeURIComponent(file.id)}`}>下载</a></div>}</article>)}<button disabled={busy} onClick={() => void act(async () => { const result = await postJson<WorkflowResult>(`${base}/materialize-pdf`); setMessage(`${literatureLabel(result.status)}${result.error ? ` · ${result.error}` : ""}`); refresh(); })}>将 Zotero 主 PDF 保存到本地</button>{message && <p role="status">{message}</p>}<ImportPanel paperId={detail.paper.id} providerReady={false} syncing={false} onSync={() => undefined} onImported={refresh} /></section>}
      {tab === "外部来源" && <section><h3>外部来源 · 外部系统引用</h3><p>此文献关联的外部系统标识，与发现及入库历史分开记录。</p>{!provenance?.references.length && <p>暂无外部来源引用。此文献由 Workbench 管理。</p>}{provenance?.references.map((reference, i) => <article className="wb-review-item" key={i}><h4>{String(reference.provider || "外部来源")}</h4><dl>{Object.entries(reference).filter(([key]) => ["library_id", "item_key", "active"].includes(key)).map(([key, value]) => <div key={key}><dt>{literatureLabel(key)}</dt><dd>{key === "active" ? (value ? "有效" : "已解绑") : String(value)}</dd></div>)}</dl></article>)}<details><summary>来源集合依据</summary><pre>{JSON.stringify(provenance?.source_collections, null, 2)}</pre></details></section>}
      {tab === "入库途径" && <section><h3>入库途径 · 发现与导入历史</h3><p>记录文献如何进入文献库，包括雷达推荐、PDF 上传等。</p>{!provenance?.origins.length && <p>暂无入库历史。</p>}{provenance?.origins.map((origin, i) => <article className="wb-review-item" key={i}><h4>{literatureLabel(String(origin.kind || origin.origin_kind || "import"))}</h4><p>{String(origin.discovered_at || "")}</p><OriginEvidence evidence={origin.evidence} /></article>)}</section>}
      {tab === "笔记" && <section><h3>我的笔记</h3><form onSubmit={(e) => { e.preventDefault(); void act(async () => { const created = await postJson<LiteratureUserNote>(`${base}/user-notes`, { content: note.trim() }); setNotes((items) => [created, ...items]); setNote(""); }); }}><label>撰写本地笔记<textarea required maxLength={50000} value={note} onChange={(e) => setNote(e.target.value)} /></label><button disabled={busy || !note.trim()}>添加笔记</button></form>{!notes.length && <p>暂无本地笔记。</p>}{notes.map((item) => <article className="wb-review-item" key={item.id}><small>{literatureLabel(item.source)} · {new Date(item.created_at).toLocaleString()}</small><p className="wb-note">{item.content}</p></article>)}<h3>来源笔记与批注</h3>{!sourceNotes.length && <p>暂无导入的来源笔记。</p>}{sourceNotes.map((item) => <article className="wb-review-item" key={item.id}><small>{literatureLabel(item.kind)}{item.page_label ? ` · 第 ${item.page_label} 页` : ""}</small><p className="wb-note">{new DOMParser().parseFromString(item.content, "text/html").body.textContent}</p></article>)}</section>}
      <div hidden={tab !== "AI"} className="wb-ai"><LiteratureAIAssistant paperId={detail.paper.id} selection={null} onNoteAdded={(item) => setNotes((items) => [item, ...items])} /></div>
    </>}
  </article>;
}
