import { useEffect, useState } from "react";
import { AppShell } from "../core/shell/AppShell";
import { LiteraturePage } from "../modules/literature/LiteraturePage";

type LiteratureStatus = {
  provider: string;
  provider_configured: boolean;
  sync_state: string;
};

export function App() {
  const [status, setStatus] = useState<LiteratureStatus | null>(null);
  const [apiError, setApiError] = useState(false);

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
      <LiteraturePage status={status} apiError={apiError} />
    </AppShell>
  );
}
