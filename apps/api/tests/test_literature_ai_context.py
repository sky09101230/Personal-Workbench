from dataclasses import dataclass

import pytest

from app.modules.literature.application.errors import (
    LiteratureAIContextError,
    PdfUnavailableError,
    ProviderAuthenticationError,
)
from app.modules.literature.domain.ai_models import (
    LiteratureAIMessage,
    LiteratureAIPaperTextPage,
)
from app.modules.literature.domain.models import Paper, PaperDetail, ProviderFile
from app.modules.literature.infrastructure.ai import paper_context
from app.modules.literature.infrastructure.ai.paper_context import PaperContextBuilder
from app.modules.literature.infrastructure.cache.sqlite import SQLiteLiteratureRepository


NOW = "2026-08-28T00:00:00+00:00"


@dataclass
class _Literature:
    paper: Paper
    pdf: bytes | None = None

    def get_paper(self, paper_id: str) -> PaperDetail:
        assert paper_id == self.paper.id
        return PaperDetail(self.paper)

    def open_pdf(self, paper_id: str) -> ProviderFile:
        if self.pdf is None:
            raise PdfUnavailableError("missing")
        return ProviderFile("paper.pdf", "application/pdf", (self.pdf,))


class _Page:
    def __init__(self, text: str) -> None:
        self._text = text

    def extract_text(self) -> str:
        return self._text


class _Pdf:
    def __init__(self, pages: list[str]) -> None:
        self.pages = [_Page(text) for text in pages]


def test_context_builder_supports_metadata_only_paper(tmp_path) -> None:
    repository = _repository(tmp_path)
    builder = PaperContextBuilder(
        _Literature(Paper("paper-1", "Metadata only", abstract="Known abstract")),
        repository,
    )

    context = builder.build_analysis_context("paper-1", deep=False)

    assert context.payload["paper"]["abstract"] == "Known abstract"
    assert context.payload["pdf_text_status"] == "unavailable"
    assert context.payload["pages"] == []


def test_context_builder_falls_back_when_pdf_provider_is_unavailable(tmp_path) -> None:
    class _UnavailablePdfLiterature(_Literature):
        def open_pdf(self, paper_id: str) -> ProviderFile:
            raise ProviderAuthenticationError("credentials rejected")

    builder = PaperContextBuilder(
        _UnavailablePdfLiterature(
            Paper("paper-1", "Metadata only", abstract="Known abstract")
        ),
        _repository(tmp_path),
    )

    context = builder.build_analysis_context("paper-1", deep=False)

    assert context.payload["paper"]["abstract"] == "Known abstract"
    assert context.payload["pdf_text_status"] == "unavailable"


def test_context_builder_extracts_normalized_pages_and_reuses_cache(
    tmp_path, monkeypatch
) -> None:
    repository = _repository(tmp_path)
    literature = _Literature(Paper("paper-1", "PDF"), pdf=b"fake")
    calls = 0

    def reader(stream):
        nonlocal calls
        calls += 1
        return _Pdf([" first\npage ", "second   page"])

    monkeypatch.setattr(paper_context, "PdfReader", reader)
    builder = PaperContextBuilder(literature, repository)

    first = builder.build_analysis_context("paper-1", deep=False)
    second = builder.build_analysis_context("paper-1", deep=False)

    assert calls == 1
    assert first.payload["pages"] == second.payload["pages"]
    assert first.payload["pages"] == [
        {"page_number": 1, "text": "first page"},
        {"page_number": 2, "text": "second page"},
    ]


def test_context_builder_replaces_stale_extractor_cache(tmp_path, monkeypatch) -> None:
    repository = _repository(tmp_path)
    repository.replace_paper_text(
        "paper-1",
        (
            LiteratureAIPaperTextPage(
                paper_id="paper-1",
                page_number=1,
                text="Supplementary Information for stale attachment",
                extractor_version="pypdf-6-v1",
                created_at=NOW,
                updated_at=NOW,
            ),
        ),
    )
    monkeypatch.setattr(paper_context, "PdfReader", lambda stream: _Pdf(["main paper text"]))
    builder = PaperContextBuilder(
        _Literature(Paper("paper-1", "Main paper"), pdf=b"fake"),
        repository,
    )

    context = builder.build_analysis_context("paper-1", deep=False)
    cached = repository.list_paper_text("paper-1")

    assert context.payload["pages"] == [{"page_number": 1, "text": "main paper text"}]
    assert cached[0].text == "main paper text"
    assert cached[0].extractor_version == paper_context.EXTRACTOR_VERSION


def test_context_builder_marks_empty_pdf_as_unavailable(tmp_path, monkeypatch) -> None:
    repository = _repository(tmp_path)
    monkeypatch.setattr(paper_context, "PdfReader", lambda stream: _Pdf([" ", "\n"]))
    builder = PaperContextBuilder(
        _Literature(Paper("paper-1", "Scan", abstract="Metadata fallback"), pdf=b"fake"),
        repository,
    )

    context = builder.build_analysis_context("paper-1", deep=True)

    assert context.payload["pdf_text_status"] == "unavailable"
    assert repository.list_paper_text("paper-1") == ()


