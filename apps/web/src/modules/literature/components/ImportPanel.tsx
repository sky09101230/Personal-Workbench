import { useState } from "react";

export function ImportPanel({ providerReady, syncing, onSync, onImported, paperId }: {
  providerReady: boolean;
  syncing: boolean;
  onSync: () => void;
  onImported: (paperId: string) => void;
  paperId?: string;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [role, setRole] = useState("primary");
  const [uploading, setUploading] = useState(false);
  const [message, setMessage] = useState("");

  const upload = async () => {
    if (!file) return;
    setUploading(true);
    setMessage("");
    try {
      if (file.size > 50 * 1024 * 1024) throw new Error("Choose a PDF smaller than 50 MiB.");
      const query = new URLSearchParams({ filename: file.name, role });
      if (title.trim()) query.set("title", title.trim());
      if (paperId) query.set("paper_id", paperId);
      const bytes = await file.arrayBuffer();
      const response = await fetch(`/api/literature/imports/pdf?${query}`, { method: "POST", headers: { "Content-Type": "application/pdf" }, body: bytes });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail?.reason || "PDF import failed. Please try again.");
      setMessage("PDF saved to your Library.");
      onImported(result.paper_id);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "PDF import failed.");
    } finally {
      setUploading(false);
    }
  };

  return <div className="library-import">
    {!paperId ? <section>
      <h2>Import from Zotero</h2>
      <p>Bring papers, collections, notes and attachment links into your Workbench library.</p>
      <button className="action-button action-secondary" disabled={!providerReady || syncing} onClick={onSync}>{syncing ? "Importing…" : "Import / Sync Zotero"}</button>
      {!providerReady ? <p>Configure Zotero credentials in the API to enable this connector.</p> : null}
    </section> : null}
    <section>
      <h2>{paperId ? "Add a PDF to this paper" : "Upload PDF"}</h2>
      <p>{paperId ? "Keep another version or supplementary material with this paper." : "Save a PDF locally. You can start reading even when publication metadata is incomplete."}</p>
      <label className="filter-field"><span>PDF file · up to 50 MiB</span><input aria-label="PDF file" type="file" accept="application/pdf,.pdf" onChange={(e) => setFile(e.target.files?.[0] ?? null)} /></label>
      {!paperId ? <label className="filter-field"><span>Title (optional)</span><input value={title} onChange={(e) => setTitle(e.target.value)} /></label> : null}
      {paperId ? <label className="filter-field"><span>File role</span><select value={role} onChange={(e) => setRole(e.target.value)}><option value="primary">Primary PDF</option><option value="preprint">Preprint</option><option value="supplementary">Supplementary</option></select></label> : null}
      <button className="action-button action-primary" disabled={!file || uploading} onClick={() => void upload()}>{uploading ? "Saving…" : "Save PDF to Library"}</button>
      {message ? <p role="status">{message}</p> : null}
    </section>
    {!paperId ? <section><h2>DOI / URL</h2><p>Metadata lookup and enrichment are planned for V2.1. Save a reviewed Radar paper or upload its PDF now.</p></section> : null}
  </div>;
}
