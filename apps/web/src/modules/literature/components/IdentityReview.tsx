import { useEffect, useState } from "react";
import { getJson, postJson, workflowError } from "../api";
import { literatureLabel } from "../labels";
import type { IdentityConflict, IdentityContext, Paper, PapersResponse } from "../types";

function ConflictCard({ item, onChanged }: { item: IdentityConflict; onChanged: () => void }) {
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const open = ["open", "reopen"].includes(item.decision);
  const decide = async (decision: string) => {
    setBusy(true); setError("");
    try { await postJson(`/api/literature/identity/conflicts/${encodeURIComponent(item.id)}/decisions`, { snapshot: item.snapshot, decision, reason }); onChanged(); }
    catch (e) { setError(workflowError(e)); } finally { setBusy(false); }
  };
  return <article className="wb-review-item"><h4>{literatureLabel(item.decision)} · 身份或来源证据</h4><p>{item.reason}</p>
    {item.papers.map((paper) => <p key={paper.id}>{paper.deleted ? `${paper.title}（已从文献库移除）` : <a href={`/literature?paper=${encodeURIComponent(paper.id)}`}>查看相关文献：{paper.title}{paper.doi ? ` · ${paper.doi}` : ""}</a>}</p>)}
    {!item.paper_ids.length && <p>尚无可靠的文献归属。保留来源证据不代表 PDF 已恢复。</p>}
    <details><summary>原始冲突证据</summary><pre>{JSON.stringify(item.payload, null, 2)}</pre></details>
    <details><summary>审核记录（{item.history.length}）</summary>{item.history.map((entry) => <p key={entry.id}>{literatureLabel(entry.decision)} · {entry.reason} · {new Date(entry.created_at).toLocaleString()}</p>)}</details>
    <label>冲突处理理由<textarea minLength={10} maxLength={4000} value={reason} onChange={(e) => setReason(e.target.value)} /></label>
    {error && <p role="alert" className="wb-error">{error} <button onClick={onChanged}>重新加载审核</button></p>}
    <div className="wb-actions">{(open ? (item.paper_ids.length ? ["keep_current", ...(["Weak title/year/author evidence requires review", "Same title has conflicting formal DOI"].includes(item.reason) ? ["keep_separate"] : [])] : ["quarantine"]) : ["reopen"]).map((action) => <button key={action} disabled={busy || reason.trim().length < 10} onClick={() => void decide(action)}>{literatureLabel(action)}</button>)}</div>
    {item.decision === "keep_separate" && <p>审核已记录。请重新尝试原导入；不会合并已有文献。</p>}
  </article>;
}

export function IdentityConflictQueue({ onChanged }: { onChanged: () => void }) {
  const [active, setActive] = useState(false);
  const [revision, setRevision] = useState(0);
  const [offset, setOffset] = useState(0);
  const [data, setData] = useState<{ items: IdentityConflict[]; total: number }>({ items: [], total: 0 });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const refresh = () => { setRevision((n) => n + 1); onChanged(); };
  useEffect(() => {
    if (!active) return;
    let current = true; setLoading(true);
    getJson<typeof data>(`/api/literature/identity/conflicts?limit=25&offset=${offset}`).then((result) => { if (current) { setData(result); setError(""); } }).catch((e) => { if (current) setError(workflowError(e)); }).finally(() => { if (current) setLoading(false); });
    return () => { current = false; };
  }, [active, revision, offset]);
  return <details className="wb-filter-more" onToggle={(event) => setActive(event.currentTarget.open)}><summary>身份与来源冲突审核</summary>
    {loading && <p role="status">正在加载冲突证据…</p>}{error && <p role="alert">{error}</p>}<button onClick={refresh}>刷新审核队列</button>
    {!loading && !data.total && <p>暂无已记录的身份或来源冲突。</p>}{data.items.map((item) => <ConflictCard key={item.id} item={item} onChanged={refresh} />)}
    <div className="wb-actions"><button disabled={loading || offset === 0} onClick={() => setOffset(Math.max(0, offset - 25))}>上一页冲突</button><span>{data.total} 条记录</span><button disabled={loading || offset + 25 >= data.total} onClick={() => setOffset(offset + 25)}>下一页冲突</button></div>
  </details>;
}

