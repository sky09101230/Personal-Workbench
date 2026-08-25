import { RefreshCw, Search } from "lucide-react";

type LiteratureHeaderProps = {
  connectionError: boolean;
  loading: boolean;
  syncing: boolean;
  providerName: string | undefined;
  providerReady: boolean;
  lastSyncedAt: string | null | undefined;
  searchQuery: string;
  syncMessage: string | null;
  syncState: string | undefined;
  statusLoading: boolean;
  totalPapers: number;
  onSearchChange: (query: string) => void;
  onSync: () => void;
};

export function LiteratureHeader({
  connectionError,
  loading,
  syncing,
  providerName,
  providerReady,
  lastSyncedAt,
  searchQuery,
  syncMessage,
  syncState,
  statusLoading,
  totalPapers,
  onSearchChange,
  onSync,
}: LiteratureHeaderProps) {
  const connectionLabel = statusLoading
    ? "Connecting to Workbench API"
    : connectionError
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
        <p>
          {lastSyncedAt ? `Last synced ${formatSyncTime(lastSyncedAt)}` : "Not synced yet"}
          {syncMessage ? ` · ${syncMessage}` : syncState === "failed" ? " · Last sync failed; showing cached data" : ""}
        </p>
      </div>

      <div className="header-actions">
        <label className="search-field">
          <Search size={16} aria-hidden="true" />
          <input
            placeholder="Search title or author..."
            aria-label="Search title or author"
            value={searchQuery}
            onChange={(event) => onSearchChange(event.target.value)}
          />
        </label>
        <button
          className="action-button action-secondary sync-button"
          type="button"
          onClick={onSync}
          disabled={!providerReady || loading || syncing}
        >
          <RefreshCw size={15} className={syncing ? "spin" : ""} />
          {syncing ? "Syncing" : "Sync Zotero"}
        </button>
      </div>
    </header>
  );
}

function formatSyncTime(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}
