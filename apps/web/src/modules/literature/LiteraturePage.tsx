import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiError, getJson, postJson } from "./api";
import { CollectionPane } from "./components/CollectionPane";
import { LiteratureHeader } from "./components/LiteratureHeader";
import { PaperInspector } from "./components/PaperInspector";
import { PaperPane } from "./components/PaperPane";
import type {
  Collection,
  CollectionsResponse,
  FiltersResponse,
  LiteratureStatus,
  Paper,
  PapersResponse,
  SyncResponse,
} from "./types";

const PAGE_SIZE = 25;
const EMPTY_FILTERS: FiltersResponse = { years: [], journals: [], tags: [] };

export function LiteraturePage({
  status,
  apiError,
  onStatusReload,
}: {
  status: LiteratureStatus | null;
  apiError: boolean;
  onStatusReload: () => Promise<void>;
}) {
  const providerReady = status?.provider_configured ?? false;
  const [collections, setCollections] = useState<Collection[]>([]);
  const [papers, setPapers] = useState<Paper[]>([]);
  const [filters, setFilters] = useState<FiltersResponse>(EMPTY_FILTERS);
  const [totalPapers, setTotalPapers] = useState(0);
  const [libraryPaperTotal, setLibraryPaperTotal] = useState(0);
  const [selectedCollectionId, setSelectedCollectionId] = useState<string | null>(null);
  const [selectedPaperId, setSelectedPaperId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [author, setAuthor] = useState("");
  const [year, setYear] = useState("");
  const [journal, setJournal] = useState("");
  const [tag, setTag] = useState("");
  const [offset, setOffset] = useState(0);
  const [loadingMetadata, setLoadingMetadata] = useState(false);
  const [loadingPapers, setLoadingPapers] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [dataError, setDataError] = useState(false);
  const [syncMessage, setSyncMessage] = useState<string | null>(null);

  const loadMetadata = useCallback(async () => {
    setLoadingMetadata(true);
    setDataError(false);
    try {
      const [collectionResponse, filterResponse, countResponse] = await Promise.all([
        getJson<CollectionsResponse>("/api/literature/collections"),
        getJson<FiltersResponse>("/api/literature/filters"),
        getJson<PapersResponse>("/api/literature/papers?limit=1"),
      ]);
      setCollections(collectionResponse.items);
      setFilters(filterResponse);
      setLibraryPaperTotal(countResponse.total);
    } catch {
      setDataError(true);
    } finally {
      setLoadingMetadata(false);
    }
  }, []);

  const loadPapers = useCallback(async (targetOffset: number) => {
    setLoadingPapers(true);
    setDataError(false);
    try {
      const query = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(targetOffset) });
      if (selectedCollectionId) query.set("collection_id", selectedCollectionId);
      if (searchQuery.trim()) query.set("query", searchQuery.trim());
      if (author.trim()) query.set("author", author.trim());
      if (year) query.set("year", year);
      if (journal) query.set("journal", journal);
      if (tag) query.set("tag", tag);
      const response = await getJson<PapersResponse>(`/api/literature/papers?${query.toString()}`);
      setPapers(response.items);
      setTotalPapers(response.total);
      setSelectedPaperId((current) => (
        current && response.items.some((paper) => paper.id === current) ? current : null
      ));
    } catch {
      setDataError(true);
      setPapers([]);
      setTotalPapers(0);
    } finally {
      setLoadingPapers(false);
    }
  }, [author, journal, searchQuery, selectedCollectionId, tag, year]);

  useEffect(() => {
    if (status) void loadMetadata();
  }, [loadMetadata, status]);

  useEffect(() => {
    if (!status) return;
    const timeout = window.setTimeout(() => void loadPapers(offset), 250);
    return () => window.clearTimeout(timeout);
  }, [loadPapers, offset, status]);

  const selectedCollection = useMemo(
    () => collections.find((collection) => collection.id === selectedCollectionId) ?? null,
    [collections, selectedCollectionId],
  );
  const connectionError = apiError || dataError;
  const statusLoading = status === null && !apiError;
  const loading = loadingMetadata || loadingPapers || statusLoading;
  const notSynced = status?.sync_state === "not_started" && libraryPaperTotal === 0;

  const selectCollection = (collectionId: string | null) => {
    setSelectedCollectionId(collectionId);
    setOffset(0);
  };

  const changeFilter = (name: "author" | "year" | "journal" | "tag", value: string) => {
    if (name === "author") setAuthor(value);
    if (name === "year") setYear(value);
    if (name === "journal") setJournal(value);
    if (name === "tag") setTag(value);
    setOffset(0);
  };

  const syncLibrary = async () => {
    setSyncing(true);
    setSyncMessage(null);
    try {
      const result = await postJson<SyncResponse>("/api/literature/sync");
      setSyncMessage(
        `${result.sync_mode === "full" ? "Full" : "Incremental"} sync succeeded`,
      );
      setOffset(0);
      await onStatusReload();
      await Promise.all([loadMetadata(), loadPapers(0)]);
    } catch (error) {
      const code = error instanceof ApiError ? error.code : null;
      setSyncMessage(
        code === "provider_authentication_failed"
          ? "Sync failed: check Zotero credentials"
          : "Sync failed: showing the previous cache",
      );
    } finally {
      setSyncing(false);
    }
  };

  return (
    <section className="literature-page" id="literature">
      <LiteratureHeader
        connectionError={connectionError}
        lastSyncedAt={status?.last_synced_at}
        loading={loading}
        providerName={status?.provider}
        providerReady={providerReady}
        searchQuery={searchQuery}
        syncing={syncing}
        syncMessage={syncMessage}
        syncState={status?.sync_state}
        statusLoading={statusLoading}
        totalPapers={libraryPaperTotal}
        onSearchChange={(value) => { setSearchQuery(value); setOffset(0); }}
        onSync={() => void syncLibrary()}
      />
      <div className="literature-workspace">
        <CollectionPane
          author={author}
          collections={collections}
          filters={filters}
          journal={journal}
          providerReady={providerReady}
          selectedCollectionId={selectedCollectionId}
          tag={tag}
          totalPapers={libraryPaperTotal}
          year={year}
          onFilterChange={changeFilter}
          onSelect={selectCollection}
        />
        <PaperPane
          dataError={connectionError}
          heading={selectedCollection?.name || "All papers"}
          loading={loadingPapers || statusLoading}
          notConfigured={!providerReady}
          notSynced={notSynced}
          offset={offset}
          pageSize={PAGE_SIZE}
          papers={papers}
          selectedPaperId={selectedPaperId}
          totalPapers={totalPapers}
          onPageChange={setOffset}
          onSelect={setSelectedPaperId}
          onSync={() => void syncLibrary()}
        />
        <PaperInspector paperId={selectedPaperId} />
      </div>
    </section>
  );
}
