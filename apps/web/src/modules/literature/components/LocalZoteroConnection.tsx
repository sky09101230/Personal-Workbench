import { useEffect, useState } from 'react';
import { disconnectLocal, localConnected, localError, pairLocal } from '../localZotero';

export function LocalZoteroConnection({ busy = false }: { busy?: boolean }) {
  const [connected, setConnected] = useState(localConnected());
  const [code, setCode] = useState('');
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => {
    const timer = window.setInterval(() => setConnected(localConnected()), 1000);
    return () => window.clearInterval(timer);
  }, []);
  return <section className="wb-review-item" aria-label="本机 Zotero 连接">
    <h4>本机 Zotero</h4>
    <p>在存有 PDF 的电脑启动 Zotero 代理，再输入它显示的配对码。文件将保存到当前工作台。</p>
    <p>代理允许的工作台地址：<code>{window.location.origin}</code></p>
    {connected ? <><p role="status">本机代理已配对（最长 30 分钟）</p><button disabled={busy || pending} onClick={() => { setError(''); void disconnectLocal().catch(e => setError(localError(e))).finally(() => setConnected(false)); }}>断开本机代理</button></> : <form onSubmit={e => {
      e.preventDefault(); setPending(true); setError('');
      void pairLocal(code.trim()).then(() => { setConnected(true); setCode(''); }).catch(e => setError(localError(e))).finally(() => setPending(false));
    }}><label>本机代理配对码<input type="password" autoComplete="off" value={code} onChange={e => setCode(e.target.value)} disabled={busy || pending} /></label><button disabled={busy || pending || !code.trim()}>{pending ? '正在配对…' : '连接本机 Zotero'}</button></form>}
    {error && <p role="alert">{error}</p>}
  </section>;
}
