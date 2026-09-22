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
      if (file.size > 50 * 1024 * 1024) throw new Error("请选择不超过 50 MiB 的 PDF。");
      const query = new URLSearchParams({ filename: file.name, role });
      if (title.trim()) query.set("title", title.trim());
      if (paperId) query.set("paper_id", paperId);
      const bytes = await file.arrayBuffer();
      const response = await fetch(`/api/literature/imports/pdf?${query}`, { method: "POST", headers: { "Content-Type": "application/pdf" }, body: bytes });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail?.reason || "PDF 导入失败，请重试。");
      setMessage("PDF 已保存到文献库。");
      onImported(result.paper_id);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "PDF 导入失败。");
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
      <h2>{paperId ? "为此文献添加 PDF" : "Upload PDF"}</h2>
      <p>{paperId ? "将其他版本或补充材料保存在此文献下。" : "Save a PDF locally. You can start reading even when publication metadata is incomplete."}</p>
      <label className="filter-field"><span>PDF 文件 · 不超过 50 MiB</span><input aria-label="PDF 文件" type="file" accept="application/pdf,.pdf" onChange={(e) => setFile(e.target.files?.[0] ?? null)} /></label>
      {!paperId ? <label className="filter-field"><span>Title (optional)</span><input value={title} onChange={(e) => setTitle(e.target.value)} /></label> : null}
      {paperId ? <label className="filter-field"><span>文件用途</span><select value={role} onChange={(e) => setRole(e.target.value)}><option value="primary">主 PDF</option><option value="preprint">预印本</option><option value="supplementary">补充材料</option></select></label> : null}
      <button className="action-button action-primary" disabled={!file || uploading} onClick={() => void upload()}>{uploading ? "正在保存…" : "保存 PDF 到文献库"}</button>
      {message ? <p role="status">{message}</p> : null}
    </section>
    {!paperId ? <section><h2>DOI / URL</h2><p>Metadata lookup and enrichment are planned for V2.1. Save a reviewed Radar paper or upload its PDF now.</p></section> : null}
  </div>;
}
