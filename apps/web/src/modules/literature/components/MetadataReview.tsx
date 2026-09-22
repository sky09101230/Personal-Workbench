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
  return <section className="metadata-review"><div className="wb-section-heading"><h3>Metadata review</h3><button disabled={busy} onClick={() => setCreating(!creating)}>Propose correction</button></div>
    <p>Metadata is {paper.metadata_status}. Review changes before updating this canonical paper. Completeness does not imply scholarly verification.</p>
    {error && <div role="alert" className="wb-error">{error} <button disabled={busy} onClick={() => { setError(""); setRevision((n) => n + 1); onChanged(); }}>Reload current metadata</button></div>}
    {creating && <MetadataForm initial={paper} busy={busy} label="Create proposal" onCancel={() => setCreating(false)} onSave={(patch) => {
      if (!Object.keys(patch).length) { setError("Change at least one field to create a proposal."); return; }
      setBusy(true); setError("");
      void postJson<MetadataProposal>(`/api/literature/papers/${encodeURIComponent(paper.id)}/metadata/proposals`, { source: "user", proposed_metadata: patch })
        .then((result) => { setProposals((items) => [result, ...items]); setCreating(false); })
        .catch((e) => setError(workflowError(e))).finally(() => setBusy(false));
    }} />}
    {loading ? <p role="status">Loading proposals…</p> : !proposals.length ? <p>No metadata proposals. Use Propose correction to complete or correct this paper.</p> : proposals.map((proposal) => {
      const stale = proposal.status === "pending" && metadataFields.some((field) => metadataText(paper[field]) !== metadataText(proposal.current_metadata[field]));
      return <article className="wb-review-item" key={proposal.id}>
      <h4>{proposal.source} · {proposal.status}</h4><small>{new Date(proposal.created_at).toLocaleString()}</small>
      {stale && <p className="wb-warning">Stale proposal: current metadata has changed. Reject this proposal and use Propose correction to create a fresh review.</p>}
      <div className="wb-table-scroll"><table><thead><tr><th>Field</th><th>Current metadata</th><th>Proposed metadata</th></tr></thead><tbody>{proposal.fields_changed.map((field) => <tr key={field}><th>{field}</th><td>{metadataText(paper[field as keyof MetadataPatch]) || "—"}</td><td>{metadataText(proposal.proposed_metadata[field as keyof MetadataPatch]) || "—"}</td></tr>)}</tbody></table></div>
      <details><summary>Original review snapshot</summary><pre>{JSON.stringify(proposal.current_metadata, null, 2)}</pre></details>
      {proposal.status === "pending" && <><div className="wb-actions"><button disabled={busy || stale} onClick={() => void decide(proposal, "accept")}>Accept</button><button disabled={busy} onClick={() => void decide(proposal, "reject")}>Reject</button><button disabled={busy || stale} onClick={() => setEditing(proposal.id)}>Edit & accept</button></div>
        {editing === proposal.id && <MetadataForm initial={{ ...proposal.current_metadata, ...proposal.proposed_metadata }} busy={busy} label="Accept edited metadata" onSave={(edits) => void decide(proposal, "edit-accept", edits)} onCancel={() => setEditing(null)} />}</>}
    </article>; })}
  </section>;
}
