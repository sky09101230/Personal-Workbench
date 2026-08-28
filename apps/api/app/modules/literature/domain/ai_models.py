from dataclasses import dataclass
from typing import Any


JSONObject = dict[str, Any]


@dataclass(frozen=True)
class LiteratureAIAnalysis:
    id: str
    paper_id: str
    analysis_type: str
    model: str
    prompt_version: str
    content: JSONObject
    created_at: str


@dataclass(frozen=True)
class LiteratureAIConversation:
    id: str
    paper_id: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class LiteratureAIMessage:
    id: str
    conversation_id: str
    role: str
    content: JSONObject
    model: str | None
    prompt_version: str | None
    created_at: str


@dataclass(frozen=True)
class LiteratureAIPaperTextPage:
    paper_id: str
    page_number: int
    text: str
    extractor_version: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class LiteratureUserNote:
    id: str
    paper_id: str
    content: str
    source: str
    created_at: str
    updated_at: str


def json_object(value: Any) -> JSONObject:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError("Expected a JSON object")
    return value
