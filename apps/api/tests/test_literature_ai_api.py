from dataclasses import dataclass, field

from fastapi.testclient import TestClient

from app.main import app
from app.modules.literature.application.ai.schemas import PaperContext, ProviderResult
from app.modules.literature.application.ai.service import LiteratureAIService
from app.modules.literature.application.errors import LiteratureAINotConfiguredError
from app.modules.literature.domain.models import Paper, PaperDetail
from app.modules.literature.infrastructure.cache.sqlite import SQLiteLiteratureRepository


client = TestClient(app)
NOW = "2026-08-28T00:00:00+00:00"


@dataclass
class _Literature:
    def get_paper(self, paper_id: str) -> PaperDetail:
        if paper_id not in {"paper-1", "paper-2"}:
            from app.modules.literature.application.errors import (
                LiteratureResourceNotFoundError,
            )

            raise LiteratureResourceNotFoundError("missing")
        return PaperDetail(Paper(paper_id, "Paper", abstract="Abstract"))


@dataclass
class _Context:
    calls: list[str] = field(default_factory=list)

    def build_analysis_context(self, paper_id: str, *, deep: bool) -> PaperContext:
        return PaperContext({"paper": {"title": "Paper"}})

    def build_ask_context(self, paper_id: str, **kwargs) -> PaperContext:
        return PaperContext({"question": kwargs["question"]})

    def build_selection_context(self, paper_id: str, **kwargs) -> PaperContext:
        return PaperContext(kwargs)


class _Provider:
    def generate(self, prompt, context) -> ProviderResult:
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
        elif prompt.version == "ask_paper_v1":
            content = {
                "answer": "Answer",
                "paper_evidence": ["Evidence"],
                "ai_inference": [],
                "uncertainty": "Low",
                "insufficient_context": False,
            }
        else:
            content = {
                "response": "Selection response",
                "paper_evidence": ["Evidence"],
                "ai_inference": [],
                "uncertainty": "Low",
            }
        return ProviderResult("deepseek-test", content)


def test_literature_ai_endpoints_and_explicit_user_notes(tmp_path, override_service) -> None:
    service = _service(tmp_path)
    override_service("literature_ai_service", service)

    overview = client.post(
        "/api/literature/papers/paper-1/ai/analyses",
        json={"analysis_type": "overview"},
    )
    cached = client.get(
        "/api/literature/papers/paper-1/ai/analyses?analysis_type=overview"
    )
    conversation = client.post("/api/literature/papers/paper-1/ai/conversations")
    conversation_id = conversation.json()["id"]
    conversations = client.get("/api/literature/papers/paper-1/ai/conversations")
    cross_paper = client.get(
        f"/api/literature/papers/paper-2/ai/conversations/{conversation_id}/messages"
    )
    answer = client.post(
        f"/api/literature/papers/paper-1/ai/conversations/{conversation_id}/messages",
        json={"question": "What is supported?"},
    )
    selection = client.post(
        "/api/literature/papers/paper-1/ai/selection",
        json={
            "action": "explain",
            "page_number": 1,
            "selected_text": "selected",
            "context_before": "before",
            "context_after": "after",
        },
    )
    before_notes = client.get("/api/literature/papers/paper-1/user-notes")
    add_note = client.post(
        "/api/literature/papers/paper-1/user-notes",
        json={"analysis_id": overview.json()["id"]},
    )
    after_notes = client.get("/api/literature/papers/paper-1/user-notes")

    assert overview.status_code == 200
    assert overview.json()["prompt_version"] == "overview_v1"
    assert len(cached.json()["items"]) == 1
    assert conversation.status_code == 201
    assert conversations.json()["items"][0]["id"] == conversation_id
    assert cross_paper.status_code == 404
    assert cross_paper.json()["detail"]["code"] == "ai_resource_not_found"
    assert answer.json()["items"][1]["role"] == "assistant"
    assert selection.json()["prompt_version"] == "selection_explain_v1"
    assert before_notes.json() == {"items": []}
    assert add_note.status_code == 201
    assert add_note.json()["source"] == "ai_overview"
    assert len(after_notes.json()["items"]) == 1


def test_literature_ai_routes_map_errors_and_validate_bounds(tmp_path, override_service) -> None:
    service = _service(tmp_path, provider=_UnavailableProvider())
    override_service("literature_ai_service", service)

    missing_key = client.post(
        "/api/literature/papers/paper-1/ai/analyses",
        json={"analysis_type": "overview"},
    )
    missing_paper = client.get("/api/literature/papers/missing/user-notes")
    invalid_selection = client.post(
        "/api/literature/papers/paper-1/ai/selection",
        json={"action": "ask", "page_number": 1, "selected_text": ""},
    )
    missing_selection_question = client.post(
        "/api/literature/papers/paper-1/ai/selection",
        json={"action": "ask", "page_number": 1, "selected_text": "selected"},
    )
    blank_question = client.post(
        "/api/literature/papers/paper-1/ai/conversations/unknown/messages",
        json={"question": "   "},
    )
    forged_note_source = client.post(
        "/api/literature/papers/paper-1/user-notes",
        json={"content": "manual", "source": "ai_chat"},
    )

    assert missing_key.status_code == 503
    assert missing_key.json()["detail"]["code"] == "ai_not_configured"
    assert missing_paper.status_code == 404
    assert invalid_selection.status_code == 422
    assert missing_selection_question.status_code == 422
    assert blank_question.status_code == 422
    assert forged_note_source.status_code == 422


class _UnavailableProvider:
    def generate(self, prompt, context):
        raise LiteratureAINotConfiguredError("secret provider detail")


def _service(tmp_path, provider=None) -> LiteratureAIService:
    repository = SQLiteLiteratureRepository(
        f"sqlite:///{(tmp_path / 'ai-api.db').as_posix()}"
    )
    ids = iter(f"api-{index}" for index in range(100))
    return LiteratureAIService(
        literature=_Literature(),
        provider=provider or _Provider(),
        context=_Context(),
        repository=repository,
        clock=lambda: NOW,
        id_factory=lambda: next(ids),
    )
