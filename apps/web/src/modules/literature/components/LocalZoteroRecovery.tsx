import { useState } from 'react';
import { localError, recoverLocal } from '../localZotero';
import { literatureLabel } from '../labels';
import type { Attachment } from '../types';
import { LocalZoteroConnection } from './LocalZoteroConnection';

export function LocalZoteroRecovery({ paperId, files, onChanged }: { paperId: string; files: Attachment[]; onChanged: () => void }) {
  const [selected, setSelected] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const eligible = files.filter(f => f.active && f.storage_kind === 'zotero' && f.downloadable && f.content_type === 'application/pdf');
  if (!eligible.length) return null;
  return <details><summary>从当前电脑的 Zotero 补充 PDF</summary>
    <LocalZoteroConnection busy={busy} />
    <label>本机恢复附件<select value={selected} disabled={busy} onChange={e => setSelected(e.target.value)}><option value="">选择要恢复的 PDF</option>{eligible.map(f => <option value={f.id} key={f.id}>{f.filename} · {literatureLabel(f.role)}</option>)}</select></label>
    <button disabled={busy || !selected} onClick={() => {
      setBusy(true); setMessage('正在读取本机附件并上传…');
      void recoverLocal(paperId, selected).then(r => { setMessage(literatureLabel(r.status)); onChanged(); }).catch(e => setMessage(localError(e))).finally(() => setBusy(false));
    }}>{busy ? '正在补充…' : '从本机获取 / 重试所选 PDF'}</button>
    {message && <p role="status">{message}</p>}
    <p>下面的“获取 / 重试这个源 PDF”使用 API 服务端的 Zotero；本机恢复失败时也可在本页手动上传。</p>
  </details>;
}
