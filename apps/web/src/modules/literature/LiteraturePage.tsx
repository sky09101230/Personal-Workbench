import { literatureLabel } from "./labels";
import { useEffect, useState } from "react";
import { getJson, postJson, workflowError } from "./api";
import { PaperDetail } from "./components/PaperDetail";
import { ImportCenter } from "./components/ImportCenter";
import { IdentityConflictQueue } from "./components/IdentityReview";
import { RadarInbox } from "../news/components/RadarInbox";
import type { Collection, CollectionsResponse, FiltersResponse, LiteratureStatus, PapersResponse } from "./types";
import "../news/news.css";
import "./literature.css";

const emptyFilters = { query: "", author: "", year: "", journal: "", tag: "", reading_status: "", collection_id: "" };
export function LiteraturePage({ status, apiError, onStatusReload }: { status: LiteratureStatus | null; apiError: boolean; onStatusReload: () => Promise<void> }) {
  const [view, setView] = useState("library");
  const [paperId, setPaperId] = useState(new URLSearchParams(location.search).get("paper"));
  const [filters, setFilters] = useState(emptyFilters);
  const [facets, setFacets] = useState<FiltersResponse>({ years: [], journals: [], tags: [] });
  const [collections, setCollections] = useState<Collection[]>([]);
  const [data, setData] = useState<PapersResponse>({ items: [], total: 0, library_version: null });
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [revision, setRevision] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [metadataError, setMetadataError] = useState("");
  const [name, setName] = useState("");
  const [creating, setCreating] = useState(false);
  const refresh = () => setRevision((n) => n + 1);
  const open = (id: string | null) => {
    setPaperId(id); setView("library");
    const url = new URL(location.href);
    if (id) url.searchParams.set("paper", id); else url.searchParams.delete("paper");
    history.pushState({}, "", url);
  };
  useEffect(() => { const pop = () => { setPaperId(new URLSearchParams(location.search).get("paper")); setView("library"); }; window.addEventListener("popstate", pop); return () => window.removeEventListener("popstate", pop); }, []);
  useEffect(() => {
    let active = true;
    Promise.all([getJson<CollectionsResponse>("/api/literature/collections"), getJson<FiltersResponse>("/api/literature/filters"), getJson<PapersResponse>("/api/literature/papers?limit=1")])
      .then(([c, f, p]) => { if (active) { setCollections(c.items); setFacets(f); setTotal(p.total); setMetadataError(""); } })
      .catch((e) => { if (active) setMetadataError(workflowError(e)); });
    return () => { active = false; };
  }, [revision]);
  useEffect(() => {
    let active = true; setLoading(true);
    const timer = window.setTimeout(() => {
      const query = new URLSearchParams({ limit: "25", offset: String(offset) });
      Object.entries(filters).forEach(([key, value]) => { if (value.trim()) query.set(key, value.trim()); });
      getJson<PapersResponse>("/api/literature/papers?" + query).then((result) => { if (active) { setData(result); setError(""); } })
        .catch((e) => { if (active) setError(workflowError(e)); }).finally(() => { if (active) setLoading(false); });
    }, 200);
    return () => { active = false; window.clearTimeout(timer); };
  }, [filters, offset, revision]);
  const filter = (key: keyof typeof filters, value: string) => { setFilters((current) => ({ ...current, [key]: value })); setOffset(0); };
  return <section className="literature-page wb-library" id="literature">
    <header className="wb-heading"><div><span className="wb-eyebrow">PERSONAL WORKBENCH</span><h1>文献库</h1><p>管理你的论文、本地文件和研究笔记。</p></div><button onClick={() => setView("import")}>导入文献</button></header>
    <nav className="library-tabs" aria-label="文献工作台导航">{["library", "radar", "import"].map((tab) => <button key={tab} aria-pressed={view === tab} className={view === tab ? "active" : ""} onClick={() => { setView(tab); if (tab === "library") { open(null); refresh(); } }}>{literatureLabel(tab)}</button>)}</nav>
    <div className="wb-body">
      {view === "radar" && <RadarInbox />}
      <div hidden={view !== "import"}><ImportCenter providerReady={status?.provider_configured ?? false} onImported={(id) => { open(id); refresh(); }} /></div>
      {view === "library" && (paperId ? <PaperDetail key={paperId} paperId={paperId} onBack={() => open(null)} onChanged={refresh} /> : <>
        <div className="wb-summary"><span><strong>{metadataError ? "—" : total}</strong> 篇正式文献</span><span><strong>{metadataError ? "—" : collections.length}</strong> 个本地集合</span><span>由 Workbench 管理的文献库</span><button onClick={() => { refresh(); void onStatusReload(); }}>刷新</button></div>
        {(error || metadataError || apiError) && <p role="alert" className="wb-error">{error || metadataError || "无法连接 Workbench API，请检查后端服务。"} <button onClick={() => { refresh(); void onStatusReload(); }}>重试</button></p>}
        <IdentityConflictQueue onChanged={refresh} />
        <div className="wb-filters"><label className="wb-search">搜索文献库<input type="search" placeholder="标题、关键词或标识符" value={filters.query} onChange={(e) => filter("query", e.target.value)} /></label>
          <label>阅读状态<select value={filters.reading_status} onChange={(e) => filter("reading_status", e.target.value)}><option value="">全部状态</option>{["inbox", "saved", "reading", "read", "archived"].map((value) => <option key={value} value={value}>{literatureLabel(String(value))}</option>)}</select></label>
          <label>本地集合<select value={filters.collection_id} onChange={(e) => filter("collection_id", e.target.value)}><option value="">全部集合</option>{collections.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></label>
          <label>年份<select value={filters.year} onChange={(e) => filter("year", e.target.value)}><option value="">全部年份</option>{facets.years.map((value) => <option key={value} value={value}>{literatureLabel(String(value))}</option>)}</select></label>
        </div>
        <details className="wb-filter-more"><summary>更多筛选与集合管理</summary><div className="wb-filters"><label>作者<input value={filters.author} onChange={(e) => filter("author", e.target.value)} /></label>{(["journal", "tag"] as const).map((key) => <label key={key}>{literatureLabel(key)}<select value={filters[key]} onChange={(e) => filter(key, e.target.value)}><option value="">全部</option>{(key === "journal" ? facets.journals : facets.tags).map((value) => <option key={value} value={value}>{literatureLabel(String(value))}</option>)}</select></label>)}
          <form onSubmit={(e) => { e.preventDefault(); setCreating(true); void postJson("/api/literature/collections", { name: name.trim() }).then(() => { setName(""); refresh(); }).catch((e) => setMetadataError(workflowError(e))).finally(() => setCreating(false)); }}><label>新建本地集合<input required maxLength={200} value={name} onChange={(e) => setName(e.target.value)} /></label><button disabled={creating || !name.trim()}>创建</button></form></div></details>
        <div className="wb-section-heading"><h2>正式文献 <small>· {error ? "—" : data.total} 篇匹配</small></h2><button onClick={() => { setFilters(emptyFilters); setOffset(0); }}>清空筛选</button></div>
        {loading ? <p role="status">正在加载文献库…</p> : error ? null : !data.items.length ? <div className="wb-empty"><h3>{total ? "没有匹配的文献" : "开始建立你的文献库"}</h3><p>{total ? "调整筛选条件以查找文献。" : "导入 PDF、选择 Zotero 条目，或保存雷达中发现的论文。"}</p><button onClick={() => setView("import")}>导入文献</button></div> : <div className="wb-paper-list">{data.items.map((paper) => <article className="wb-paper" key={paper.id}><div><button className="wb-paper-title" onClick={() => open(paper.id)}>{paper.title || "未命名文献"}</button><p>{paper.authors.join(" · ") || "未记录作者"}</p><small>{[paper.journal, paper.year].filter(Boolean).join(" · ") || "未记录出版信息"}</small><div className="wb-paper-provenance"><span>外部来源：{paper.sources.join(", ") || "无"}</span><span>入库途径：{paper.origins?.map(literatureLabel).join("、") || "未记录"}</span></div></div><div className="wb-paper-state"><span className="wb-badge">{literatureLabel(paper.reading_status)}</span><span>{paper.pdf_available ? "有 PDF" : "无 PDF"}</span><span className={paper.metadata_status === "complete" ? "" : "wb-warning"}>元数据：{literatureLabel(paper.metadata_status)}</span>{paper.tags.length > 0 && <small>{paper.tags.join(" · ")}</small>}</div></article>)}</div>}
        <nav className="wb-actions" aria-label="文献分页"><button disabled={loading || offset === 0} onClick={() => setOffset(Math.max(0, offset - 25))}>上一页</button><span>{data.total ? offset + 1 : 0}–{Math.min(offset + 25, data.total)} / {data.total}</span><button disabled={loading || offset + 25 >= data.total} onClick={() => setOffset(offset + 25)}>下一页</button></nav>
      </>)}
    </div>
  </section>;
}
