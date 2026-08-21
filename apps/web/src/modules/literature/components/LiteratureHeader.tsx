import { Command, RefreshCw, Search } from "lucide-react";

type LiteratureHeaderProps = {
  connectionError: boolean;
  loading: boolean;
  providerName: string | undefined;
  providerReady: boolean;
  totalPapers: number;
  onRefresh: () => void;
};

export function LiteratureHeader({
  connectionError,
  loading,
  providerName,
  providerReady,
  totalPapers,
  onRefresh,
}: LiteratureHeaderProps) {
  const connectionLabel = connectionError
    ? "Library unavailable"
    : providerReady
      ? `${providerName ?? "Zotero"} connected · ${totalPapers} papers`
      : "Provider not configured";

  return (
    <header className="literature-header">
      <div className="literature-heading">
        <div className="title-row">
          <h1>Literature</h1>
          <span className={`connection-state ${connectionError ? "error" : ""}`}>
            <span aria-hidden="true" className="connection-dot" />
            {connectionLabel}
          </span>
        </div>
        <p>Your research library</p>
      </div>

      <div className="header-actions">
        <label className="search-field">
          <Search size={16} aria-hidden="true" />
          <input placeholder="Search papers..." aria-label="Search papers" disabled />
          <kbd><Command size={11} aria-hidden="true" />K</kbd>
        </label>
        <button
          className="icon-button header-refresh"
          type="button"
          title="Refresh library"
          aria-label="Refresh library"
          onClick={onRefresh}
          disabled={!providerReady || loading}
        >
          <RefreshCw size={16} className={loading ? "spin" : ""} />
        </button>
      </div>
    </header>
  );
}
