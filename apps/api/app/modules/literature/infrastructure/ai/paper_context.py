import io
import math
import re
from collections import Counter
from datetime import datetime, timezone

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.modules.literature.application.ai.ports import LiteratureAIRepository
from app.modules.literature.application.ai.schemas import PaperContext
from app.modules.literature.application.errors import (
    LiteratureAIContextError,
    LiteratureAINoTextError,
    PdfUnavailableError,
    ProviderAuthenticationError,
    ProviderNotConfiguredError,
    ProviderUnavailableError,
)
from app.modules.literature.application.service import LiteratureService
from app.modules.literature.domain.ai_models import (
    LiteratureAIMessage,
    LiteratureAIPaperTextPage,
)
from app.modules.literature.domain.models import Paper


MAX_PDF_BYTES = 50 * 1024 * 1024
OVERVIEW_TEXT_CHARS = 80_000
DEEP_READ_TEXT_CHARS = 160_000
CHUNK_CHARS = 2_000
CHUNK_OVERLAP = 250
MAX_ASK_CHUNKS = 8
MAX_RECENT_MESSAGES = 8
MAX_CONVERSATION_CHARS = 16_000
MAX_TITLE_CHARS = 4_000
MAX_ABSTRACT_CHARS = 30_000
MAX_AUTHORS = 100
MAX_AUTHOR_CHARS = 512
MAX_TAGS = 100
MAX_TAG_CHARS = 256
MAX_JOURNAL_CHARS = 1_000
MAX_DOI_CHARS = 512
MAX_SELECTION_CHARS = 8_000
MAX_SELECTION_NEIGHBOR_CHARS = 2_000
MAX_SELECTION_QUESTION_CHARS = 2_000
EXTRACTOR_VERSION = "pypdf-6-v2-main-pdf"

_LATIN_STOP_WORDS = frozenset(
    {
        "a", "an", "and", "are", "as", "at", "be", "by", "for", "from",
        "how", "in", "is", "it", "of", "on", "or", "that", "the", "this",
        "to", "was", "were", "what", "when", "where", "which", "why", "with",
    }
)
_CJK_STOP_TOKENS = frozenset(
    {
        "的", "了", "是", "在", "和", "与", "或", "对", "中", "这", "那",
        "什么", "如何", "为什么", "是否", "这个", "这些", "那些", "以及", "其中",
    }
)


class PaperContextBuilder:
    def __init__(
        self,
        literature_service: LiteratureService,
        repository: LiteratureAIRepository,
    ) -> None:
        self._literature = literature_service
        self._repository = repository

    def build_analysis_context(self, paper_id: str, *, deep: bool) -> PaperContext:
        detail = self._literature.get_paper(paper_id)
        pages = self._optional_pages(paper_id)
        selected_pages = _representative_pages(
            pages,
            DEEP_READ_TEXT_CHARS if deep else OVERVIEW_TEXT_CHARS,
        )
        if not detail.paper.title.strip() and not detail.paper.abstract and not selected_pages:
            raise LiteratureAIContextError("The paper has no metadata or text context")
        return PaperContext(
            payload={
                "paper": _paper_metadata(detail.paper),
                "context_kind": "deep_read" if deep else "overview",
                "pdf_text_status": "available" if pages else "unavailable",
                "pages": [_page_payload(page) for page in selected_pages],
            }
        )

    def build_ask_context(
        self,
        paper_id: str,
        *,
        question: str,
        messages: tuple[LiteratureAIMessage, ...],
    ) -> PaperContext:
        detail = self._literature.get_paper(paper_id)
        pages = self._optional_pages(paper_id)
        chunks = _relevant_chunks(pages, question)
        recent_messages = _bounded_messages(messages)
        if not detail.paper.abstract and not chunks:
            raise LiteratureAIContextError("The paper has no context available for questions")
        return PaperContext(
            payload={
                "paper": _paper_metadata(detail.paper),
                "question": question,
                "retrieved_chunks": chunks,
                "recent_conversation": recent_messages,
            }
        )

    def build_selection_context(
        self,
        paper_id: str,
        *,
        page_number: int,
        selected_text: str,
        context_before: str,
        context_after: str,
        question: str | None,
    ) -> PaperContext:
        paper = self._literature.get_paper(paper_id).paper
        return PaperContext(
            payload={
                "paper": _paper_metadata(paper),
                "page_number": page_number,
                "selected_text": selected_text[:MAX_SELECTION_CHARS],
                "context_before": context_before[-MAX_SELECTION_NEIGHBOR_CHARS:],
                "context_after": context_after[:MAX_SELECTION_NEIGHBOR_CHARS],
                "question": (
                    question[:MAX_SELECTION_QUESTION_CHARS]
                    if question is not None
                    else None
                ),
            }
        )

    def _optional_pages(self, paper_id: str) -> tuple[LiteratureAIPaperTextPage, ...]:
        try:
            return self._pages(paper_id)
        except (
            PdfUnavailableError,
            ProviderAuthenticationError,
            ProviderNotConfiguredError,
            ProviderUnavailableError,
            LiteratureAINoTextError,
        ):
            return ()

    def _pages(self, paper_id: str) -> tuple[LiteratureAIPaperTextPage, ...]:
        cached = self._repository.list_paper_text(paper_id)
        if cached and all(page.extractor_version == EXTRACTOR_VERSION for page in cached):
            return cached
        provider_file = self._literature.open_pdf(paper_id)
        data = bytearray()
        try:
            for chunk in provider_file.chunks:
                data.extend(chunk)
                if len(data) > MAX_PDF_BYTES:
                    raise LiteratureAIContextError("The PDF exceeds the extraction size limit")
        finally:
            if provider_file.close:
                provider_file.close()

        try:
            pdf = PdfReader(io.BytesIO(data))
            extracted = tuple(
                (page_number, _normalize_text(page.extract_text() or ""))
                for page_number, page in enumerate(pdf.pages, start=1)
            )
        except (PdfReadError, ValueError, OSError) as error:
            raise LiteratureAIContextError("The PDF could not be read for text extraction") from error
        non_empty = tuple((number, text) for number, text in extracted if text)
        if not non_empty:
            raise LiteratureAINoTextError("The PDF has no extractable text layer")
        now = _utc_now()
        pages = tuple(
            LiteratureAIPaperTextPage(
                paper_id=paper_id,
                page_number=number,
                text=text,
                extractor_version=EXTRACTOR_VERSION,
                created_at=now,
                updated_at=now,
            )
            for number, text in non_empty
        )
        self._repository.replace_paper_text(paper_id, pages)
        return pages


