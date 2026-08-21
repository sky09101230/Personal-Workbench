import { AlertCircle, FileText, RefreshCw } from "lucide-react";
import type { ReactNode } from "react";
import { PaneHeader } from "./CollectionPane";
import type { Paper } from "../types";

type PaperPaneProps = {
  dataError: boolean;
  heading: string;
  loading: boolean;
  papers: Paper[];
  selectedPaperId: string | null;
  totalPapers: number;
  onSelect: (paperId: string) => void;
};

export function PaperPane({
  dataError,
  heading,
  loading,
  papers,
  selectedPaperId,
  totalPapers,
  onSelect,
}: PaperPaneProps) {
  return (
    <section className="workspace-pane paper-pane" aria-label="Paper list">
      <PaneHeader label={heading} trailing={loading ? "Loading" : `${totalPapers} papers`} />
      {loading ? (
        <WorkspaceState icon={<RefreshCw size={20} className="spin" />} title="Loading your library" detail="Reading collections and paper metadata." />
      ) : dataError ? (
        <WorkspaceState icon={<AlertCircle size={20} />} title="Library unavailable" detail="Check the API service and Zotero permissions, then refresh." />
      ) : papers.length > 0 ? (
        <div className="pane-scroll papers-scroll">
          <div className="paper-rows">
            {papers.map((paper) => (
              <button
                className={`paper-row ${selectedPaperId === paper.id ? "selected" : ""}`}
                key={paper.id}
                type="button"
                onClick={() => onSelect(paper.id)}
              >
                <div className="paper-row-topline">
                  <FileText size={15} aria-hidden="true" />
                  <strong>{paper.title || "Untitled paper"}</strong>
                </div>
                <span className="paper-authors" title={paper.authors.join(", ")}>{formatAuthors(paper.authors)}</span>
                <span className="paper-publication">
                  {paper.journal || "Publication not recorded"}
                  {paper.year ? <span>{paper.year}</span> : null}
                </span>
                {paper.tags.length > 0 ? (
                  <span className="paper-tags" aria-label="Paper tags">
                    {paper.tags.slice(0, 2).map((tag) => <span className="paper-tag" key={tag}>{tag}</span>)}
                    {paper.tags.length > 2 ? <span className="paper-tag">+{paper.tags.length - 2}</span> : null}
                  </span>
                ) : null}
              </button>
            ))}
          </div>
        </div>
      ) : (
        <WorkspaceState icon={<FileText size={20} />} title="No papers here" detail="This collection does not contain any top-level papers." />
      )}
    </section>
  );
}

function WorkspaceState({ icon, title, detail }: { icon: ReactNode; title: string; detail: string }) {
  return (
    <div className="workspace-state">
      <span className="state-icon" aria-hidden="true">{icon}</span>
      <h2>{title}</h2>
      <p>{detail}</p>
    </div>
  );
}

function formatAuthors(authors: string[]) {
  if (authors.length === 0) return "Author not recorded";
  if (authors.length <= 3) return authors.join(" · ");
  return `${authors.slice(0, 3).join(" · ")} · +${authors.length - 3}`;
}
