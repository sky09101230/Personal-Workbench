import { AlertCircle, FileText, RefreshCw } from "lucide-react";
import type { ReactNode } from "react";
import { PaneHeader } from "./CollectionPane";
import type { Paper } from "../types";

type PaperPaneProps = {
  dataError: boolean;
  heading: string;
  loading: boolean;
  notConfigured: boolean;
  notSynced: boolean;
  offset: number;
  pageSize: number;
  papers: Paper[];
  selectedPaperId: string | null;
  totalPapers: number;
  onSelect: (paperId: string) => void;
  onPageChange: (offset: number) => void;
  onSync: () => void;
};

export function PaperPane({
  dataError,
  heading,
  loading,
  notConfigured,
  notSynced,
  offset,
  pageSize,
  papers,
  selectedPaperId,
  totalPapers,
  onSelect,
  onPageChange,
  onSync,
}: PaperPaneProps) {
  return (
    <section className="workspace-pane paper-pane" aria-label="Paper list">
      <PaneHeader label={heading} trailing={loading ? "Loading" : `${totalPapers} papers`} />
      {loading ? (
        <WorkspaceState icon={<RefreshCw size={20} className="spin" />} title="Loading your library" detail="Reading collections and paper metadata." />
      ) : dataError ? (
        <WorkspaceState icon={<AlertCircle size={20} />} title="Library unavailable" detail="Check the API service and Zotero permissions, then refresh." />
      ) : notConfigured && totalPapers === 0 ? (
        <WorkspaceState icon={<AlertCircle size={20} />} title="Zotero is not configured" detail="Add ZOTERO_USER_ID and ZOTERO_API_KEY on the API service, then restart it." />
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
          {totalPapers > pageSize ? (
            <nav className="paper-pagination" aria-label="Paper pages">
              <button type="button" disabled={offset === 0} onClick={() => onPageChange(Math.max(0, offset - pageSize))}>Previous</button>
              <span>{Math.floor(offset / pageSize) + 1} / {Math.ceil(totalPapers / pageSize)}</span>
              <button type="button" disabled={offset + pageSize >= totalPapers} onClick={() => onPageChange(offset + pageSize)}>Next</button>
            </nav>
          ) : null}
        </div>
      ) : notSynced ? (
        <WorkspaceState
          icon={<RefreshCw size={20} />}
          title="Sync your Zotero library"
          detail="Run the first manual sync to fill the local Literature cache."
          action={<button className="action-button action-primary" type="button" onClick={onSync}>Sync Zotero</button>}
        />
      ) : (
        <WorkspaceState icon={<FileText size={20} />} title="No matching papers" detail="This collection or filter combination has no cached papers." />
      )}
    </section>
  );
}

function WorkspaceState({ icon, title, detail, action }: { icon: ReactNode; title: string; detail: string; action?: ReactNode }) {
  return (
    <div className="workspace-state">
      <span className="state-icon" aria-hidden="true">{icon}</span>
      <h2>{title}</h2>
      <p>{detail}</p>
      {action ? <div className="workspace-state-action">{action}</div> : null}
    </div>
  );
}

function formatAuthors(authors: string[]) {
  if (authors.length === 0) return "Author not recorded";
  if (authors.length <= 3) return authors.join(" · ");
  return `${authors.slice(0, 3).join(" · ")} · +${authors.length - 3}`;
}
