import { literatureLabel } from "../labels";
import { useEffect, useState } from "react";
import { getJson, postJson, workflowError } from "../api";
import type { MetadataPatch, MetadataProposal, MetadataProvenance, Paper } from "../types";
import { MetadataForm, metadataFields, metadataText } from "./MetadataForm";

export function MetadataReview({ paper, provenance, onChanged }: { paper: Paper; provenance: MetadataProvenance | null; onChanged: () => void }) {
  const [proposals, setProposals] = useState<MetadataProposal[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [editing, setEditing] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [revision, setRevision] = useState(0);
  const pending = proposals.some((proposal) => proposal.status === "pending");
  useEffect(() => {
    let active = true;
    setLoading(true);
    getJson<{ proposals: MetadataProposal[] }>(`/api/literature/papers/${encodeURIComponent(paper.id)}/metadata/proposals`)
      .then((result) => { if (active) setProposals(result.proposals); })
      .catch((e) => { if (active) setError(workflowError(e)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [paper.id, revision]);
  const decide = async (proposal: MetadataProposal, action: string, edits?: MetadataPatch) => {
    setBusy(true); setError("");
    try {
      const updated = await postJson<MetadataProposal>(`/api/literature/metadata/proposals/${encodeURIComponent(proposal.id)}/${action}`, edits ? { edits } : undefined);
      setProposals((items) => items.map((item) => item.id === updated.id ? updated : item));
      setEditing(null); setRevision((n) => n + 1); onChanged();
    } catch (e) { setError(workflowError(e)); } finally { setBusy(false); }
  };
  return <section className="metadata-review"><div className="wb-section-heading"><h3>元数据审核</h3><button disabled={busy} onClick={() => setCreating(!creating)}>提出修订</button></div>
    <p>信息完整度：{literatureLabel(paper.metadata_status)} · 审核状态：{literatureLabel(paper.metadata_review_status ?? "unreviewed")}。来源更新会先形成建议，人工审核不等同于学术核验。</p>
    <button disabled={busy || loading || pending || paper.metadata_status === "conflict" || paper.metadata_review_status === "reviewed"} onClick={() => {
      setBusy(true); setError("");
      const snapshot = Object.fromEntries(metadataFields.map((field) => [field, paper[field] ?? (field === "authors" ? [] : null)]));
      void postJson(`/api/literature/papers/${encodeURIComponent(paper.id)}/metadata/confirm`, { snapshot })
        .then(onChanged).catch((e) => setError(workflowError(e))).finally(() => setBusy(false));
    }}>确认当前元数据已人工核对</button>
    {pending && <p>请先处理所有待审核建议，再确认当前元数据。</p>}
    <details><summary>当前字段依据</summary><div className="wb-table-scroll"><table><thead><tr><th>字段</th><th>当前值</th><th>采用依据</th></tr></thead><tbody>{metadataFields.filter((field) => metadataText(paper[field])).map((field) => {
      const choice = provenance?.selected_fields[field];
      return <tr key={field}><th>{literatureLabel(field)}</th><td>{metadataText(paper[field])}</td><td>{choice ? `${literatureLabel(choice.source)} · ${choice.reviewed ? "已人工审核" : "尚未审核"}` : "尚未记录"}{choice?.selection_basis === "legacy_unlinked" && <small>（历史来源记录，未绑定单条决策证据）</small>}</td></tr>;
    })}</tbody></table></div></details>
    {error && <div role="alert" className="wb-error">{error} <button disabled={busy} onClick={() => { setError(""); setRevision((n) => n + 1); onChanged(); }}>重新加载当前元数据</button></div>}
    {creating && <MetadataForm initial={paper} busy={busy} label="创建修订建议" onCancel={() => setCreating(false)} onSave={(patch) => {
      if (!Object.keys(patch).length) { setError("请至少修改一个字段再创建建议。"); return; }
      setBusy(true); setError("");
      void postJson<MetadataProposal>(`/api/literature/papers/${encodeURIComponent(paper.id)}/metadata/proposals`, { source: "user", proposed_metadata: patch })
        .then((result) => { setProposals((items) => [result, ...items]); setCreating(false); onChanged(); })
        .catch((e) => setError(workflowError(e))).finally(() => setBusy(false));
    }} />}
    {loading ? <p role="status">正在加载修订建议…</p> : !proposals.length ? <p>暂无修订建议。可通过“提出修订”补全或更正文献信息。</p> : proposals.map((proposal) => {
      const stale = proposal.status === "pending" && metadataFields.some((field) => metadataText(paper[field]) !== metadataText(proposal.current_metadata[field]));
      return <article className="wb-review-item" key={proposal.id}>
      <h4>{literatureLabel(proposal.source)} · {literatureLabel(proposal.status)}</h4><small>{new Date(proposal.created_at).toLocaleString()}</small>
      {stale && <p className="wb-warning">建议已过期：当前元数据已更改。请拒绝此建议，再通过“提出修订”创建新的审核。</p>}
      {proposal.identity_conflict && <p className="wb-warning">标识符存在冲突，直接接受不会更改正式文献。可以拒绝或编辑修正。<br />{proposal.identity_conflict}</p>}
      <div className="wb-table-scroll"><table><thead><tr><th>字段</th><th>当前元数据</th><th>建议元数据</th></tr></thead><tbody>{proposal.fields_changed.map((field) => <tr key={field}><th>{literatureLabel(field)}</th><td>{metadataText(paper[field as keyof MetadataPatch]) || "—"}</td><td>{metadataText(proposal.proposed_metadata[field as keyof MetadataPatch]) || "—"}</td></tr>)}</tbody></table></div>
      <details><summary>原始审核快照</summary><pre>{JSON.stringify(proposal.current_metadata, null, 2)}</pre></details>
      <details><summary>来源证据（{proposal.evidence_ids?.length ?? 0}）</summary>{provenance?.metadata_evidence.filter((item) => proposal.evidence_ids?.includes(item.id)).map((item) => <article key={item.id}><p>{literatureLabel(item.source)} · {new Date(item.observed_at).toLocaleString()}</p><pre>{JSON.stringify({ metadata: item.metadata, evidence: item.evidence }, null, 2)}</pre></article>)}{!proposal.evidence_ids?.length && <p>历史建议未绑定单条来源证据，保留原始审核快照。</p>}</details>
      {proposal.status === "pending" && <><div className="wb-actions"><button disabled={busy || stale || !!proposal.identity_conflict} onClick={() => void decide(proposal, "accept")}>接受</button><button disabled={busy} onClick={() => void decide(proposal, "reject")}>拒绝</button><button disabled={busy || stale} onClick={() => setEditing(proposal.id)}>编辑后接受</button></div>
        {editing === proposal.id && <MetadataForm initial={{ ...proposal.current_metadata, ...proposal.proposed_metadata }} busy={busy} label="接受编辑后的元数据" onSave={(edits) => void decide(proposal, "edit-accept", edits)} onCancel={() => setEditing(null)} />}</>}
    </article>; })}
  </section>;
}