function EvidenceChoices({ data, selected, onChange }: { data: IdentityContext; selected: string[]; onChange: (ids: string[]) => void }) {
  return <details><summary>选择支持证据（已选 {selected.length}）</summary><p>请选择与当前标识对应的依据，每次最多 50 条。</p>{data.evidence.map((item) => <article className="wb-review-item" key={item.id}><label className="wb-check"><input type="checkbox" checked={selected.includes(item.id)} disabled={!selected.includes(item.id) && selected.length >= 50} onChange={(e) => onChange(e.target.checked ? [...selected, item.id] : selected.filter((id) => id !== item.id))} />{item.source === "manual" ? "手动导入" : literatureLabel(item.source)} · {new Date(item.observed_at).toLocaleString()}</label><p>{item.metadata.title} · {[item.metadata.doi, item.metadata.arxiv_id, item.metadata.openalex_id].filter(Boolean).join(" · ")}</p><details><summary>查看证据内容</summary><pre>{JSON.stringify(item, null, 2)}</pre></details></article>)}</details>;
}

export function IdentityReview({ paper, onChanged }: { paper: Paper; onChanged: () => void }) {
  const [data, setData] = useState<IdentityContext | null>(null);
  const [revision, setRevision] = useState(0);
  const [reason, setReason] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const [values, setValues] = useState({ doi: "", arxiv_id: "", openalex_id: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [query, setQuery] = useState("");
  const [options, setOptions] = useState<Paper[]>([]);
  const [otherId, setOtherId] = useState("");
  const [other, setOther] = useState<IdentityContext | null>(null);
  const [otherEvidence, setOtherEvidence] = useState<string[]>([]);
  const refresh = () => { setRevision((n) => n + 1); onChanged(); };
  useEffect(() => {
    let current = true;
    getJson<IdentityContext>(`/api/literature/papers/${encodeURIComponent(paper.id)}/identity`).then((result) => {
      if (current) { setData(result); setSelected([]); setValues({ doi: result.metadata.doi ?? "", arxiv_id: result.metadata.arxiv_id ?? "", openalex_id: result.metadata.openalex_id ?? "" }); setError(""); }
    }).catch((e) => { if (current) setError(workflowError(e)); });
    return () => { current = false; };
  }, [paper, revision]);
  useEffect(() => {
    let current = true;
    getJson<PapersResponse>(`/api/literature/papers?limit=100&query=${encodeURIComponent(query)}`).then((result) => { if (current) setOptions(result.items.filter((item) => item.id !== paper.id && item.doi && !item.doi.startsWith("10.48550/arxiv."))); }).catch((e) => { if (current) setError(workflowError(e)); });
    return () => { current = false; };
  }, [paper.id, query]);
  useEffect(() => {
    let current = true; setOther(null); setOtherEvidence([]);
    if (otherId) getJson<IdentityContext>(`/api/literature/papers/${encodeURIComponent(otherId)}/identity`).then((result) => { if (current) setOther(result); }).catch((e) => { if (current) setError(workflowError(e)); });
    return () => { current = false; };
  }, [otherId, revision]);
  const act = async (url: string, payload: object) => {
    setBusy(true); setError("");
    try { await postJson(url, payload); refresh(); }
    catch (e) { setError(workflowError(e)); } finally { setBusy(false); }
  };
  const enabled = !!data && selected.length > 0 && reason.trim().length >= 10 && !busy;
  const base = `/api/literature/papers/${encodeURIComponent(paper.id)}`;
  return <section className="metadata-review"><h3>文献身份与版本</h3>
    {error && <p role="alert" className="wb-error">{error} <button onClick={refresh}>重新加载身份依据</button></p>}
    {!data ? <p role="status">正在加载身份依据…</p> : <>
      <p>身份状态：{literatureLabel(data.identity_status)}。人工确认记录你的核对依据，不代替外部学术核验。</p>
      <p>{data.identifiers.map((item) => `${item.kind}: ${item.value}`).join(" · ") || "没有已接受的学术标识；可以保留为身份待确定的文献。"}</p>
      <EvidenceChoices data={data} selected={selected} onChange={setSelected} />
      <label>身份审核理由<textarea minLength={10} maxLength={4000} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="说明你如何确认论文、标识与来源对应（至少 10 个字符）" /></label>
      <button disabled={!enabled || !data.identifiers.length || data.identity_status === "conflict" || data.pending_proposals.length > 0 || data.conflicts.some((item) => ["open", "reopen"].includes(item.decision))} onClick={() => void act(`${base}/identity/confirm`, { snapshot: data.snapshot, evidence_ids: selected, reason })}>确认当前文献身份</button>
      {!!data.pending_proposals.length && <p>身份确认前，请先处理待审核的元数据建议。</p>}
      <details><summary>更正已接受的学术标识</summary><p>更正保留现有文献记录、笔记和附件；不能占用另一篇文献的标识。清空字段表示明确撤销当前标识。</p><div className="metadata-fields">{(["doi", "arxiv_id", "openalex_id"] as const).map((field) => <label key={field}>更正 {literatureLabel(field)}<input value={values[field]} maxLength={1000} onChange={(e) => setValues({ ...values, [field]: e.target.value })} /></label>)}</div><button disabled={!enabled} onClick={() => void act(`${base}/identity/correct`, { snapshot: data.snapshot, evidence_ids: selected, reason, correction: Object.fromEntries(Object.entries(values).map(([key, value]) => [key, value.trim() || null])) })}>记录标识更正</button></details>
      {data.conflicts.map((item) => <ConflictCard key={item.id} item={item} onChanged={refresh} />)}
      <details><summary>预印本与发表版本关系</summary><p>版本关系保留两篇独立文献，不合并身份、笔记或文件。</p>
        {data.versions.map((version) => <article className="wb-review-item" key={version.id}><h4>{version.status === "active" ? "有效" : literatureLabel(version.status)}{version.needs_review ? " · 版本依据已变化，请复核" : ""}</h4><p>{version.current_metadata.preprint?.title ?? version.preprint_id} → {version.current_metadata.published?.title ?? version.published_id}</p><details><summary>版本关系依据</summary><pre>{JSON.stringify(version.evidence, null, 2)}</pre></details>{version.status === "active" && <button disabled={busy || reason.trim().length < 10} onClick={() => void act(`/api/literature/versions/${encodeURIComponent(version.id)}/retract`, { snapshot: version.snapshot, reason })}>撤回版本关系</button>}</article>)}
        {data.metadata.arxiv_id && (!data.metadata.doi || data.metadata.doi.startsWith("10.48550/arxiv.")) ? <>
          <label>查找发表版本<input value={query} onChange={(e) => setQuery(e.target.value)} /></label><label>发表版本文献<select value={otherId} onChange={(e) => setOtherId(e.target.value)}><option value="">选择独立的正式论文</option>{options.map((item) => <option key={item.id} value={item.id}>{item.title} · {item.doi}</option>)}</select></label>
          {other && <><p>发表版本的支持证据</p><EvidenceChoices data={other} selected={otherEvidence} onChange={setOtherEvidence} /></>}
          <button disabled={!enabled || !other || !otherEvidence.length} onClick={() => other && void act(`${base}/versions`, { published_id: other.paper_id, preprint_snapshot: data.snapshot, published_snapshot: other.snapshot, evidence_ids: [...selected, ...otherEvidence], reason })}>记录预印本与发表版本关系</button>
        </> : <p>从具有 arXiv 标识的独立预印本文献发起版本关联。</p>}
      </details>
    </>}
  </section>;
}
