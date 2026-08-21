import { useCallback, useEffect, useMemo, useState } from "react";
import { CollectionPane } from "./components/CollectionPane";
import { LiteratureHeader } from "./components/LiteratureHeader";
import { PaperInspector } from "./components/PaperInspector";
import { PaperPane } from "./components/PaperPane";
import type {
  Collection,
  CollectionsResponse,
  LiteratureStatus,
  Paper,
  PapersResponse,
} from "./types";

export function LiteraturePage({
  status,
  apiError,
}: {
  status: LiteratureStatus | null;
  apiError: boolean;
}) {
  const providerReady = status?.provider_configured ?? false;
  const [collections, setCollections] = useState<Collection[]>([]);
  const [papers, setPapers] = useState<Paper[]>([]);
  const [totalPapers, setTotalPapers] = useState(0);
  const [libraryPaperTotal, setLibraryPaperTotal] = useState(0);
  const [selectedCollectionId, setSelectedCollectionId] = useState<string | null>(null);
  const [selectedPaperId, setSelectedPaperId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [dataError, setDataError] = useState(false);

  const loadPapers = useCallback(async (collectionId: string | null) => {
    setLoading(true);
    setDataError(false);
    setSelectedPaperId(null);
    try {
      const query = collectionId ? `?collection_id=${encodeURIComponent(collectionId)}` : "";
      const response = await getJson<PapersResponse>(`/api/literature/papers${query}`);
      setPapers(response.items);
      setTotalPapers(response.total);
      if (collectionId === null) {
        setLibraryPaperTotal(response.total);
      }
      setSelectedPaperId(null);
    } catch {
      setDataError(true);
      setPapers([]);
      setTotalPapers(0);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadLibrary = useCallback(async () => {
    setLoading(true);
    setDataError(false);
    setSelectedPaperId(null);
    try {
      const [collectionResponse, paperResponse] = await Promise.all([
        getJson<CollectionsResponse>("/api/literature/collections"),
        getJson<PapersResponse>(
          selectedCollectionId
            ? `/api/literature/papers?collection_id=${encodeURIComponent(selectedCollectionId)}`
            : "/api/literature/papers",
        ),
      ]);
      setCollections(collectionResponse.items);
      setPapers(paperResponse.items);
      setTotalPapers(paperResponse.total);
      if (selectedCollectionId === null) {
        setLibraryPaperTotal(paperResponse.total);
      }
      setSelectedPaperId(null);
    } catch {
      setDataError(true);
      setCollections([]);
      setPapers([]);
      setTotalPapers(0);
    } finally {
      setLoading(false);
    }
  }, [selectedCollectionId]);

  useEffect(() => {
    if (providerReady) {
      void loadLibrary();
    }
  }, [loadLibrary, providerReady]);

  const selectedPaper = useMemo(
    () => papers.find((paper) => paper.id === selectedPaperId) ?? null,
    [papers, selectedPaperId],
  );
  const selectedCollection = useMemo(
    () => collections.find((collection) => collection.id === selectedCollectionId) ?? null,
    [collections, selectedCollectionId],
  );
  const connectionError = apiError || dataError;

  const selectCollection = (collectionId: string | null) => {
    setSelectedCollectionId(collectionId);
    void loadPapers(collectionId);
  };

  return (
    <section className="literature-page" id="literature">
      <LiteratureHeader
        connectionError={connectionError}
        loading={loading}
        providerName={status?.provider}
        providerReady={providerReady}
        totalPapers={libraryPaperTotal}
        onRefresh={() => void loadLibrary()}
      />
      <div className="literature-workspace">
        <CollectionPane
          collections={collections}
          providerReady={providerReady}
          selectedCollectionId={selectedCollectionId}
          totalPapers={libraryPaperTotal}
          onSelect={selectCollection}
        />
        <PaperPane
          dataError={dataError}
          heading={selectedCollection?.name || "All papers"}
          loading={loading}
          papers={papers}
          selectedPaperId={selectedPaperId}
          totalPapers={totalPapers}
          onSelect={setSelectedPaperId}
        />
        <PaperInspector paper={selectedPaper} />
      </div>
    </section>
  );
}

async function getJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}
