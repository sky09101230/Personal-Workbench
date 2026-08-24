export class NewsApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string | null,
  ) {
    super(message);
  }
}

export async function getNewsJson<T>(url: string): Promise<T> {
  return requestNewsJson<T>(url, { method: "GET" });
}

export async function postNewsJson<T>(url: string): Promise<T> {
  return requestNewsJson<T>(url, { method: "POST" });
}

async function requestNewsJson<T>(url: string, init: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    let code: string | null = null;
    try {
      const payload = (await response.json()) as { detail?: { code?: string } };
      code = payload.detail?.code ?? null;
    } catch {
      // Keep the stable HTTP status when an intermediary returns non-JSON.
    }
    throw new NewsApiError(`News request failed: ${response.status}`, response.status, code);
  }
  return response.json() as Promise<T>;
}
