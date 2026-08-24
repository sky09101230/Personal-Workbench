import { lazy, Suspense, useCallback, useEffect, useState } from "react";
import { AppShell } from "../core/shell/AppShell";
import { LiteraturePage } from "../modules/literature/LiteraturePage";
import { getJson } from "../modules/literature/api";
import type { LiteratureStatus } from "../modules/literature/types";

const PdfReaderPage = lazy(() => import("../modules/literature/PdfReaderPage").then((module) => ({
  default: module.PdfReaderPage,
})));

export function App() {
  const [status, setStatus] = useState<LiteratureStatus | null>(null);
  const [apiError, setApiError] = useState(false);
  const pathname = window.location.pathname;

  const loadStatus = useCallback(async () => {
    setApiError(false);
    try {
      setStatus(await getJson<LiteratureStatus>("/api/literature/status"));
    } catch {
      setApiError(true);
    }
  }, []);

  useEffect(() => {
    void loadStatus();
  }, [loadStatus]);

  const readerMatch = pathname.match(/^\/literature\/papers\/(.+)\/reader\/?$/);
  if (readerMatch) {
    return (
      <Suspense fallback={<div className="reader-state"><strong>Loading Reader</strong></div>}>
        <PdfReaderPage paperId={decodeURIComponent(readerMatch[1])} />
      </Suspense>
    );
  }

  return (
    <AppShell>
      <LiteraturePage status={status} apiError={apiError} onStatusReload={loadStatus} />
    </AppShell>
  );
}
