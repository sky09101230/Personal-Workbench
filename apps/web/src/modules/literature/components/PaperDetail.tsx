import { useEffect, useState } from "react";
import { deleteJson, patchJson } from "../../../core/api";
import { getJson, postJson, workflowError } from "../api";
import type { AttachmentsResponse, CollectionsResponse, LiteratureUserNote, NotesResponse, PaperDetailResponse, UserNoteListResponse, WorkflowResult } from "../types";
import { ImportPanel } from "./ImportPanel";
import { LiteratureAIAssistant } from "./LiteratureAIAssistant";
import { MetadataReview } from "./MetadataReview";

type Provenance = { references: Record<string, unknown>[]; origins: Record<string, unknown>[]; source_collections: unknown[]; metadata_evidence: unknown[]; conflicts: unknown[]; selected_fields: unknown; identifiers: unknown[] };
function OriginEvidence({ evidence }: { evidence: unknown }) {
  const values = evidence && typeof evidence === "object" ? evidence as Record<string, unknown> : {};
  return <><dl>{["recommendation_reason", "ai_summary", "selection_rank", "overall_score", "run_key", "method", "filename"].filter((field) => values[field] != null).map((field) => <div key={field}><dt>{field.replaceAll("_", " ")}</dt><dd>{String(values[field])}</dd></div>)}</dl><details><summary>Full origin evidence</summary><pre>{JSON.stringify(evidence, null, 2)}</pre></details></>;
}
export function PaperDetail({ paperId, onBack, onChanged }: { paperId: string; onBack: () => void; onChanged: () => void }) {
  const [detail, setDetail] = useState<PaperDetailResponse | null>(null);
  const [files, setFiles] = useState<AttachmentsResponse["items"]>([]);
  const [sourceNotes, setSourceNotes] = useState<NotesResponse["items"]>([]);
  const [notes, setNotes] = useState<LiteratureUserNote[]>([]);
  const [collections, setCollections] = useState<CollectionsResponse["items"]>([]);
  const [provenance, setProvenance] = useState<Provenance | null>(null);
  const [tab, setTab] = useState("Metadata");
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
  return <article className="wb-detail"><button onClick={onBack}>← Back to Library</button>
    {error && <p role="alert" className="wb-error">{error} <button onClick={refresh}>Reload paper</button></p>}
    {loading && !detail ? <p role="status">Loading canonical paper…</p> : detail && <>
      <header className="wb-detail-heading"><span className="wb-eyebrow">CANONICAL PAPER</span><h2>{detail.paper.title}</h2><p>{detail.paper.authors.join(", ") || "Authors not recorded"}</p><small>{[detail.paper.journal, detail.paper.year].filter(Boolean).join(" · ")}</small><div className="wb-actions">{detail.pdf_available && <a href={`/literature/papers/${encodeURIComponent(detail.paper.id)}/reader`}>Read PDF</a>}<span className="wb-badge">{detail.paper.metadata_status} metadata</span></div></header>
      <nav className="wb-subtabs" aria-label="Paper sections">{["Metadata", "Files", "Sources", "Origins", "Notes", "AI"].map((value) => <button key={value} aria-pressed={tab === value} onClick={() => setTab(value)}>{value}</button>)}</nav>
      {tab === "Metadata" && <>
        <dl className="wb-metadata">{["doi", "arxiv_id", "openalex_id", "abstract"].map((field) => <div key={field}><dt>{field.replace("_", " ")}</dt><dd>{String(detail.paper[field as "doi"] || "Not recorded")}</dd></div>)}</dl>
        <div className="wb-filters"><label>Reading status<select disabled={busy} value={detail.paper.reading_status} onChange={(e) => void act(async () => { await patchJson(`${base}/state`, { reading_status: e.target.value }); refresh(); })}>{["inbox", "saved", "reading", "read", "archived"].map((value) => <option key={value}>{value}</option>)}</select></label><label>Tags (comma separated)<input value={tags} onChange={(e) => setTags(e.target.value)} /></label><button disabled={busy} onClick={() => void act(async () => { await patchJson(`${base}/state`, { tags: tags.split(",").map((value) => value.trim()).filter(Boolean) }); refresh(); })}>Save tags</button></div>
        <details><summary>Native collection membership</summary>{!collections.length && <p>Create a collection from Library filters.</p>}{collections.map((collection) => <label className="wb-check" key={collection.id}><input type="checkbox" disabled={busy} checked={detail.collections.some((c) => c.id === collection.id)} onChange={(e) => void act(async () => { await patchJson(`${base}/collections/${encodeURIComponent(collection.id)}`, { present: e.target.checked }); refresh(); })} />{collection.name}</label>)}</details>
        <MetadataReview paper={detail.paper} onChanged={refresh} />
        <details><summary>Metadata evidence and conflicts</summary><pre>{JSON.stringify({ selected_fields: provenance?.selected_fields, metadata_evidence: provenance?.metadata_evidence, conflicts: provenance?.conflicts, identifiers: provenance?.identifiers }, null, 2)}</pre></details>
        <div className="wb-actions">{removing ? <><span>Remove from Library? Retained data remains recoverable.</span><button disabled={busy} onClick={() => void act(async () => { await deleteJson(base); onChanged(); onBack(); })}>Confirm remove</button><button onClick={() => setRemoving(false)}>Cancel</button></> : <button onClick={() => setRemoving(true)}>Remove from Library</button>}</div>
      </>}
      {tab === "Files" && <section><h3>Files & local assets</h3><p>Local assets remain available independently of the Zotero connector.</p>{!files.length && <p>No files attached. Add a PDF below.</p>}{files.map((file) => <article className="wb-review-item" key={file.id}><h4>{file.filename}</h4><p>{file.role} · {file.storage_kind === "local" ? "Workbench local asset" : "Zotero file reference"} · {file.active ? file.availability : "detached"}</p>{file.downloadable && <div className="wb-actions"><a target="_blank" rel="noreferrer" href={`${base}/pdf?asset_id=${encodeURIComponent(file.id)}`}>Open file</a><a href={`${base}/pdf/download?asset_id=${encodeURIComponent(file.id)}`}>Download</a></div>}</article>)}<button disabled={busy} onClick={() => void act(async () => { const result = await postJson<WorkflowResult>(`${base}/materialize-pdf`); setMessage(`${result.status.replaceAll("_", " ")}${result.error ? ` · ${result.error}` : ""}`); refresh(); })}>Copy Zotero primary PDF locally</button>{message && <p role="status">{message}</p>}<ImportPanel paperId={detail.paper.id} providerReady={false} syncing={false} onSync={() => undefined} onImported={refresh} /></section>}
      {tab === "Sources" && <section><h3>Sources · external references</h3><p>External provider identities attached to this paper. These are separate from discovery and ingestion history.</p>{!provenance?.references.length && <p>No external source reference. This paper is owned by Workbench.</p>}{provenance?.references.map((reference, i) => <article className="wb-review-item" key={i}><h4>{String(reference.provider || "External source")}</h4><dl>{Object.entries(reference).filter(([key]) => ["library_id", "item_key", "active"].includes(key)).map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{key === "active" ? (value ? "Active" : "Detached") : String(value)}</dd></div>)}</dl></article>)}<details><summary>Source collection evidence</summary><pre>{JSON.stringify(provenance?.source_collections, null, 2)}</pre></details></section>}
      {tab === "Origins" && <section><h3>Origins · discovery & ingestion history</h3><p>How this paper entered your Library, including Radar recommendations and PDF imports.</p>{!provenance?.origins.length && <p>No origin history recorded.</p>}{provenance?.origins.map((origin, i) => <article className="wb-review-item" key={i}><h4>{String(origin.kind || origin.origin_kind || "Import")}</h4><p>{String(origin.discovered_at || "")}</p><OriginEvidence evidence={origin.evidence} /></article>)}</section>}
      {tab === "Notes" && <section><h3>My Notes</h3><form onSubmit={(e) => { e.preventDefault(); void act(async () => { const created = await postJson<LiteratureUserNote>(`${base}/user-notes`, { content: note.trim() }); setNotes((items) => [created, ...items]); setNote(""); }); }}><label>Write a local note<textarea required maxLength={50000} value={note} onChange={(e) => setNote(e.target.value)} /></label><button disabled={busy || !note.trim()}>Add Note</button></form>{!notes.length && <p>No local notes yet.</p>}{notes.map((item) => <article className="wb-review-item" key={item.id}><small>{item.source} · {new Date(item.created_at).toLocaleString()}</small><p className="wb-note">{item.content}</p></article>)}<h3>Source notes & annotations</h3>{!sourceNotes.length && <p>No imported source notes.</p>}{sourceNotes.map((item) => <article className="wb-review-item" key={item.id}><small>{item.kind}{item.page_label ? ` · page ${item.page_label}` : ""}</small><p className="wb-note">{new DOMParser().parseFromString(item.content, "text/html").body.textContent}</p></article>)}</section>}
      <div hidden={tab !== "AI"} className="wb-ai"><LiteratureAIAssistant paperId={detail.paper.id} selection={null} onNoteAdded={(item) => setNotes((items) => [item, ...items])} /></div>
    </>}
  </article>;
}
