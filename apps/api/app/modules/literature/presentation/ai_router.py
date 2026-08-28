from dataclasses import asdict
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.literature.application.ai.service import LiteratureAIService
from app.modules.literature.application.errors import (
    LiteratureAIContextError,
    LiteratureAIError,
    LiteratureAIInvalidResponseError,
    LiteratureAINoTextError,
    LiteratureAINotConfiguredError,
    LiteratureAIProviderError,
    LiteratureAIRateLimitError,
    LiteratureAIResourceNotFoundError,
    LiteratureError,
    LiteratureResourceNotFoundError,
)


router = APIRouter()


class AnalysisRequest(BaseModel):
    analysis_type: Literal["overview", "deep_read"]
    regenerate: bool = False


class SelectionRequest(BaseModel):
    action: Literal["explain", "summarize", "translate", "ask"]
    page_number: int = Field(ge=1)
    selected_text: str = Field(min_length=1, max_length=8_000)
    context_before: str = Field(default="", max_length=2_000)
    context_after: str = Field(default="", max_length=2_000)
    question: str | None = Field(default=None, max_length=2_000)

    @model_validator(mode="after")
    def validate_text(self) -> "SelectionRequest":
        self.selected_text = self.selected_text.strip()
        if not self.selected_text:
            raise ValueError("selected_text must not be empty")
        if self.question is not None:
            self.question = self.question.strip() or None
        if self.action == "ask" and self.question is None:
            raise ValueError("question is required for the ask action")
        return self


class AskPaperRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4_000)

    @model_validator(mode="after")
    def validate_question(self) -> "AskPaperRequest":
        self.question = self.question.strip()
        if not self.question:
            raise ValueError("question must not be empty")
        return self


class UserNoteCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str | None = Field(default=None, max_length=50_000)
    analysis_id: str | None = None
    message_id: str | None = None

    @model_validator(mode="after")
    def exactly_one_source(self) -> "UserNoteCreateRequest":
        supplied = sum(
            value is not None for value in (self.content, self.analysis_id, self.message_id)
        )
        if supplied != 1:
            raise ValueError("Provide exactly one of content, analysis_id, or message_id")
        if self.content is not None and not self.content.strip():
            raise ValueError("content must not be empty")
        return self


class OverviewContentResponse(BaseModel):
    research_question: str
    core_idea: str
    methodology: str
    contributions: list[str]
    experiments: str
    key_results: list[str]
    limitations: list[str]
    worth_reading: str
    suggested_focus: list[str]


class DeepReadContentResponse(BaseModel):
    research_problem: str
    core_logic: str
    key_assumptions: list[str]
    why_it_may_work: str
    evidence_assessment: str
    reproducible_parts: list[str]
    potential_problems: list[str]
    underdiscussed_limitations: list[str]
    unresolved_questions: list[str]
    research_inspirations: list[str]


class SelectionContentResponse(BaseModel):
    action: Literal["explain", "summarize", "translate", "ask"]
    response: str
    paper_evidence: list[str]
    ai_inference: list[str]
    uncertainty: str


class AskPaperContentResponse(BaseModel):
    answer: str
    paper_evidence: list[str]
    ai_inference: list[str]
    uncertainty: str
    insufficient_context: bool


class UserQuestionContentResponse(BaseModel):
    question: str


class AnalysisResponse(BaseModel):
    id: str
    paper_id: str
    analysis_type: str
    model: str
    prompt_version: str
    content: OverviewContentResponse | DeepReadContentResponse | SelectionContentResponse
    created_at: str


class ConversationResponse(BaseModel):
    id: str
    paper_id: str
    created_at: str
    updated_at: str


class ConversationListResponse(BaseModel):
    items: list[ConversationResponse]


class MessageResponse(BaseModel):
    id: str
    conversation_id: str
    role: str
    content: UserQuestionContentResponse | AskPaperContentResponse
    model: str | None
    prompt_version: str | None
    created_at: str


class UserNoteResponse(BaseModel):
    id: str
    paper_id: str
    content: str
    source: str
    created_at: str
    updated_at: str


class AnalysisListResponse(BaseModel):
    items: list[AnalysisResponse]


class MessageListResponse(BaseModel):
    items: list[MessageResponse]


class UserNoteListResponse(BaseModel):
    items: list[UserNoteResponse]


def get_literature_ai_service(request: Request) -> LiteratureAIService:
    return request.app.state.literature_ai_service


@router.get(
    "/papers/{paper_id}/ai/analyses",
    response_model=AnalysisListResponse,
)
def list_analyses(
    paper_id: str,
    analysis_type: str | None = Query(default=None),
    service: LiteratureAIService = Depends(get_literature_ai_service),
) -> AnalysisListResponse:
    try:
        return AnalysisListResponse(
            items=[
                AnalysisResponse.model_validate(asdict(item))
                for item in service.list_analyses(paper_id, analysis_type=analysis_type)
            ]
        )
    except (LiteratureError, ValueError) as error:
        raise _http_error(error) from error


@router.post(
    "/papers/{paper_id}/ai/analyses",
    response_model=AnalysisResponse,
)
def create_analysis(
    paper_id: str,
    request: AnalysisRequest,
    service: LiteratureAIService = Depends(get_literature_ai_service),
) -> AnalysisResponse:
    try:
        result = service.generate_analysis(
            paper_id,
            analysis_type=request.analysis_type,
            regenerate=request.regenerate,
        )
        return AnalysisResponse.model_validate(asdict(result))
    except LiteratureError as error:
        raise _http_error(error) from error


