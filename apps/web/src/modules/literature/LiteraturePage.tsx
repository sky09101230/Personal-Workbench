import { useEffect, useState } from "react";
import { getJson, postJson, workflowError } from "./api";
import { PaperDetail } from "./components/PaperDetail";
import { ImportCenter } from "./components/ImportCenter";
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
    <header className="wb-heading"><div><span className="wb-eyebrow">PERSONAL WORKBENCH</span><h1>Literature Library</h1><p>Your papers, local files and research notes.</p></div><button onClick={() => setView("import")}>Import papers</button></header>
    <nav className="library-tabs" aria-label="Literature views">{["library", "radar", "import"].map((tab) => <button key={tab} aria-pressed={view === tab} className={view === tab ? "active" : ""} onClick={() => { setView(tab); if (tab === "library") { open(null); refresh(); } }}>{tab[0].toUpperCase() + tab.slice(1)}</button>)}</nav>
    <div className="wb-body">
      {view === "radar" && <RadarInbox />}
      <div hidden={view !== "import"}><ImportCenter providerReady={status?.provider_configured ?? false} onImported={(id) => { open(id); refresh(); }} /></div>
      {view === "library" && (paperId ? <PaperDetail key={paperId} paperId={paperId} onBack={() => open(null)} onChanged={refresh} /> : <>
        <div className="wb-summary"><span><strong>{metadataError ? "—" : total}</strong> canonical papers</span><span><strong>{collections.length}</strong> native collections</span><span>Library is owned by Workbench</span><button onClick={() => { refresh(); void onStatusReload(); }}>Refresh</button></div>
        {(apiError || metadataError) && <p role="alert" className="wb-error">{metadataError || "Workbench API unavailable."}</p>}
        <div className="wb-filters"><label className="wb-search">Search library<input type="search" placeholder="Title, keywords or identifier" value={filters.query} onChange={(e) => filter("query", e.target.value)} /></label>
          <label>Reading status<select value={filters.reading_status} onChange={(e) => filter("reading_status", e.target.value)}><option value="">All states</option>{["inbox", "saved", "reading", "read", "archived"].map((value) => <option key={value}>{value}</option>)}</select></label>
          <label>Native collection<select value={filters.collection_id} onChange={(e) => filter("collection_id", e.target.value)}><option value="">All collections</option>{collections.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></label>
          <label>Year<select value={filters.year} onChange={(e) => filter("year", e.target.value)}><option value="">All years</option>{facets.years.map((value) => <option key={value}>{value}</option>)}</select></label>
        </div>
        <details className="wb-filter-more"><summary>More filters & collections</summary><div className="wb-filters"><label>Author<input value={filters.author} onChange={(e) => filter("author", e.target.value)} /></label>{(["journal", "tag"] as const).map((key) => <label key={key}>{key}<select value={filters[key]} onChange={(e) => filter(key, e.target.value)}><option value="">All</option>{(key === "journal" ? facets.journals : facets.tags).map((value) => <option key={value}>{value}</option>)}</select></label>)}
          <form onSubmit={(e) => { e.preventDefault(); setCreating(true); void postJson("/api/literature/collections", { name: name.trim() }).then(() => { setName(""); refresh(); }).catch((e) => setMetadataError(workflowError(e))).finally(() => setCreating(false)); }}><label>New native collection<input required maxLength={200} value={name} onChange={(e) => setName(e.target.value)} /></label><button disabled={creating || !name.trim()}>Create</button></form></div></details>
        <div className="wb-section-heading"><h2>Canonical papers <small>· {data.total} matching</small></h2><button onClick={() => { setFilters(emptyFilters); setOffset(0); }}>Clear filters</button></div>
        {loading ? <p role="status">Loading Library…</p> : error ? <p className="wb-error" role="alert">{error} <button onClick={refresh}>Retry</button></p> : !data.items.length ? <div className="wb-empty"><h3>{total ? "No matching papers" : "Your Library starts here"}</h3><p>{total ? "Adjust the filters to find your papers." : "Import PDFs, choose Zotero items, or save reviewed Radar discoveries."}</p><button onClick={() => setView("import")}>Import papers</button></div> : <div className="wb-paper-list">{data.items.map((paper) => <article className="wb-paper" key={paper.id}><div><button className="wb-paper-title" onClick={() => open(paper.id)}>{paper.title || "Untitled paper"}</button><p>{paper.authors.join(" · ") || "Authors not recorded"}</p><small>{[paper.journal, paper.year].filter(Boolean).join(" · ") || "Publication not recorded"}</small><div className="wb-paper-provenance"><span>Sources: {paper.sources.join(", ") || "None"}</span><span>Origins: {paper.origins?.join(", ") || "None recorded"}</span></div></div><div className="wb-paper-state"><span className="wb-badge">{paper.reading_status}</span><span>{paper.pdf_available ? "PDF available" : "No PDF"}</span><span className={paper.metadata_status === "complete" ? "" : "wb-warning"}>{paper.metadata_status} metadata</span>{paper.tags.length > 0 && <small>{paper.tags.join(" · ")}</small>}</div></article>)}</div>}
        <nav className="wb-actions" aria-label="Library pagination"><button disabled={loading || offset === 0} onClick={() => setOffset(Math.max(0, offset - 25))}>Previous</button><span>{data.total ? offset + 1 : 0}–{Math.min(offset + 25, data.total)} / {data.total}</span><button disabled={loading || offset + 25 >= data.total} onClick={() => setOffset(offset + 25)}>Next</button></nav>
      </>)}
    </div>
  </section>;
}
