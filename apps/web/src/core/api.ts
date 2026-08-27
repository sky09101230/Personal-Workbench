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

export async function postJson<T>(url: string, body?: object): Promise<T> {
  return requestJson<T>(url, {
    method: "POST",
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
}

export async function patchJson<T>(url: string, body: object): Promise<T> {
  return requestJson<T>(url, { method: "PATCH", body: JSON.stringify(body) });
}

export async function deleteJson(url: string): Promise<void> {
  return requestJson<void>(url, { method: "DELETE" });
}

async function requestJson<T>(url: string, init: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...init,
    headers: init.body ? { "Content-Type": "application/json" } : undefined,
  });
  if (!response.ok) {
    let code: string | null = null;
    let message = `Request failed: ${response.status}`;
    try {
      const payload = (await response.json()) as {
        detail?: { code?: string; message?: string };
      };
      code = payload.detail?.code ?? null;
      message = payload.detail?.message ?? message;
    } catch {
      // Preserve the stable HTTP status when an intermediary returns non-JSON.
    }
    throw new ApiError(message, response.status, code);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}
