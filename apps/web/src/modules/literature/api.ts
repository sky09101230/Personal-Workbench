export { ApiError, getJson, postJson } from "../../core/api";
import { ApiError } from "../../core/api";

export function workflowError(error: unknown): string {
  if (error instanceof TypeError && /fetch|network|load failed/i.test(error.message)) return "无法连接文献服务。请打开正式工作台 http://localhost:5173/literature，并确认后端服务正在运行。";
  if (!(error instanceof ApiError)) return error instanceof Error ? error.message : "请求失败，请重试。";
  if (error.code === "workflow_conflict") return "审核已过期或已经处理。请重新加载当前元数据后再操作。";
  if (error.code === "identity_conflict") return "文献标识冲突，未执行合并。请核对 DOI 和 arXiv 后重试。";
  if (error.code === "migration_required") return "文献库需要迁移，请通过明确的迁移操作完成升级。";
  if (error.code === "provider_not_configured") return "尚未配置 Zotero 连接器，本地文献库和 PDF 上传仍可使用。";
  if (error.status === 422) return "元数据或 PDF 无效，请检查标题、年份（1000–3000）、标识符和文件格式。";
  return `请求失败（${error.code || error.status}），可以保留当前审核内容并重试。`;
}

export async function uploadPdf<T>(url: string, file: File): Promise<T> {
  if (file.size > 50 * 1024 * 1024) throw new Error("请选择不超过 50 MiB 的 PDF。");
  const response = await fetch(url, { method: "POST", headers: { "Content-Type": "application/pdf" }, body: file });
  const result = await response.json();
  if (!response.ok) throw new ApiError("PDF upload failed", response.status, result.detail?.code ?? null);
  return result as T;
}
