import { ApiError, getJson, postJson } from './api';
import type { AssetAcquisition, AttachmentsResponse } from './types';

const agentUrl = 'http://127.0.0.1:23120';
const maxBytes = 50 * 1024 * 1024;
let session: { token: string; expires: number } | null = null;

export function localConnected() { return !!session && session.expires > Date.now(); }

const messages: Record<string, string> = {
  pairing_required: '配对码无效或会话过期，请重新启动本机代理并配对。',
  pairing_rate_limited: '配对尝试过多，请稍后重试。',
  origin_denied: '代理允许的工作台地址与当前页面不一致。',
  source_unavailable: '本机 Zotero 找不到此附件文件。',
  account_mismatch: '本机 Zotero 账号与此文献来源不一致。',
  parent_mismatch: '附件所属论文不匹配，未导入。',
  source_parent_unresolved: '无法确认来源论文关系，请先重新导入该 Zotero 条目的元数据。',
  linked_file_unsupported: '暂不支持 Zotero 链接文件，请在文献文件页手动上传 PDF。',
  size_limit: '文件超过 50 MiB，请使用服务端获取方式。',
  source_changed: '本机附件在读取时发生变化，请重试。',
  source_checksum_mismatch: '文件校验与来源记录不一致，请核对附件版本。',
  source_descriptor_changed: '来源记录已变化，请重新发起导入。',
  intent_expired: '传输已过期，请重试。',
  owned_content_differs: '已有受管副本与本机文件不同，保留现有副本；请作为新版本人工审核上传。',
  invalid_pdf: '文件不是可读取的 PDF。',
  not_pdf: '此附件不是 PDF。',
};
export function localError(error: unknown) {
  const code = error instanceof ApiError ? error.code || error.message : error instanceof Error ? error.message : 'unknown';
  return messages[code] || (code === 'agent_unreachable' ? '无法连接本机代理或浏览器阻止了本地访问。请启动代理并检查浏览器本地网络权限；也可在文献文件页手动上传 PDF。' : `本机导入失败：${code}`);
}

async function agentRequest(path: string, body: unknown, token?: string) {
  let response: Response;
  try {
    response = await fetch(`${agentUrl}/v1/${path}`, { method: 'POST', headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) }, body: JSON.stringify(body), signal: AbortSignal.timeout(120000), credentials: 'omit', redirect: 'error' });
  } catch { throw new Error('agent_unreachable'); }
  if (!response.ok) {
    if (response.status === 401) session = null;
    throw new Error((await response.json()).error || 'agent_unreachable');
  }
  return response;
}

export async function pairLocal(code: string) {
  const result = await (await agentRequest('pair', { code })).json();
  session = { token: result.token, expires: Date.now() + result.expires_in * 1000 };
}

export async function disconnectLocal() {
  const token = session?.token;
  session = null;
  if (token) await agentRequest('disconnect', {}, token);
}

async function boundedBlob(response: Response): Promise<Blob> {
  if (!response.body) throw new Error('source_unavailable');
  const reader = response.body.getReader();
  const chunks: BlobPart[] = [];
  let size = 0;
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > maxBytes) throw new Error('size_limit');
      chunks.push(new Uint8Array(value).buffer);
    }
    return new Blob(chunks, { type: 'application/pdf' });
  } finally { await reader.cancel(); reader.releaseLock(); }
}

export async function recoverLocal(paperId: string, assetId: string): Promise<AssetAcquisition> {
  if (!localConnected()) throw new Error('pairing_required');
  const token = session!.token;
  const base = `/api/literature/papers/${encodeURIComponent(paperId)}/assets/${encodeURIComponent(assetId)}`;
  const intent = await postJson<{ intent: string; source: Record<string, string> }>(`${base}/local-intent`);
  const exported = await agentRequest('export', intent.source, token);
  const observation = exported.headers.get('X-Zotero-Observation');
  if (!observation) throw new Error('invalid_observation');
  const pdf = await boundedBlob(exported);
  const response = await fetch(`${base}/local-transfer`, { method: 'POST', headers: { 'Content-Type': 'application/pdf', 'X-Transfer-Intent': intent.intent, 'X-Zotero-Observation': observation }, body: pdf, signal: AbortSignal.timeout(120000) });
  const result = await response.json();
  if (!response.ok) throw new Error(result.detail?.code || 'transfer_failed');
  return result;
}

export async function recoverLocalPaper(paperId: string): Promise<AssetAcquisition[]> {
  const { items } = await getJson<AttachmentsResponse>(`/api/literature/papers/${encodeURIComponent(paperId)}/attachments`);
  const results: AssetAcquisition[] = [];
  for (const file of items.filter(f => f.active && f.storage_kind === 'zotero' && f.downloadable && f.content_type === 'application/pdf')) {
    try { results.push(await recoverLocal(paperId, file.id)); }
    catch (error) { results.push({ source_asset_id: file.id, status: 'failed', filename: file.filename, error: localError(error) }); }
  }
  return results;
}