def test_representative_context_includes_first_middle_and_last_pages(tmp_path) -> None:
    repository = _repository(tmp_path)
    pages = tuple(_page(number, f"page-{number} " * 10) for number in range(1, 31))
    repository.replace_paper_text("paper-1", pages)
    builder = PaperContextBuilder(_Literature(Paper("paper-1", "Long")), repository)

    payload = builder.build_analysis_context("paper-1", deep=False).payload
    page_numbers = [item["page_number"] for item in payload["pages"]]

    assert {1, 2, 3, 28, 29, 30}.issubset(page_numbers)
    assert any(10 <= number <= 20 for number in page_numbers)


def test_ask_context_uses_lexical_chunks_and_bounded_conversation(tmp_path) -> None:
    repository = _repository(tmp_path)
    repository.replace_paper_text(
        "paper-1",
        (
            _page(1, "generic introduction " * 200),
            _page(2, "diffraction neural network loss function evidence " * 100),
        ),
    )
    messages = tuple(
        LiteratureAIMessage(
            id=f"m-{index}",
            conversation_id="c-1",
            role="user" if index % 2 == 0 else "assistant",
            content={"text": f"message {index}"},
            model=None,
            prompt_version=None,
            created_at=NOW,
        )
        for index in range(12)
    )
    builder = PaperContextBuilder(
        _Literature(Paper("paper-1", "Question", abstract="Abstract")),
        repository,
    )

    payload = builder.build_ask_context(
        "paper-1",
        question="Why this loss function?",
        messages=messages,
    ).payload

    assert payload["retrieved_chunks"][0]["page_number"] == 2
    assert len(payload["retrieved_chunks"]) <= 8
    assert len(payload["recent_conversation"]) == 8


def test_ask_context_filters_stop_words_supports_chinese_and_deduplicates(tmp_path) -> None:
    repository = _repository(tmp_path)
    duplicate = "衍射神经网络通过光学传播完成分类。"
    repository.replace_paper_text(
        "paper-1",
        (
            _page(1, "the and of generic background"),
            _page(2, duplicate),
            _page(3, duplicate),
        ),
    )
    builder = PaperContextBuilder(
        _Literature(Paper("paper-1", "Question", abstract="Abstract")),
        repository,
    )

    payload = builder.build_ask_context(
        "paper-1",
        question="这个衍射网络如何完成分类？",
        messages=(),
    ).payload

    assert payload["retrieved_chunks"] == [
        {"page_number": 2, "text": duplicate}
    ]


def test_ask_context_stopword_only_query_does_not_send_unrelated_chunks(tmp_path) -> None:
    repository = _repository(tmp_path)
    repository.replace_paper_text("paper-1", (_page(1, "unrelated content"),))
    builder = PaperContextBuilder(
        _Literature(Paper("paper-1", "Question", abstract="Abstract")),
        repository,
    )

    payload = builder.build_ask_context(
        "paper-1",
        question="the and of",
        messages=(),
    ).payload

    assert payload["retrieved_chunks"] == []


def test_ask_context_rejects_paper_without_usable_context(tmp_path) -> None:
    builder = PaperContextBuilder(
        _Literature(Paper("paper-1", "Title only")),
        _repository(tmp_path),
    )
    with pytest.raises(LiteratureAIContextError, match="no context"):
        builder.build_ask_context("paper-1", question="Why?", messages=())


def test_selection_context_contains_only_supplied_neighbors(tmp_path) -> None:
    builder = PaperContextBuilder(
        _Literature(Paper("paper-1", "Selection"), pdf=b"must not be read"),
        _repository(tmp_path),
    )

    payload = builder.build_selection_context(
        "paper-1",
        page_number=3,
        selected_text="selected",
        context_before="before",
        context_after="after",
        question="meaning?",
    ).payload

    assert payload["selected_text"] == "selected"
    assert payload["context_before"] == "before"
    assert payload["context_after"] == "after"


def test_context_applies_backend_metadata_and_selection_budgets(tmp_path) -> None:
    builder = PaperContextBuilder(
        _Literature(
            Paper(
                "paper-1",
                "t" * 5_000,
                abstract="a" * 40_000,
                authors=tuple("n" * 600 for _ in range(110)),
            )
        ),
        _repository(tmp_path),
    )

    analysis = builder.build_analysis_context("paper-1", deep=False).payload
    selection = builder.build_selection_context(
        "paper-1",
        page_number=1,
        selected_text="s" * 9_000,
        context_before="b" * 3_000,
        context_after="a" * 3_000,
        question="q" * 3_000,
    ).payload

    assert len(analysis["paper"]["title"]) == 4_000
    assert len(analysis["paper"]["abstract"]) == 30_000
    assert len(analysis["paper"]["authors"]) == 100
    assert len(selection["selected_text"]) == 8_000
    assert len(selection["context_before"]) == 2_000
    assert len(selection["context_after"]) == 2_000
    assert len(selection["question"]) == 2_000


def _repository(tmp_path) -> SQLiteLiteratureRepository:
    return SQLiteLiteratureRepository(f"sqlite:///{(tmp_path / 'ai-context.db').as_posix()}")


def _page(number: int, text: str) -> LiteratureAIPaperTextPage:
    return LiteratureAIPaperTextPage(
        paper_id="paper-1",
        page_number=number,
        text=text,
        extractor_version=paper_context.EXTRACTOR_VERSION,
        created_at=NOW,
        updated_at=NOW,
    )
