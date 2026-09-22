import { literatureLabel } from "../labels";
import { useEffect, useState } from "react";
import { getJson, postJson, workflowError } from "../api";
import type { MetadataPatch, MetadataProposal, Paper } from "../types";
import { MetadataForm, metadataFields, metadataText } from "./MetadataForm";

export function MetadataReview({ paper, onChanged }: { paper: Paper; onChanged: () => void }) {
  const [proposals, setProposals] = useState<MetadataProposal[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [editing, setEditing] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [revision, setRevision] = useState(0);
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
      setEditing(null); onChanged();
    } catch (e) { setError(workflowError(e)); } finally { setBusy(false); }
  };
  return <section className="metadata-review"><div className="wb-section-heading"><h3>元数据审核</h3><button disabled={busy} onClick={() => setCreating(!creating)}>提出修订</button></div>
    <p>元数据状态：{literatureLabel(paper.metadata_status)}。 更新正式文献前请审核改动。信息完整不代表已经过学术核验。</p>
    {error && <div role="alert" className="wb-error">{error} <button disabled={busy} onClick={() => { setError(""); setRevision((n) => n + 1); onChanged(); }}>重新加载当前元数据</button></div>}
    {creating && <MetadataForm initial={paper} busy={busy} label="创建修订建议" onCancel={() => setCreating(false)} onSave={(patch) => {
      if (!Object.keys(patch).length) { setError("请至少修改一个字段再创建建议。"); return; }
      setBusy(true); setError("");
      void postJson<MetadataProposal>(`/api/literature/papers/${encodeURIComponent(paper.id)}/metadata/proposals`, { source: "user", proposed_metadata: patch })
        .then((result) => { setProposals((items) => [result, ...items]); setCreating(false); })
        .catch((e) => setError(workflowError(e))).finally(() => setBusy(false));
    }} />}
    {loading ? <p role="status">正在加载修订建议…</p> : !proposals.length ? <p>暂无修订建议。可通过“提出修订”补全或更正文献信息。</p> : proposals.map((proposal) => {
      const stale = proposal.status === "pending" && metadataFields.some((field) => metadataText(paper[field]) !== metadataText(proposal.current_metadata[field]));
      return <article className="wb-review-item" key={proposal.id}>
      <h4>{literatureLabel(proposal.source)} · {literatureLabel(proposal.status)}</h4><small>{new Date(proposal.created_at).toLocaleString()}</small>
      {stale && <p className="wb-warning">建议已过期：当前元数据已更改。请拒绝此建议，再通过“提出修订”创建新的审核。</p>}
      <div className="wb-table-scroll"><table><thead><tr><th>字段</th><th>当前元数据</th><th>建议元数据</th></tr></thead><tbody>{proposal.fields_changed.map((field) => <tr key={field}><th>{literatureLabel(field)}</th><td>{metadataText(paper[field as keyof MetadataPatch]) || "—"}</td><td>{metadataText(proposal.proposed_metadata[field as keyof MetadataPatch]) || "—"}</td></tr>)}</tbody></table></div>
      <details><summary>原始审核快照</summary><pre>{JSON.stringify(proposal.current_metadata, null, 2)}</pre></details>
      {proposal.status === "pending" && <><div className="wb-actions"><button disabled={busy || stale} onClick={() => void decide(proposal, "accept")}>接受</button><button disabled={busy} onClick={() => void decide(proposal, "reject")}>拒绝</button><button disabled={busy || stale} onClick={() => setEditing(proposal.id)}>编辑后接受</button></div>
        {editing === proposal.id && <MetadataForm initial={{ ...proposal.current_metadata, ...proposal.proposed_metadata }} busy={busy} label="接受编辑后的元数据" onSave={(edits) => void decide(proposal, "edit-accept", edits)} onCancel={() => setEditing(null)} />}</>}
    </article>; })}
  </section>;
}