def _paper_metadata(paper: Paper) -> dict[str, object]:
    return {
        "title": paper.title[:MAX_TITLE_CHARS],
        "authors": [
            author[:MAX_AUTHOR_CHARS] for author in paper.authors[:MAX_AUTHORS]
        ],
        "abstract": (
            paper.abstract[:MAX_ABSTRACT_CHARS]
            if paper.abstract is not None
            else None
        ),
        "year": paper.year,
        "journal": (
            paper.journal[:MAX_JOURNAL_CHARS] if paper.journal is not None else None
        ),
        "doi": paper.doi[:MAX_DOI_CHARS] if paper.doi is not None else None,
        "tags": [tag[:MAX_TAG_CHARS] for tag in paper.tags[:MAX_TAGS]],
    }


def _page_payload(page: LiteratureAIPaperTextPage) -> dict[str, object]:
    return {"page_number": page.page_number, "text": page.text}


def _representative_pages(
    pages: tuple[LiteratureAIPaperTextPage, ...],
    budget: int,
) -> tuple[LiteratureAIPaperTextPage, ...]:
    if not pages:
        return ()
    count = len(pages)
    priority: list[int] = []
    for index in (*range(min(3, count)), *range(max(0, count - 3), count)):
        if index not in priority:
            priority.append(index)
    sample_count = min(count, 24)
    if sample_count > 1:
        for position in range(sample_count):
            index = round(position * (count - 1) / (sample_count - 1))
            if index not in priority:
                priority.append(index)

    selected: list[LiteratureAIPaperTextPage] = []
    used = 0
    for index in priority:
        page = pages[index]
        remaining = budget - used
        if remaining <= 0:
            break
        text = page.text[:remaining]
        if not text:
            continue
        selected.append(
            page if len(text) == len(page.text) else LiteratureAIPaperTextPage(
                paper_id=page.paper_id,
                page_number=page.page_number,
                text=text,
                extractor_version=page.extractor_version,
                created_at=page.created_at,
                updated_at=page.updated_at,
            )
        )
        used += len(text)
    return tuple(sorted(selected, key=lambda item: item.page_number))


def _relevant_chunks(
    pages: tuple[LiteratureAIPaperTextPage, ...],
    question: str,
) -> list[dict[str, object]]:
    query_terms = _tokens(question)
    if not query_terms:
        return []
    candidates: list[tuple[float, int, int, str]] = []
    seen_text: set[str] = set()
    for page in pages:
        for offset, text in _chunks(page.text):
            fingerprint = text.casefold()
            if fingerprint in seen_text:
                continue
            seen_text.add(fingerprint)
            terms = Counter(_tokens(text))
            score = sum(1.0 + math.log1p(terms[term]) for term in query_terms if term in terms)
            if score > 0:
                candidates.append((score, page.page_number, offset, text))
    candidates.sort(key=lambda item: (-item[0], item[1], item[2]))
    return [
        {"page_number": page_number, "text": text}
        for _, page_number, _, text in candidates[:MAX_ASK_CHUNKS]
    ]


def _chunks(text: str) -> tuple[tuple[int, str], ...]:
    if not text:
        return ()
    step = CHUNK_CHARS - CHUNK_OVERLAP
    return tuple(
        (offset, text[offset : offset + CHUNK_CHARS])
        for offset in range(0, len(text), step)
        if text[offset : offset + CHUNK_CHARS]
    )


def _tokens(value: str) -> set[str]:
    lowered = value.casefold()
    latin = [
        token
        for token in re.findall(r"[a-z0-9][a-z0-9_-]+", lowered)
        if token not in _LATIN_STOP_WORDS
    ]
    cjk_runs = re.findall(r"[\u3400-\u9fff]+", lowered)
    cjk: list[str] = []
    for run in cjk_runs:
        cjk.extend(token for token in run if token not in _CJK_STOP_TOKENS)
        cjk.extend(
            token
            for index in range(len(run) - 1)
            if (token := run[index : index + 2]) not in _CJK_STOP_TOKENS
        )
    return set((*latin, *cjk))


def _bounded_messages(messages: tuple[LiteratureAIMessage, ...]) -> list[dict[str, object]]:
    selected: list[dict[str, object]] = []
    used = 0
    for message in reversed(messages[-MAX_RECENT_MESSAGES:]):
        text = str(message.content)
        remaining = MAX_CONVERSATION_CHARS - used
        if remaining <= 0:
            break
        selected.append({"role": message.role, "content": text[:remaining]})
        used += min(len(text), remaining)
    selected.reverse()
    return selected


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
