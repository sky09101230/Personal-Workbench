import json
from dataclasses import asdict, dataclass
from typing import Any

from app.modules.literature.domain.ai_models import JSONObject


ANALYSIS_TYPES = ("overview", "deep_read")
SELECTION_ACTIONS = ("explain", "summarize", "translate", "ask")
USER_NOTE_SOURCES = (
    "manual",
    "ai_overview",
    "ai_deep_read",
    "ai_chat",
    "ai_selection",
)


@dataclass(frozen=True)
class PromptSpec:
    version: str
    system_prompt: str
    max_tokens: int


@dataclass(frozen=True)
class PaperContext:
    payload: JSONObject


@dataclass(frozen=True)
class ProviderResult:
    model: str
    content: JSONObject


@dataclass(frozen=True)
class OverviewResult:
    research_question: str
    core_idea: str
    methodology: str
    contributions: tuple[str, ...]
    experiments: str
    key_results: tuple[str, ...]
    limitations: tuple[str, ...]
    worth_reading: str
    suggested_focus: tuple[str, ...]


@dataclass(frozen=True)
class DeepReadResult:
    research_problem: str
    core_logic: str
    key_assumptions: tuple[str, ...]
    why_it_may_work: str
    evidence_assessment: str
    reproducible_parts: tuple[str, ...]
    potential_problems: tuple[str, ...]
    underdiscussed_limitations: tuple[str, ...]
    unresolved_questions: tuple[str, ...]
    research_inspirations: tuple[str, ...]


@dataclass(frozen=True)
class AskPaperResult:
    answer: str
    paper_evidence: tuple[str, ...]
    ai_inference: tuple[str, ...]
    uncertainty: str
    insufficient_context: bool


@dataclass(frozen=True)
class SelectionResult:
    action: str
    response: str
    paper_evidence: tuple[str, ...]
    ai_inference: tuple[str, ...]
    uncertainty: str


def parse_overview(value: JSONObject) -> OverviewResult:
    return OverviewResult(
        research_question=_text(value, "research_question"),
        core_idea=_text(value, "core_idea"),
        methodology=_text(value, "methodology"),
        contributions=_text_list(value, "contributions"),
        experiments=_text(value, "experiments"),
        key_results=_text_list(value, "key_results"),
        limitations=_text_list(value, "limitations"),
        worth_reading=_text(value, "worth_reading"),
        suggested_focus=_text_list(value, "suggested_focus"),
    )


def parse_deep_read(value: JSONObject) -> DeepReadResult:
    return DeepReadResult(
        research_problem=_text(value, "research_problem"),
        core_logic=_text(value, "core_logic"),
        key_assumptions=_text_list(value, "key_assumptions"),
        why_it_may_work=_text(value, "why_it_may_work"),
        evidence_assessment=_text(value, "evidence_assessment"),
        reproducible_parts=_text_list(value, "reproducible_parts"),
        potential_problems=_text_list(value, "potential_problems"),
        underdiscussed_limitations=_text_list(value, "underdiscussed_limitations"),
        unresolved_questions=_text_list(value, "unresolved_questions"),
        research_inspirations=_text_list(value, "research_inspirations"),
    )


def parse_ask_paper(value: JSONObject) -> AskPaperResult:
    insufficient = value.get("insufficient_context")
    if not isinstance(insufficient, bool):
        raise ValueError("insufficient_context must be boolean")
    return AskPaperResult(
        answer=_text(value, "answer"),
        paper_evidence=_text_list(value, "paper_evidence"),
        ai_inference=_text_list(value, "ai_inference"),
        uncertainty=_text(value, "uncertainty"),
        insufficient_context=insufficient,
    )


def parse_selection(value: JSONObject, action: str) -> SelectionResult:
    return SelectionResult(
        action=action,
        response=_text(value, "response"),
        paper_evidence=_text_list(value, "paper_evidence"),
        ai_inference=_text_list(value, "ai_inference"),
        uncertainty=_text(value, "uncertainty"),
    )


def result_object(value: object) -> JSONObject:
    return json.loads(json.dumps(asdict(value), ensure_ascii=False))


def _text(value: dict[str, Any], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item.strip():
        raise ValueError(f"{key} must be non-empty text")
    return item.strip()


def _text_list(value: dict[str, Any], key: str) -> tuple[str, ...]:
    items = value.get(key)
    if not isinstance(items, list) or not all(isinstance(item, str) and item.strip() for item in items):
        raise ValueError(f"{key} must be a text list")
    return tuple(item.strip() for item in items)
