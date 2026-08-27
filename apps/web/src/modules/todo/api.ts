export class TodoApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string | null,
  ) {
    super(message);
  }
}

export function getTodoJson<T>(url: string): Promise<T> {
  return requestTodoJson<T>(url, { method: "GET" });
}

export function postTodoJson<T>(url: string, body?: object): Promise<T> {
  return requestTodoJson<T>(url, {
    method: "POST",
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
}

export function patchTodoJson<T>(url: string, body: object): Promise<T> {
  return requestTodoJson<T>(url, { method: "PATCH", body: JSON.stringify(body) });
}

export function deleteTodo(url: string): Promise<void> {
  return requestTodoJson<void>(url, { method: "DELETE" });
}

async function requestTodoJson<T>(url: string, init: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...init,
    headers: init.body ? { "Content-Type": "application/json" } : undefined,
  });
  if (!response.ok) {
    let code: string | null = null;
    let message = `Todo request failed: ${response.status}`;
    try {
      const payload = (await response.json()) as {
        detail?: { code?: string; message?: string };
      };
      code = payload.detail?.code ?? null;
      message = payload.detail?.message ?? message;
    } catch {
      // Preserve the status when an intermediary returns non-JSON.
    }
    throw new TodoApiError(message, response.status, code);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}
