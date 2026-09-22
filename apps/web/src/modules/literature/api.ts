export { ApiError, getJson, postJson } from "../../core/api";
import { ApiError } from "../../core/api";

export function workflowError(error: unknown): string {
  if (!(error instanceof ApiError)) return error instanceof Error ? error.message : "Request failed. Try again.";
  if (error.code === "workflow_conflict") return "This review is stale or already resolved. Reload current metadata before making another decision.";
  if (error.code === "identity_conflict") return "Conflicting identifiers: no merge was made. Review the DOI and arXiv identity before retrying.";
  if (error.code === "migration_required") return "Library migration is required. Ask the operator to run the explicit migration.";
  if (error.code === "provider_not_configured") return "Zotero connector is not configured. Local Library and PDF upload remain available.";
  if (error.status === 422) return "Invalid metadata or PDF. Check the title, year (1000–3000), identifiers and file format.";
  return `${error.code || error.message}. You can retry without discarding your review.`;
}

export async function uploadPdf<T>(url: string, file: File): Promise<T> {
  if (file.size > 50 * 1024 * 1024) throw new Error("Choose a PDF no larger than 50 MiB.");
  const response = await fetch(url, { method: "POST", headers: { "Content-Type": "application/pdf" }, body: file });
  const result = await response.json();
  if (!response.ok) throw new ApiError("PDF upload failed", response.status, result.detail?.code ?? null);
  return result as T;
}
