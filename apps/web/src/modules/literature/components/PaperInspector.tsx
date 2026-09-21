import { BookOpenText, Download, FileText, Link2, NotebookPen, RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { getJson, postJson } from "../api";
import { patchJson, deleteJson } from "../../../core/api";
import { ImportPanel } from "./ImportPanel";
import { LiteratureAIAssistant } from "./LiteratureAIAssistant";
import type {
  AttachmentsResponse,
  NotesResponse,
  PaperDetailResponse,
  Collection,
  CollectionsResponse,
  UserNoteListResponse,
  LiteratureUserNote,
} from "../types";
import { PaneHeader } from "./CollectionPane";

export function PaperInspector({ paperId, onChanged }: { paperId: string | null; onChanged: () => void }) {
  const [detail, setDetail] = useState<PaperDetailResponse | null>(null);
  const [notes, setNotes] = useState<NotesResponse["items"]>([]);
  const [attachments, setAttachments] = useState<AttachmentsResponse["items"]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const [revision, setRevision] = useState(0);
  const [collections, setCollections] = useState<Collection[]>([]);
  const [provenance, setProvenance] = useState<Record<string, unknown> | null>(null);
  const [editError, setEditError] = useState("");
  const [tags, setTags] = useState("");
  const [deleteConfirm, setDeleteConfirm] = useState(false);
  const [userNotes, setUserNotes] = useState<LiteratureUserNote[]>([]);
  const [manualNote, setManualNote] = useState("");
  const refresh = () => { setRevision((n) => n + 1); onChanged(); };
  const update = async (url: string, body: object) => {
    try { await patchJson(url, body); setEditError(""); refresh(); }
    catch { setEditError("Could not save your change. Try again."); }
  };

  useEffect(() => {
    setDetail(null);
    setNotes([]);
    setAttachments([]);
    setError(false);
    setDeleteConfirm(false);
    setUserNotes([]);
    setManualNote("");
    if (!paperId) return;

    let cancelled = false;
    setLoading(true);
    Promise.all([
      getJson<PaperDetailResponse>(`/api/literature/papers/${encodeURIComponent(paperId)}`),
      getJson<NotesResponse>(`/api/literature/papers/${encodeURIComponent(paperId)}/notes`),
      getJson<AttachmentsResponse>(`/api/literature/papers/${encodeURIComponent(paperId)}/attachments`),
      getJson<CollectionsResponse>("/api/literature/collections"),
      getJson<Record<string, unknown>>(`/api/literature/papers/${encodeURIComponent(paperId)}/provenance`),
      getJson<UserNoteListResponse>(`/api/literature/papers/${encodeURIComponent(paperId)}/user-notes`),
    ])
      .then(([paperDetail, noteResponse, attachmentResponse, collectionResponse, provenanceResponse, userNoteResponse]) => {
        if (cancelled) return;
        setDetail(paperDetail);
        setNotes(noteResponse.items);
        setAttachments(attachmentResponse.items);
        setCollections(collectionResponse.items);
        setProvenance(provenanceResponse);
        setTags(paperDetail.paper.tags.join(", "));
        setUserNotes(userNoteResponse.items);
      })
      .catch(() => {
        if (!cancelled) setError(true);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [paperId, revision]);

  return (
    <aside className="workspace-pane inspector-pane" aria-label="Paper details">
      <PaneHeader label="Inspector" />
      {loading ? (
        <InspectorState icon={<RefreshCw size={22} className="spin" />} title="Loading details" detail="Reading cached metadata, Notes, and attachments." />
      ) : error ? (
        <InspectorState icon={<BookOpenText size={22} />} title="Details unavailable" detail="The selected paper could not be read from the local cache." />
      ) : detail ? (
        <div className="pane-scroll inspector-scroll">
          <article className="inspector-content">
            <h2>{detail.paper.title || "Untitled paper"}</h2>
            <div className="library-edit">
              <label>Reading status<select aria-label="Paper reading status" value={detail.paper.reading_status} onChange={(e) => void update(`/api/literature/papers/${encodeURIComponent(detail.paper.id)}/state`, { reading_status: e.target.value })}>{["inbox", "saved", "reading", "read", "archived"].map((s) => <option value={s} key={s}>{s}</option>)}</select></label>
              <label>Tags (comma separated)<input aria-label="Paper tags" value={tags} onChange={(e) => setTags(e.target.value)} /></label>
              <button type="button" className="library-save" onClick={() => void update(`/api/literature/papers/${encodeURIComponent(detail.paper.id)}/state`, { tags: tags.split(",").map((t) => t.trim()).filter(Boolean) })}>Save tags</button>
              <details><summary>Manage collections</summary>{collections.map((collection) => <label className="library-membership" key={collection.id}><input type="checkbox" checked={detail.collections.some((c) => c.id === collection.id)} onChange={(e) => void update(`/api/literature/papers/${encodeURIComponent(detail.paper.id)}/collections/${encodeURIComponent(collection.id)}`, { present: e.target.checked })} />{collection.name}</label>)}</details>
              {editError ? <p role="alert">{editError}</p> : null}
            </div>
            <InspectorField label="Authors">
              <p>{detail.paper.authors.join(", ") || "Not recorded"}</p>
            </InspectorField>
            <InspectorField label="Abstract">
              <p className="abstract-value">{detail.paper.abstract || "Not recorded"}</p>
            </InspectorField>
            <InspectorField label="Publication">
              <p>{[detail.paper.journal, detail.paper.year].filter(Boolean).join(" · ") || "Not recorded"}</p>
            </InspectorField>
            <InspectorField label="DOI">
              <p className={detail.paper.doi ? "doi-value" : ""}>
                {detail.paper.doi ? <><Link2 size={14} aria-hidden="true" />{detail.paper.doi}</> : "Not recorded"}
              </p>
            </InspectorField>
            <InspectorField label="Collections">
              <p>{detail.collections.map((collection) => collection.name).join(", ") || "Not in a collection"}</p>
            </InspectorField>
            <InspectorField label="Tags">
              {detail.paper.tags.length > 0 ? (
                <div className="inspector-tags">
                  {detail.paper.tags.map((tag) => <span className="inspector-tag" key={tag}>{tag}</span>)}
                </div>
              ) : <p>Not recorded</p>}
            </InspectorField>

            <InspectorField label="Zotero Notes">
              {notes.length > 0 ? (
                <div className="note-list">
                  {notes.map((note) => (
                    <article className="note-card" key={note.id}>
                      <span className="note-kind">
                        {note.kind === "annotation" ? `Annotation${note.page_label ? ` · p. ${note.page_label}` : ""}` : "Note"}
                      </span>
                      <p>{plainNoteText(note.content) || "Empty note"}</p>
                    </article>
                  ))}
                </div>
              ) : <p>There are no synced Zotero Notes for this paper.</p>}
            </InspectorField>

            <InspectorField label="Attachments">
              {attachments.length > 0 ? (
                <div className="attachment-list">
                  {attachments.map((attachment) => (
                    <div className="attachment-row" key={attachment.id}>
                      <span>{attachment.filename}</span>
                      <small>{attachment.role} · {attachmentLabel(attachment.availability)}</small>
                      {attachment.downloadable ? <a href={`/api/literature/papers/${encodeURIComponent(detail.paper.id)}/pdf?asset_id=${encodeURIComponent(attachment.id)}`} target="_blank" rel="noreferrer">Open file</a> : null}
                    </div>
                  ))}
                </div>
              ) : <p>No attachments recorded.</p>}
            </InspectorField>

            <div className="inspector-actions">
              <a
                className={`action-button action-primary ${detail.pdf_available ? "" : "disabled"}`}
                href={detail.pdf_available ? `/literature/papers/${encodeURIComponent(detail.paper.id)}/reader` : undefined}
                aria-disabled={!detail.pdf_available}
                title={detail.pdf_available ? "Open PDF Reader" : "PDF unavailable"}
              >
                <FileText size={15} aria-hidden="true" />
                Read PDF
              </a>
              <a
                className={`action-button action-secondary ${detail.pdf_available ? "" : "disabled"}`}
                href={detail.pdf_available ? `/api/literature/papers/${encodeURIComponent(detail.paper.id)}/pdf/download` : undefined}
                aria-disabled={!detail.pdf_available}
                title={detail.pdf_available ? "Download PDF" : "PDF unavailable"}
              >
                <Download size={15} aria-hidden="true" />
                Download PDF
              </a>
            </div>
            <details><summary>Add PDF / another version</summary><ImportPanel paperId={detail.paper.id} providerReady={false} syncing={false} onSync={() => undefined} onImported={refresh} /></details>
            <details className="library-provenance"><summary>Sources and metadata evidence</summary><pre>{JSON.stringify(provenance, null, 2)}</pre></details>
            <details className="library-detail-ai"><summary>AI Assistant · Overview and Ask</summary><LiteratureAIAssistant paperId={detail.paper.id} selection={null} onNoteAdded={(note) => setUserNotes((current) => [note, ...current])} /></details>
            <InspectorField label="My Notes">
              <div className="my-notes">
                <textarea aria-label="Write a local note" placeholder="Write a local note…" value={manualNote} maxLength={50000} onChange={(e) => setManualNote(e.target.value)} />
                <button type="button" className="library-save" disabled={!manualNote.trim()} onClick={() => {
                  void postJson<LiteratureUserNote>(`/api/literature/papers/${encodeURIComponent(detail.paper.id)}/user-notes`, { content: manualNote.trim() }).then((note) => {
                    setUserNotes((current) => [note, ...current]); setManualNote("");
                  }).catch(() => setEditError("Could not save note."));
                }}>Add Note</button>
                {userNotes.map((note) => <article className="reader-note-card" key={note.id}><span>{note.source}</span><p>{note.content}</p></article>)}
              </div>
            </InspectorField>
            <div className="library-edit">{deleteConfirm ? <><p>Remove this paper from Library? Its data is retained for recovery.</p><button type="button" className="library-save" onClick={() => { void deleteJson(`/api/literature/papers/${encodeURIComponent(detail.paper.id)}`).then(() => { setDetail(null); onChanged(); }).catch(() => setEditError("Could not remove paper.")); }}>Confirm remove</button><button type="button" onClick={() => setDeleteConfirm(false)}>Cancel</button></> : <button type="button" className="library-save" onClick={() => setDeleteConfirm(true)}>Remove from Library</button>}</div>
          </article>
        </div>
      ) : (
        <InspectorState icon={<NotebookPen size={22} />} title="No paper selected" detail="Select a paper to inspect its metadata, Zotero Notes, and PDF availability." />
      )}
    </aside>
  );
}

function InspectorField({ label, children }: { label: string; children: ReactNode }) {
  return (
    <section className="inspector-field">
      <h3>{label}</h3>
      {children}
    </section>
  );
}

function InspectorState({ icon, title, detail }: { icon: ReactNode; title: string; detail: string }) {
  return (
    <div className="inspector-empty">
      {icon}
      <h2>{title}</h2>
      <p>{detail}</p>
    </div>
  );
}

function plainNoteText(content: string) {
  const document = new DOMParser().parseFromString(content, "text/html");
  return document.body.textContent?.trim() ?? "";
}

function attachmentLabel(availability: AttachmentsResponse["items"][number]["availability"]) {
  if (availability === "available") return "PDF available";
  if (availability === "linked_file") return "Linked file · unavailable via Web API";
  if (availability === "provider_unavailable") return "PDF unavailable from provider";
  return "Not a readable PDF";
}
