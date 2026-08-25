import { BookOpenText, Download, FileText, Link2, NotebookPen, RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { getJson } from "../api";
import type {
  AttachmentsResponse,
  NotesResponse,
  PaperDetailResponse,
} from "../types";
import { PaneHeader } from "./CollectionPane";

export function PaperInspector({ paperId }: { paperId: string | null }) {
  const [detail, setDetail] = useState<PaperDetailResponse | null>(null);
  const [notes, setNotes] = useState<NotesResponse["items"]>([]);
  const [attachments, setAttachments] = useState<AttachmentsResponse["items"]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);

  useEffect(() => {
    setDetail(null);
    setNotes([]);
    setAttachments([]);
    setError(false);
    if (!paperId) return;

    let cancelled = false;
    setLoading(true);
    Promise.all([
      getJson<PaperDetailResponse>(`/api/literature/papers/${encodeURIComponent(paperId)}`),
      getJson<NotesResponse>(`/api/literature/papers/${encodeURIComponent(paperId)}/notes`),
      getJson<AttachmentsResponse>(`/api/literature/papers/${encodeURIComponent(paperId)}/attachments`),
    ])
      .then(([paperDetail, noteResponse, attachmentResponse]) => {
        if (cancelled) return;
        setDetail(paperDetail);
        setNotes(noteResponse.items);
        setAttachments(attachmentResponse.items);
      })
      .catch(() => {
        if (!cancelled) setError(true);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [paperId]);

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
                      <small>{attachmentLabel(attachment.availability)}</small>
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
