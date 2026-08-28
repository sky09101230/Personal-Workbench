import {
  ArrowLeft,
  Bot,
  ChevronLeft,
  ChevronRight,
  Download,
  Maximize2,
  Minus,
  NotebookPen,
  Plus,
  Save,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { CSSProperties } from "react";
import { getDocument, GlobalWorkerOptions, Util } from "pdfjs-dist";
import type { PDFDocumentProxy, RenderTask } from "pdfjs-dist";
import pdfWorkerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import { getJson, postJson } from "./api";
import { LiteratureAIAssistant } from "./components/LiteratureAIAssistant";
import type {
  LiteratureUserNote,
  NotesResponse,
  PaperDetailResponse,
  PdfSelection,
  UserNoteListResponse,
} from "./types";

GlobalWorkerOptions.workerSrc = pdfWorkerUrl;

type SidebarTab = "zotero" | "my-notes" | "ai";
type RenderedTextItem = { key: string; text: string; style: CSSProperties };

export function PdfReaderPage({ paperId }: { paperId: string }) {
  const [detail, setDetail] = useState<PaperDetailResponse | null>(null);
  const [notes, setNotes] = useState<NotesResponse["items"]>([]);
  const [userNotes, setUserNotes] = useState<LiteratureUserNote[]>([]);
  const [document, setDocument] = useState<PDFDocumentProxy | null>(null);
  const [pageNumber, setPageNumber] = useState(1);
  const [pageInput, setPageInput] = useState("1");
  const [zoom, setZoom] = useState(1);
  const [fitPage, setFitPage] = useState(true);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [sidebarTab, setSidebarTab] = useState<SidebarTab>("zotero");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [fitRevision, setFitRevision] = useState(0);
  const [textItems, setTextItems] = useState<RenderedTextItem[]>([]);
  const [pageSize, setPageSize] = useState({ width: 0, height: 0 });
  const [selection, setSelection] = useState<PdfSelection | null>(null);
  const [manualNote, setManualNote] = useState("");
  const [savingNote, setSavingNote] = useState(false);
  const [noteError, setNoteError] = useState<string | null>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const textLayerRef = useRef<HTMLDivElement>(null);
  const pageAreaRef = useRef<HTMLDivElement>(null);
  const pageTextRef = useRef("");

  const encodedPaperId = encodeURIComponent(paperId);
  const pdfUrl = `/api/literature/papers/${encodedPaperId}/pdf`;
  const downloadUrl = `/api/literature/papers/${encodedPaperId}/pdf/download`;

  useEffect(() => {
    let cancelled = false;
    let loadingTask: ReturnType<typeof getDocument> | null = null;
    setLoading(true);
    setError(null);
    Promise.all([
      getJson<PaperDetailResponse>(`/api/literature/papers/${encodedPaperId}`),
      getJson<NotesResponse>(`/api/literature/papers/${encodedPaperId}/notes`),
      getJson<UserNoteListResponse>(`/api/literature/papers/${encodedPaperId}/user-notes`).catch(() => {
        if (!cancelled) setNoteError("My Notes could not be loaded; PDF reading remains available.");
        return { items: [] };
      }),
    ])
      .then(async ([paperDetail, noteResponse, userNoteResponse]) => {
        if (cancelled) return;
        setDetail(paperDetail);
        setNotes(noteResponse.items);
        setUserNotes(userNoteResponse.items);
        if (!paperDetail.pdf_available) throw new Error("PDF unavailable");
        loadingTask = getDocument({ url: pdfUrl });
        const pdfDocument = await loadingTask.promise;
        if (!cancelled) setDocument(pdfDocument);
      })
      .catch(() => {
        if (!cancelled) setError("This paper or PDF is unavailable from the configured provider.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
      void loadingTask?.destroy();
    };
  }, [encodedPaperId, pdfUrl]);

  useEffect(() => {
    const pageArea = pageAreaRef.current;
    if (!pageArea) return;
    const observer = new ResizeObserver(() => setFitRevision((value) => value + 1));
    observer.observe(pageArea);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!document || !canvasRef.current || !pageAreaRef.current) return;
    let cancelled = false;
    let renderTask: RenderTask | null = null;
    setTextItems([]);
    setSelection(null);
    const render = async () => {
      const page = await document.getPage(pageNumber);
      if (cancelled || !canvasRef.current || !pageAreaRef.current) return;
      const baseViewport = page.getViewport({ scale: 1 });
      const availableWidth = Math.max(240, pageAreaRef.current.clientWidth - 56);
      const pageScale = fitPage ? availableWidth / baseViewport.width : zoom;
      const viewport = page.getViewport({ scale: pageScale });
      const outputScale = window.devicePixelRatio || 1;
      const canvas = canvasRef.current;
      const context = canvas.getContext("2d");
      if (!context) return;
      canvas.width = Math.floor(viewport.width * outputScale);
      canvas.height = Math.floor(viewport.height * outputScale);
      canvas.style.width = `${Math.floor(viewport.width)}px`;
      canvas.style.height = `${Math.floor(viewport.height)}px`;
      setPageSize({ width: viewport.width, height: viewport.height });
      renderTask = page.render({
        canvas,
        canvasContext: context,
        viewport,
        transform: outputScale === 1 ? undefined : [outputScale, 0, 0, outputScale, 0, 0],
      });
      const textContent = await page.getTextContent();
      const renderedItems = textContent.items.flatMap((item, index) => {
        if (!("str" in item) || !("transform" in item) || !item.str) return [];
        const transform = Util.transform(viewport.transform, item.transform);
        const angle = Math.atan2(transform[1], transform[0]);
        const fontHeight = Math.hypot(transform[2], transform[3]);
        const width = "width" in item ? item.width * pageScale : undefined;
        return [{
          key: `${pageNumber}-${index}`,
          text: item.str,
          style: {
            left: transform[4],
            top: transform[5] - fontHeight,
            fontSize: fontHeight,
            width,
            transform: `rotate(${angle}rad)`,
          },
        }];
      });
      pageTextRef.current = normalizeText(renderedItems.map((item) => item.text).join(" "));
      if (!cancelled) setTextItems(renderedItems);
      await renderTask.promise;
    };
    void render().catch((renderError: unknown) => {
      if (!cancelled && !(renderError instanceof Error && renderError.name === "RenderingCancelledException")) {
        setError("The PDF page could not be rendered.");
      }
    });
    return () => {
      cancelled = true;
      renderTask?.cancel();
    };
  }, [document, fitPage, fitRevision, pageNumber, zoom]);

  useEffect(() => setPageInput(String(pageNumber)), [pageNumber]);

  const goToPage = () => {
    if (!document) return;
    const requested = Number.parseInt(pageInput, 10);
    if (Number.isFinite(requested)) {
      setPageNumber(Math.min(document.numPages, Math.max(1, requested)));
    } else {
      setPageInput(String(pageNumber));
    }
  };

  const changeZoom = (next: number) => {
    setFitPage(false);
    setZoom(Math.min(3, Math.max(0.5, next)));
  };

  const showSidebar = (tab: SidebarTab) => {
    if (sidebarOpen && sidebarTab === tab) {
      setSidebarOpen(false);
      return;
    }
    setSidebarTab(tab);
    setSidebarOpen(true);
  };

  const captureSelection = () => {
    const browserSelection = window.getSelection();
    const layer = textLayerRef.current;
    if (!browserSelection || browserSelection.rangeCount === 0 || !layer) return;
    if (!layer.contains(browserSelection.anchorNode) || !layer.contains(browserSelection.focusNode)) return;
    const selectedText = normalizeText(browserSelection.toString());
    if (!selectedText) return;
    const pageText = pageTextRef.current;
    const offset = pageText.indexOf(selectedText);
    setSelection({
      pageNumber,
      selectedText: selectedText.slice(0, 8_000),
      contextBefore: offset >= 0 ? pageText.slice(Math.max(0, offset - 2_000), offset) : "",
      contextAfter: offset >= 0 ? pageText.slice(offset + selectedText.length, offset + selectedText.length + 2_000) : "",
    });
  };

  const saveManualNote = async () => {
    const content = manualNote.trim();
    if (!content) return;
    setSavingNote(true);
    setNoteError(null);
    try {
      const note = await postJson<LiteratureUserNote>(
        `/api/literature/papers/${encodedPaperId}/user-notes`,
        { content },
      );
      setUserNotes((items) => [note, ...items]);
      setManualNote("");
    } catch {
      setNoteError("The local note could not be saved.");
    } finally {
      setSavingNote(false);
    }
  };

  return (
    <main className={`pdf-reader ${sidebarOpen ? "notes-open" : ""}`}>
      <header className="reader-header">
        <a className="reader-back" href="/"><ArrowLeft size={16} aria-hidden="true" />Library</a>
        <div className="reader-title">
          <strong>{detail?.paper.title ?? "PDF Reader"}</strong>
          <span>{document ? `${document.numPages} pages` : "Loading document"}</span>
        </div>
        <div className="reader-actions">
          <button className="reader-button" type="button" onClick={() => showSidebar("zotero")}><NotebookPen size={15} />Notes</button>
          <button className="reader-button" type="button" onClick={() => showSidebar("ai")}><Bot size={15} />AI</button>
          <a className="reader-button" href={downloadUrl}><Download size={15} />Download</a>
        </div>
      </header>

      <div className="reader-toolbar" aria-label="PDF controls">
        <button type="button" disabled={!document || pageNumber <= 1} onClick={() => setPageNumber((value) => value - 1)} aria-label="Previous page"><ChevronLeft size={16} /></button>
        <label className="page-jump"><input value={pageInput} onChange={(event) => setPageInput(event.target.value)} onBlur={goToPage} onKeyDown={(event) => { if (event.key === "Enter") goToPage(); }} aria-label="Page number" /><span>/ {document?.numPages ?? "–"}</span></label>
        <button type="button" disabled={!document || pageNumber >= document.numPages} onClick={() => setPageNumber((value) => value + 1)} aria-label="Next page"><ChevronRight size={16} /></button>
        <span className="toolbar-divider" />
        <button type="button" onClick={() => changeZoom(zoom - 0.15)} aria-label="Zoom out"><Minus size={16} /></button>
        <span className="zoom-label">{fitPage ? "Fit" : `${Math.round(zoom * 100)}%`}</span>
        <button type="button" onClick={() => changeZoom(zoom + 0.15)} aria-label="Zoom in"><Plus size={16} /></button>
        <button className={fitPage ? "active" : ""} type="button" onClick={() => setFitPage(true)} title="Fit page width" aria-label="Fit page width"><Maximize2 size={15} /></button>
        {selection ? <span className="selection-status">Selected · p. {selection.pageNumber}</span> : null}
      </div>

      <section className="reader-page-area" ref={pageAreaRef} aria-label="PDF page">
        {loading ? <ReaderState title="Loading PDF" detail="Fetching the PDF through the Workbench API." /> : null}
        {error ? <ReaderState title="Reader unavailable" detail={error} /> : null}
        {!loading && !error ? (
          <div className="pdf-page-stack" style={{ width: pageSize.width, height: pageSize.height }} onMouseUp={captureSelection}>
            <canvas ref={canvasRef} className="pdf-canvas" />
            <div ref={textLayerRef} className="pdf-text-layer" aria-label="Selectable PDF text">
              {textItems.map((item) => <span key={item.key} style={item.style}>{item.text} </span>)}
            </div>
          </div>
        ) : null}
      </section>

      {sidebarOpen ? (
        <aside className="reader-notes reader-sidebar" aria-label="Paper reading sidebar">
          <div className="reader-sidebar-tabs" role="tablist">
            <button className={sidebarTab === "zotero" ? "active" : ""} type="button" onClick={() => setSidebarTab("zotero")}>Zotero Notes</button>
            <button className={sidebarTab === "my-notes" ? "active" : ""} type="button" onClick={() => setSidebarTab("my-notes")}>My Notes</button>
            <button className={sidebarTab === "ai" ? "active" : ""} type="button" onClick={() => setSidebarTab("ai")}>AI Assistant</button>
          </div>
          <div className="reader-notes-scroll">
            {sidebarTab === "zotero" ? (
              notes.length > 0 ? notes.map((note) => (
                <article className="reader-note-card" key={note.id}>
                  <span>{note.kind === "annotation" ? `Annotation${note.page_label ? ` · p. ${note.page_label}` : ""}` : "Zotero Note"}</span>
                  <p>{plainNoteText(note.content) || "Empty note"}</p>
                </article>
              )) : <ReaderState title="No Zotero Notes" detail="This paper has no synced Zotero Notes." />
            ) : null}
            {sidebarTab === "my-notes" ? (
              <div className="my-notes">
                {noteError ? <div className="ai-error" role="alert"><span>{noteError}</span><button type="button" onClick={() => setNoteError(null)}>Dismiss</button></div> : null}
                <textarea value={manualNote} onChange={(event) => setManualNote(event.target.value)} rows={4} placeholder="Write a local note…" />
                <button className="ai-trigger" type="button" disabled={!manualNote.trim() || savingNote} onClick={() => void saveManualNote()}><Save size={14} />{savingNote ? "Saving…" : "Add Note"}</button>
                {userNotes.length > 0 ? userNotes.map((note) => (
                  <article className="reader-note-card" key={note.id}><span>{userNoteLabel(note.source)}</span><p>{note.content}</p></article>
                )) : <ReaderState title="No My Notes" detail="Manual notes and explicitly saved AI results appear here." />}
              </div>
            ) : null}
            {sidebarTab === "ai" ? <LiteratureAIAssistant paperId={paperId} selection={selection} onNoteAdded={(note) => setUserNotes((items) => [note, ...items])} /> : null}
          </div>
        </aside>
      ) : null}
    </main>
  );
}

function ReaderState({ title, detail }: { title: string; detail: string }) {
  return <div className="reader-state"><strong>{title}</strong><p>{detail}</p></div>;
}

function plainNoteText(content: string) {
  const document = new DOMParser().parseFromString(content, "text/html");
  return document.body.textContent?.trim() ?? "";
}

function normalizeText(value: string) {
  return value.replace(/\s+/g, " ").trim();
}

function userNoteLabel(source: LiteratureUserNote["source"]) {
  if (source === "manual") return "My Note";
  if (source === "ai_overview") return "Saved from AI Overview";
  if (source === "ai_deep_read") return "Saved from AI Deep Read";
  if (source === "ai_chat") return "Saved from Ask Paper";
  return "Saved from PDF Selection";
}
