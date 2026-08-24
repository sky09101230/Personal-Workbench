import { useEffect, useState } from "react";
import { AppShell } from "../core/shell/AppShell";
import { LiteraturePage } from "../modules/literature/LiteraturePage";
import { NewsPage } from "../modules/news/NewsPage";

type LiteratureStatus = {
  provider: string;
  provider_configured: boolean;
  sync_state: string;
};

export function App() {
  const [status, setStatus] = useState<LiteratureStatus | null>(null);
  const [apiError, setApiError] = useState(false);
  const pathname = window.location.pathname;
  const isNews = pathname === "/news" || pathname.startsWith("/news/");

  useEffect(() => {
    fetch("/api/literature/status")
      .then((response) => {
        if (!response.ok) throw new Error("API unavailable");
        return response.json() as Promise<LiteratureStatus>;
      })
      .then(setStatus)
      .catch(() => setApiError(true));
  }, []);

  return (
    <AppShell>
      {isNews ? <NewsPage /> : <LiteraturePage status={status} apiError={apiError} />}
    </AppShell>
  );
}
