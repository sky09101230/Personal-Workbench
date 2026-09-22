import { useEffect, useState } from "react";
import { getJson, postJson, uploadPdf, workflowError } from "../api";
import { patchJson } from "../../../core/api";
import type { Collection, UploadBatch, UploadItem, WorkflowResult, ZoteroItem } from "../types";
import { MetadataForm, metadataText } from "./MetadataForm";

const batchStorage = "workbench.literature.upload-batch";
export function ImportCenter({ providerReady, onImported }: { providerReady: boolean; onImported: (id: string) => void }) {
  const [mode, setMode] = useState<"pdf" | "zotero">("pdf");
  return <div className="wb-import"><h2>Import into your Library</h2><p>Review PDFs or select papers from a connector. Workbench owns the saved paper and its research history.</p>
    <nav className="wb-subtabs" aria-label="Import methods"><button aria-pressed={mode === "pdf"} onClick={() => setMode("pdf")}>PDF upload</button><button aria-pressed={mode === "zotero"} onClick={() => setMode("zotero")}>Zotero connector</button></nav>
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
      if (files.length + (batch?.items.length ?? 0) > 50) throw new Error("A batch supports at most 50 PDFs.");
      if (files.some((file) => file.size > 50 * 1024 * 1024 || !file.name.toLowerCase().endsWith(".pdf"))) throw new Error("Select PDF files up to 50 MiB each.");
      const current = batch ?? await postJson<UploadBatch>("/api/literature/uploads/batches");
      remember(current);
      const failures: string[] = [];
      for (const [index, file] of files.entries()) {
        setProgress(`Staging ${index + 1}/${files.length}: ${file.name}`);
        try { await uploadPdf<UploadItem>(`/api/literature/uploads/batches/${encodeURIComponent(current.id)}/files?${new URLSearchParams({ filename: file.name })}`, file); }
        catch (e) { failures.push(`${file.name}: ${workflowError(e)}`); }
      }
      await refresh(current.id);
      if (failures.length) setError(failures.join("\n"));
    });
  };
  const closed = batch?.status === "confirmed" || batch?.status === "cancelled";
  return <section><h3>1. Stage PDFs → 2. Review metadata → 3. Confirm</h3><p>Nothing enters Library until you confirm. Extraction reads PDF metadata and the first three pages; check all suggested values.</p>
    {!batch && recoverId && <p>An upload batch is available to resume. <button disabled={busy} onClick={() => void perform(() => refresh(recoverId))}>Resume staged batch</button><button disabled={busy} onClick={() => { localStorage.removeItem(batchStorage); setRecoverId(null); }}>Dismiss resume link</button></p>}
    {!closed && <label className="wb-upload">Select PDFs · up to 50 files, 50 MiB each<input aria-label="PDF files" type="file" accept="application/pdf,.pdf" multiple disabled={busy || (!!recoverId && !batch)} onChange={(e) => { const files = Array.from(e.target.files ?? []); e.target.value = ""; void stage(files); }} /></label>}
    {progress && <p role="status">{progress}</p>}{error && <p className="wb-error" role="alert">{error}</p>}
    {batch && <><div className="wb-section-heading"><h3>Batch · {batch.status}</h3><span>{batch.items.length} files</span></div>
      {batch.items.map((item) => <article className="wb-review-item" key={item.id}><div className="wb-section-heading"><h4>{item.filename}</h4><span className="wb-badge">{item.status}</span></div>
        <p>{item.candidate_metadata.title || "Title required"}</p>
        <dl>{Object.entries(item.candidate_metadata).filter(([field]) => field !== "title").map(([field, value]) => <div key={field}><dt>{field.replaceAll("_", " ")}</dt><dd>{metadataText(value) || "Not recorded"}</dd></div>)}</dl>
        {!!item.warnings.length && <details><summary className="wb-warning">Extraction warnings · {item.warnings.length}</summary><p>These describe the original extraction; your reviewed values are shown above.</p>{item.warnings.map((warning, i) => <p className="wb-warning" key={i}>{warning.replaceAll("_", " ")}</p>)}</details>}{item.error && <p role="alert">{item.error}</p>}
        <details><summary>Extracted evidence</summary><dl>{Object.entries(item.extracted_metadata).map(([field, evidence]) => <div key={field}><dt>{field}</dt><dd>{metadataText(evidence.value)} <small>· {evidence.source} · confidence {evidence.confidence}</small></dd></div>)}</dl></details>
        {!closed && !["confirmed", "cancelled"].includes(item.status) && <><div className="wb-actions"><button disabled={busy} onClick={() => setEditing(item.id)}>Review / edit metadata</button><button disabled={busy} onClick={() => void perform(async () => { await postJson(`/api/literature/uploads/batches/${encodeURIComponent(batch.id)}/items/${encodeURIComponent(item.id)}/cancel`); await refresh(batch.id); })}>Cancel file</button></div>
          {editing === item.id && <MetadataForm key={`${item.id}-${JSON.stringify(item.candidate_metadata)}`} initial={item.candidate_metadata} busy={busy} onCancel={() => setEditing(null)} onSave={(patch) => void perform(async () => { await patchJson(`/api/literature/uploads/batches/${encodeURIComponent(batch.id)}/items/${encodeURIComponent(item.id)}`, patch); await refresh(batch.id); setEditing(null); })} />}</>}
        {item.target_paper_id && <button onClick={() => onImported(item.target_paper_id!)}>Open canonical paper</button>}
      </article>)}
      <WorkflowResults results={results} onImported={onImported} />
      {!closed ? <div className="wb-actions"><button disabled={busy || editing !== null || !batch.items.some((item) => !["confirmed", "cancelled"].includes(item.status))} onClick={() => void perform(async () => {
        const response = await postJson<{ results: WorkflowResult[] }>(`/api/literature/uploads/batches/${encodeURIComponent(batch.id)}/confirm`); setResults(response.results); await refresh(batch.id);
      })}>Confirm reviewed files</button><button disabled={busy} onClick={() => void perform(async () => { remember(await postJson<UploadBatch>(`/api/literature/uploads/batches/${encodeURIComponent(batch.id)}/cancel`)); setEditing(null); })}>Cancel remaining batch</button><small>Confirmed files remain in Library. Conflicts can be edited and retried.</small></div> : <button onClick={() => { setBatch(null); setResults([]); setRecoverId(null); localStorage.removeItem(batchStorage); }}>Start another batch</button>}
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
  if (!providerReady) return <p>Zotero connector is not configured. Configure it on the API service to browse source collections and select items.</p>;
  return <section><h3>Zotero selective import</h3><p>Select source items to import metadata, source notes and file references. Then copy PDFs into Workbench local assets.</p>
    <label>Source collection<select disabled={busy} value={collection} onChange={(e) => { setCollection(e.target.value); setOffset(0); setSelected([]); }}><option value="">All Zotero items</option>{collections.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label>
    {error && <p role="alert" className="wb-error">{error} <button onClick={() => setRevision((n) => n + 1)}>Retry</button></p>}
    {loading ? <p role="status">Loading connector items…</p> : <><div className="wb-actions"><button disabled={busy || !items.length} onClick={() => setSelected(items.map((item) => item.id))}>Select this page</button><button disabled={busy} onClick={() => setSelected([])}>Clear selection</button><span>{selected.length} selected</span></div>
      {!items.length && !error && <p>No items in this source collection.</p>}
      {items.map((item) => <label className="wb-source-item" key={item.id}><input type="checkbox" disabled={busy} checked={selected.includes(item.id)} onChange={(e) => setSelected((current) => e.target.checked ? [...current, item.id] : current.filter((id) => id !== item.id))} /><span><strong>{item.title}</strong><small>{item.authors.join(", ")} · {item.year || "Year unknown"} · {item.import_status}</small></span></label>)}
      <div className="wb-actions"><button disabled={busy || offset === 0} onClick={() => { setOffset(offset - 25); setSelected([]); }}>Previous</button><span>{total ? offset + 1 : 0}–{Math.min(offset + 25, total)} / {total}</span><button disabled={busy || offset + 25 >= total} onClick={() => { setOffset(offset + 25); setSelected([]); }}>Next</button></div></>}
    <button disabled={busy || loading || !selected.length} onClick={() => {
      setBusy(true); setError(""); setLocalResults([]);
      void postJson<{ results: WorkflowResult[] }>("/api/literature/imports/zotero/selective", { item_keys: selected })
        .then((response) => { setResults(response.results); setSelected([]); setRevision((n) => n + 1); }).catch((e) => setError(workflowError(e))).finally(() => setBusy(false));
    }}>{busy ? "Working…" : "Import selected items"}</button>
    <WorkflowResults results={results} onImported={onImported} />
    {!!importedIds.length && <button disabled={busy} onClick={() => {
      setBusy(true); setError("");
      void postJson<{ results: WorkflowResult[] }>("/api/literature/papers/materialize-pdfs", { paper_ids: importedIds })
        .then((response) => setLocalResults(response.results)).catch((e) => setError(workflowError(e))).finally(() => setBusy(false));
    }}>Copy imported PDFs to Workbench</button>}
    <WorkflowResults results={localResults} onImported={onImported} />
  </section>;
}

function WorkflowResults({ results, onImported }: { results: WorkflowResult[]; onImported: (id: string) => void }) {
  if (!results.length) return null;
  return <div className="wb-results" role="status"><h4>Per-item results</h4>{results.map((result, index) => <p key={index}><strong>{result.status.replaceAll("_", " ")}</strong> · {result.item_key || result.item_id || result.paper_id}{result.error && ` · ${result.error}`} {result.paper_id && <button onClick={() => onImported(result.paper_id!)}>Open paper</button>}</p>)}</div>;
}
