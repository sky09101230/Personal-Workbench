from dataclasses import dataclass, field

import pytest

from app.modules.literature.application.ai.schemas import PaperContext, ProviderResult
from app.modules.literature.application.ai.service import LiteratureAIService
from app.modules.literature.application.errors import (
    LiteratureAIContextError,
    LiteratureAIInvalidResponseError,
    LiteratureAIResourceNotFoundError,
    LiteratureResourceNotFoundError,
)
from app.modules.literature.domain.models import Paper, PaperDetail
from app.modules.literature.infrastructure.cache.sqlite import SQLiteLiteratureRepository


NOW = "2026-08-28T00:00:00+00:00"


@dataclass
class _Literature:
    paper_id: str = "paper-1"

    def get_paper(self, paper_id: str) -> PaperDetail:
        if paper_id != self.paper_id:
            raise LiteratureResourceNotFoundError("missing")
        return PaperDetail(Paper(paper_id, "Paper", abstract="Abstract"))


@dataclass
class _Context:
    fail: bool = False
    calls: list[tuple[str, object]] = field(default_factory=list)

    def build_analysis_context(self, paper_id: str, *, deep: bool) -> PaperContext:
        self.calls.append(("analysis", deep))
        if self.fail:
            raise LiteratureAIContextError("missing context")
        return PaperContext({"paper": {"title": "Paper"}, "deep": deep})

    def build_ask_context(self, paper_id: str, *, question: str, messages) -> PaperContext:
        self.calls.append(("ask", question))
        if self.fail:
            raise LiteratureAIContextError("missing context")
        return PaperContext({"question": question, "messages": len(messages)})

    def build_selection_context(self, paper_id: str, **kwargs) -> PaperContext:
        self.calls.append(("selection", kwargs["selected_text"]))
        return PaperContext(kwargs)


@dataclass
class _Provider:
    invalid: bool = False
    calls: list[str] = field(default_factory=list)

    def generate(self, prompt, context) -> ProviderResult:
        self.calls.append(prompt.version)
        if self.invalid:
            return ProviderResult("deepseek-test", {"wrong": "shape"})
        if prompt.version == "overview_v1":
            content = {
                "research_question": "RQ",
                "core_idea": "Idea",
                "methodology": "Method",
                "contributions": ["Contribution"],
                "experiments": "Experiments",
                "key_results": ["Result"],
                "limitations": ["Limit"],
                "worth_reading": "Yes",
                "suggested_focus": ["Focus"],
            }
        elif prompt.version == "deep_read_v1":
            content = {
                "research_problem": "Problem",
                "core_logic": "Logic",
                "key_assumptions": ["Assumption"],
                "why_it_may_work": "Why",
                "evidence_assessment": "Evidence",
                "reproducible_parts": ["Part"],
                "potential_problems": ["Problem"],
                "underdiscussed_limitations": ["Limit"],
                "unresolved_questions": ["Question"],
                "research_inspirations": ["Idea"],
            }
        elif prompt.version == "ask_paper_v1":
            content = {
                "answer": "Answer",
                "paper_evidence": ["Evidence"],
                "ai_inference": ["Inference"],
                "uncertainty": "Low",
                "insufficient_context": False,
            }
        else:
            content = {
                "response": "Selection response",
                "paper_evidence": ["Selection"],
                "ai_inference": [],
                "uncertainty": "Low",
            }
        return ProviderResult("deepseek-test", content)


def test_overview_is_persisted_and_reused_without_duplicate_request(tmp_path) -> None:
    service, provider, repository = _service(tmp_path)

    first = service.generate_analysis("paper-1", analysis_type="overview")
    second = service.generate_analysis("paper-1", analysis_type="overview")
    regenerated = service.generate_analysis(
        "paper-1", analysis_type="overview", regenerate=True
    )

    assert first == second
    assert regenerated.id != first.id
    assert provider.calls == ["overview_v1", "overview_v1"]
    assert len(repository.list_analyses("paper-1", analysis_type="overview")) == 2
    assert repository.list_user_notes("paper-1") == ()


def test_overview_prompt_explicitly_requires_array_fields() -> None:
    from app.modules.literature.application.ai.prompts import OVERVIEW

    assert "MUST always be JSON arrays of strings" in OVERVIEW.system_prompt
    assert "never return a scalar string or null" in OVERVIEW.system_prompt


