import {
  ArrowLeft,
  ChevronLeft,
  ChevronRight,
  Download,
  Maximize2,
  Minus,
  NotebookPen,
  Plus,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { getDocument, GlobalWorkerOptions } from "pdfjs-dist";
import type { PDFDocumentProxy, RenderTask } from "pdfjs-dist";
import pdfWorkerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import { getJson } from "./api";
import type { NotesResponse, PaperDetailResponse } from "./types";

GlobalWorkerOptions.workerSrc = pdfWorkerUrl;

export function PdfReaderPage({ paperId }: { paperId: string }) {
  const [detail, setDetail] = useState<PaperDetailResponse | null>(null);
  const [notes, setNotes] = useState<NotesResponse["items"]>([]);
  const [document, setDocument] = useState<PDFDocumentProxy | null>(null);
  const [pageNumber, setPageNumber] = useState(1);
  const [pageInput, setPageInput] = useState("1");
  const [zoom, setZoom] = useState(1);
  const [fitPage, setFitPage] = useState(true);
  const [notesOpen, setNotesOpen] = useState(true);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [fitRevision, setFitRevision] = useState(0);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const pageAreaRef = useRef<HTMLDivElement>(null);

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
    ])
      .then(async ([paperDetail, noteResponse]) => {
        if (cancelled) return;
        setDetail(paperDetail);
        setNotes(noteResponse.items);
        if (!paperDetail.pdf_available) throw new Error("PDF unavailable");
        loadingTask = getDocument({ url: pdfUrl });
        const pdfDocument = await loadingTask.promise;
        if (!cancelled) setDocument(pdfDocument);
      })
      .catch(() => {
        if (!cancelled) setError("This PDF is unavailable from the configured Zotero provider.");
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
      renderTask = page.render({
        canvas,
        canvasContext: context,
        viewport,
        transform: outputScale === 1 ? undefined : [outputScale, 0, 0, outputScale, 0, 0],
      });
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

  return (
    <main className={`pdf-reader ${notesOpen ? "notes-open" : ""}`}>
      <header className="reader-header">
        <a className="reader-back" href="/">
          <ArrowLeft size={16} aria-hidden="true" />
          Library
        </a>
        <div className="reader-title">
          <strong>{detail?.paper.title ?? "PDF Reader"}</strong>
          <span>{document ? `${document.numPages} pages` : "Loading document"}</span>
        </div>
        <div className="reader-actions">
          <button className="reader-button" type="button" onClick={() => setNotesOpen((value) => !value)}>
            <NotebookPen size={15} aria-hidden="true" />
            Notes
          </button>
          <a className="reader-button" href={downloadUrl}>
            <Download size={15} aria-hidden="true" />
            Download
          </a>
        </div>
      </header>

      <div className="reader-toolbar" aria-label="PDF controls">
        <button type="button" disabled={!document || pageNumber <= 1} onClick={() => setPageNumber((value) => value - 1)} aria-label="Previous page"><ChevronLeft size={16} /></button>
        <label className="page-jump">
          <input value={pageInput} onChange={(event) => setPageInput(event.target.value)} onBlur={goToPage} onKeyDown={(event) => { if (event.key === "Enter") goToPage(); }} aria-label="Page number" />
          <span>/ {document?.numPages ?? "–"}</span>
        </label>
        <button type="button" disabled={!document || pageNumber >= document.numPages} onClick={() => setPageNumber((value) => value + 1)} aria-label="Next page"><ChevronRight size={16} /></button>
        <span className="toolbar-divider" />
        <button type="button" onClick={() => changeZoom(zoom - 0.15)} aria-label="Zoom out"><Minus size={16} /></button>
        <span className="zoom-label">{fitPage ? "Fit" : `${Math.round(zoom * 100)}%`}</span>
        <button type="button" onClick={() => changeZoom(zoom + 0.15)} aria-label="Zoom in"><Plus size={16} /></button>
        <button className={fitPage ? "active" : ""} type="button" onClick={() => setFitPage(true)} title="Fit page width" aria-label="Fit page width"><Maximize2 size={15} /></button>
      </div>

      <section className="reader-page-area" ref={pageAreaRef} aria-label="PDF page">
        {loading ? <ReaderState title="Loading PDF" detail="Fetching the PDF through the Workbench API." /> : null}
        {error ? <ReaderState title="PDF unavailable" detail={error} /> : null}
        {!loading && !error ? <canvas ref={canvasRef} className="pdf-canvas" /> : null}
      </section>

      {notesOpen ? (
        <aside className="reader-notes" aria-label="Zotero Notes">
          <div className="reader-notes-heading">
            <strong>Zotero Notes</strong>
            <span>Read only</span>
          </div>
          <div className="reader-notes-scroll">
            {notes.length > 0 ? notes.map((note) => (
              <article className="reader-note-card" key={note.id}>
                <span>{note.kind === "annotation" ? `Annotation${note.page_label ? ` · p. ${note.page_label}` : ""}` : "Note"}</span>
                <p>{plainNoteText(note.content) || "Empty note"}</p>
              </article>
            )) : <ReaderState title="No Notes" detail="This paper has no synced Zotero Notes." />}
          </div>
        </aside>
      ) : null}
    </main>
  );
}

function ReaderState({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="reader-state">
      <strong>{title}</strong>
      <p>{detail}</p>
    </div>
  );
}

function plainNoteText(content: string) {
  const document = new DOMParser().parseFromString(content, "text/html");
  return document.body.textContent?.trim() ?? "";
}
