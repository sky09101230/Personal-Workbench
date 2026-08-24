export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string | null,
  ) {
    super(message);
  }
}

export async function getJson<T>(url: string): Promise<T> {
  return requestJson<T>(url, { method: "GET" });
}

export async function postJson<T>(url: string): Promise<T> {
  return requestJson<T>(url, { method: "POST" });
}

async function requestJson<T>(url: string, init: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    let code: string | null = null;
    try {
      const payload = (await response.json()) as { detail?: { code?: string } };
      code = payload.detail?.code ?? null;
    } catch {
      // The stable HTTP status is still useful when a proxy returns a non-JSON error.
    }
    throw new ApiError(`Request failed: ${response.status}`, response.status, code);
  }
  return response.json() as Promise<T>;
}