@router.post(
    "/papers/{paper_id}/ai/conversations",
    response_model=ConversationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_conversation(
    paper_id: str,
    service: LiteratureAIService = Depends(get_literature_ai_service),
) -> ConversationResponse:
    try:
        return ConversationResponse.model_validate(asdict(service.create_conversation(paper_id)))
    except LiteratureError as error:
        raise _http_error(error) from error


@router.get(
    "/papers/{paper_id}/ai/conversations",
    response_model=ConversationListResponse,
)
def list_conversations(
    paper_id: str,
    service: LiteratureAIService = Depends(get_literature_ai_service),
) -> ConversationListResponse:
    try:
        return ConversationListResponse(
            items=[
                ConversationResponse.model_validate(asdict(item))
                for item in service.list_conversations(paper_id)
            ]
        )
    except LiteratureError as error:
        raise _http_error(error) from error


@router.get(
    "/papers/{paper_id}/ai/conversations/{conversation_id}/messages",
    response_model=MessageListResponse,
)
def list_messages(
    paper_id: str,
    conversation_id: str,
    service: LiteratureAIService = Depends(get_literature_ai_service),
) -> MessageListResponse:
    try:
        return MessageListResponse(
            items=[
                MessageResponse.model_validate(asdict(item))
                for item in service.list_messages(paper_id, conversation_id)
            ]
        )
    except LiteratureError as error:
        raise _http_error(error) from error


@router.post(
    "/papers/{paper_id}/ai/conversations/{conversation_id}/messages",
    response_model=MessageListResponse,
)
def ask_paper(
    paper_id: str,
    conversation_id: str,
    request: AskPaperRequest,
    service: LiteratureAIService = Depends(get_literature_ai_service),
) -> MessageListResponse:
    try:
        messages = service.ask_paper(
            paper_id,
            conversation_id,
            question=request.question.strip(),
        )
        return MessageListResponse(
            items=[MessageResponse.model_validate(asdict(item)) for item in messages]
        )
    except LiteratureError as error:
        raise _http_error(error) from error


@router.post(
    "/papers/{paper_id}/ai/selection",
    response_model=AnalysisResponse,
)
def run_selection(
    paper_id: str,
    request: SelectionRequest,
    service: LiteratureAIService = Depends(get_literature_ai_service),
) -> AnalysisResponse:
    try:
        result = service.run_selection(
            paper_id,
            action=request.action,
            page_number=request.page_number,
            selected_text=request.selected_text,
            context_before=request.context_before,
            context_after=request.context_after,
            question=request.question,
        )
        return AnalysisResponse.model_validate(asdict(result))
    except LiteratureError as error:
        raise _http_error(error) from error


@router.get(
    "/papers/{paper_id}/user-notes",
    response_model=UserNoteListResponse,
)
def list_user_notes(
    paper_id: str,
    service: LiteratureAIService = Depends(get_literature_ai_service),
) -> UserNoteListResponse:
    try:
        return UserNoteListResponse(
            items=[
                UserNoteResponse.model_validate(asdict(item))
                for item in service.list_user_notes(paper_id)
            ]
        )
    except LiteratureError as error:
        raise _http_error(error) from error


@router.post(
    "/papers/{paper_id}/user-notes",
    response_model=UserNoteResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_user_note(
    paper_id: str,
    request: UserNoteCreateRequest,
    service: LiteratureAIService = Depends(get_literature_ai_service),
) -> UserNoteResponse:
    try:
        if request.analysis_id is not None:
            note = service.add_analysis_to_notes(paper_id, request.analysis_id)
        elif request.message_id is not None:
            note = service.add_message_to_notes(paper_id, request.message_id)
        else:
            note = service.create_manual_note(paper_id, request.content or "")
        return UserNoteResponse.model_validate(asdict(note))
    except (LiteratureError, ValueError) as error:
        raise _http_error(error) from error


def _http_error(error: Exception) -> HTTPException:
    if isinstance(error, LiteratureResourceNotFoundError):
        return HTTPException(
            status_code=404,
            detail={"code": "paper_not_found", "message": "Paper was not found"},
        )
    if isinstance(error, LiteratureAIResourceNotFoundError):
        return HTTPException(
            status_code=404,
            detail={"code": "ai_resource_not_found", "message": str(error)},
        )
    if isinstance(error, LiteratureAINotConfiguredError):
        return HTTPException(
            status_code=503,
            detail={"code": "ai_not_configured", "message": "DeepSeek is not configured"},
        )
    if isinstance(error, LiteratureAIRateLimitError):
        return HTTPException(
            status_code=429,
            detail={"code": "ai_rate_limited", "message": "AI rate limit reached; retry later"},
        )
    if isinstance(error, LiteratureAINoTextError):
        return HTTPException(
            status_code=422,
            detail={"code": "pdf_text_unavailable", "message": "PDF has no extractable text"},
        )
    if isinstance(error, LiteratureAIContextError):
        return HTTPException(
            status_code=422,
            detail={"code": "ai_context_unavailable", "message": str(error)},
        )
    if isinstance(error, LiteratureAIInvalidResponseError):
        return HTTPException(
            status_code=502,
            detail={"code": "ai_invalid_response", "message": "AI returned invalid content"},
        )
    if isinstance(error, (LiteratureAIProviderError, LiteratureAIError)):
        return HTTPException(
            status_code=502,
            detail={"code": "ai_provider_unavailable", "message": "AI provider unavailable"},
        )
    return HTTPException(
        status_code=400,
        detail={"code": "invalid_request", "message": str(error)},
    )
