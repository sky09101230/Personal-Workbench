import { BookOpenText, FileText, Link2, NotebookPen } from "lucide-react";
import type { ReactNode } from "react";
import { PaneHeader } from "./CollectionPane";
import type { Paper } from "../types";

export function PaperInspector({ paper }: { paper: Paper | null }) {
  return (
    <aside className="workspace-pane inspector-pane" aria-label="Paper details">
      <PaneHeader label="Inspector" />
      {paper ? (
        <div className="pane-scroll inspector-scroll">
          <article className="inspector-content">
            <h2>{paper.title || "Untitled paper"}</h2>
            <InspectorField label="Authors">
              <p>{paper.authors.join(", ") || "Not recorded"}</p>
            </InspectorField>
            <InspectorField label="Publication">
              <p>{[paper.journal, paper.year].filter(Boolean).join(" · ") || "Not recorded"}</p>
            </InspectorField>
            <InspectorField label="DOI">
              <p className={paper.doi ? "doi-value" : ""}>
                {paper.doi ? <><Link2 size={14} aria-hidden="true" />{paper.doi}</> : "Not recorded"}
              </p>
            </InspectorField>
            <InspectorField label="Tags">
              {paper.tags.length > 0 ? (
                <div className="inspector-tags">
                  {paper.tags.map((tag) => <span className="inspector-tag" key={tag}>{tag}</span>)}
                </div>
              ) : <p>Not recorded</p>}
            </InspectorField>
            <div className="inspector-actions">
              <button className="action-button action-primary" type="button" disabled title="PDF unavailable">
                <FileText size={15} aria-hidden="true" />
                Read PDF
              </button>
              <button className="action-button action-secondary" type="button" disabled title="Notes unavailable">
                <NotebookPen size={15} aria-hidden="true" />
                Notes
              </button>
            </div>
          </article>
        </div>
      ) : (
        <div className="inspector-empty">
          <BookOpenText size={22} aria-hidden="true" />
          <h2>No paper selected</h2>
          <p>Select a paper to inspect its metadata and available actions.</p>
        </div>
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
