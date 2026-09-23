import { useEffect, useState } from "react";
import { getJson, workflowError } from "../api";
import { literatureLabel } from "../labels";
import type { Attachment } from "../types";

type Inspection = { asset_id: string; state: string; size_bytes: number | null; sha256: string | null; owned_asset_id?: string | null; acquisition_error?: string | null };
export function AssetIntegrity({ paperId, files }: { paperId: string; files: Attachment[] }) {
  const [items, setItems] = useState<Inspection[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let current = true; setLoading(true);
    getJson<{ items: Inspection[] }>(`/api/literature/papers/${encodeURIComponent(paperId)}/assets/integrity`).then((result) => { if (current) { setItems(result.items); setError(""); } }).catch((e) => { if (current) setError(workflowError(e)); }).finally(() => { if (current) setLoading(false); });
    return () => { current = false; };
  }, [paperId, files]);
  return <section className="wb-asset-integrity"><h4>文件完整性</h4>{loading && <p role="status">正在校验本地文件…</p>}{error && <p role="alert">{error}</p>}{items.map((item) => <article key={item.asset_id}><p>{files.find((file) => file.id === item.asset_id)?.filename ?? item.asset_id} · {literatureLabel(item.state)}{item.size_bytes != null ? ` · ${item.size_bytes.toLocaleString()} 字节` : ""}{item.sha256 && <small> · SHA-256: {item.sha256}</small>}</p>{item.acquisition_error && <p className="wb-warning">最近获取结果：{literatureLabel(item.acquisition_error)}</p>}{item.state === 'owned_copy' && item.owned_asset_id && <a href={`/api/literature/papers/${encodeURIComponent(paperId)}/pdf?asset_id=${encodeURIComponent(item.owned_asset_id)}`} target="_blank" rel="noreferrer">打开已校验副本</a>}</article>)}</section>;
}