def test_deep_read_uses_distinct_schema_and_prompt(tmp_path) -> None:
    service, provider, _ = _service(tmp_path)
    analysis = service.generate_analysis("paper-1", analysis_type="deep_read")
    assert analysis.prompt_version == "deep_read_v1"
    assert analysis.content["evidence_assessment"] == "Evidence"
    assert provider.calls == ["deep_read_v1"]


def test_invalid_schema_is_not_persisted(tmp_path) -> None:
    service, _, repository = _service(tmp_path, provider=_Provider(invalid=True))
    with pytest.raises(LiteratureAIInvalidResponseError):
        service.generate_analysis("paper-1", analysis_type="overview")
    assert repository.list_analyses("paper-1") == ()


def test_ask_paper_persists_bound_conversation_and_messages(tmp_path) -> None:
    service, _, repository = _service(tmp_path)
    conversation = service.create_conversation("paper-1")

    user, assistant = service.ask_paper(
        "paper-1", conversation.id, question="What is supported?"
    )

    assert user.role == "user"
    assert assistant.role == "assistant"
    assert assistant.content["paper_evidence"] == ["Evidence"]
    assert service.list_messages("paper-1", conversation.id) == (user, assistant)
    assert repository.list_user_notes("paper-1") == ()


def test_conversation_cannot_be_used_for_another_paper(tmp_path) -> None:
    service, _, _ = _service(tmp_path)
    conversation = service.create_conversation("paper-1")
    service.literature.paper_id = "paper-2"
    with pytest.raises(LiteratureAIResourceNotFoundError):
        service.list_messages("paper-2", conversation.id)


@pytest.mark.parametrize("action", ["explain", "summarize", "translate", "ask"])
def test_selection_actions_record_distinct_prompt_versions(tmp_path, action: str) -> None:
    service, provider, _ = _service(tmp_path)
    analysis = service.run_selection(
        "paper-1",
        action=action,
        page_number=2,
        selected_text="selected",
        context_before="before",
        context_after="after",
        question="why?" if action == "ask" else None,
    )
    assert analysis.prompt_version == f"selection_{action}_v1"
    assert provider.calls == [f"selection_{action}_v1"]


def test_add_to_notes_is_explicit_for_analysis_and_chat(tmp_path) -> None:
    service, _, repository = _service(tmp_path)
    analysis = service.generate_analysis("paper-1", analysis_type="overview")
    conversation = service.create_conversation("paper-1")
    _, assistant = service.ask_paper("paper-1", conversation.id, question="Question")
    assert repository.list_user_notes("paper-1") == ()

    overview_note = service.add_analysis_to_notes("paper-1", analysis.id)
    chat_note = service.add_message_to_notes("paper-1", assistant.id)
    manual_note = service.create_manual_note("paper-1", "Manual")

    assert {overview_note.source, chat_note.source, manual_note.source} == {
        "ai_overview",
        "ai_chat",
        "manual",
    }
    assert len(repository.list_user_notes("paper-1")) == 3


def test_service_maps_missing_paper_and_context(tmp_path) -> None:
    service, _, _ = _service(tmp_path)
    with pytest.raises(LiteratureResourceNotFoundError):
        service.generate_analysis("missing", analysis_type="overview")

    context = _Context(fail=True)
    service, _, _ = _service(tmp_path, context=context, suffix="missing-context")
    with pytest.raises(LiteratureAIContextError):
        service.ask_paper(
            "paper-1",
            service.create_conversation("paper-1").id,
            question="Question",
        )


def _service(tmp_path, *, provider=None, context=None, suffix="default"):
    repository = SQLiteLiteratureRepository(
        f"sqlite:///{(tmp_path / f'ai-service-{suffix}.db').as_posix()}"
    )
    ids = iter(f"id-{index}" for index in range(100))
    provider = provider or _Provider()
    service = LiteratureAIService(
        literature=_Literature(),
        provider=provider,
        context=context or _Context(),
        repository=repository,
        clock=lambda: NOW,
        id_factory=lambda: next(ids),
    )
    return service, provider, repository
