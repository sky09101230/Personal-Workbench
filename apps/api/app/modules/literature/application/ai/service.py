import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from app.modules.literature.application.ai.ports import (
    LiteratureAIProvider,
    LiteratureAIRepository,
    PaperContextProvider,
)
from app.modules.literature.application.ai.prompts import (
    ASK_PAPER,
    DEEP_READ,
    OVERVIEW,
    selection_prompt,
)
from app.modules.literature.application.ai.schemas import (
    ANALYSIS_TYPES,
    SELECTION_ACTIONS,
    USER_NOTE_SOURCES,
    parse_ask_paper,
    parse_deep_read,
    parse_overview,
    parse_selection,
    result_object,
)
from app.modules.literature.application.errors import (
    LiteratureAIInvalidResponseError,
    LiteratureAIResourceNotFoundError,
)
from app.modules.literature.application.service import LiteratureService
from app.modules.literature.domain.ai_models import (
    LiteratureAIAnalysis,
    LiteratureAIConversation,
    LiteratureAIMessage,
    LiteratureUserNote,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return str(uuid4())


@dataclass(frozen=True)
class LiteratureAIService:
    literature: LiteratureService
    provider: LiteratureAIProvider
    context: PaperContextProvider
    repository: LiteratureAIRepository
    clock: Callable[[], str] = _utc_now
    id_factory: Callable[[], str] = _new_id

    def list_analyses(
        self,
        paper_id: str,
        *,
        analysis_type: str | None = None,
    ) -> tuple[LiteratureAIAnalysis, ...]:
        self.literature.get_paper(paper_id)
        if analysis_type is not None and not _valid_analysis_type(analysis_type):
            raise ValueError("Unsupported analysis type")
        return self.repository.list_analyses(paper_id, analysis_type=analysis_type)

    def generate_analysis(
        self,
        paper_id: str,
        *,
        analysis_type: str,
        regenerate: bool = False,
    ) -> LiteratureAIAnalysis:
        if analysis_type not in ANALYSIS_TYPES:
            raise ValueError("Unsupported analysis type")
        self.literature.get_paper(paper_id)
        existing = self.repository.list_analyses(paper_id, analysis_type=analysis_type)
        if existing and not regenerate:
            return existing[0]

        prompt = DEEP_READ if analysis_type == "deep_read" else OVERVIEW
        context = self.context.build_analysis_context(
            paper_id,
            deep=analysis_type == "deep_read",
        )
        generated = self.provider.generate(prompt, context)
        try:
            result = (
                parse_deep_read(generated.content)
                if analysis_type == "deep_read"
                else parse_overview(generated.content)
            )
        except ValueError as error:
            raise LiteratureAIInvalidResponseError(
                "The AI response did not match the expected analysis schema"
            ) from error
        analysis = LiteratureAIAnalysis(
            id=self.id_factory(),
            paper_id=paper_id,
            analysis_type=analysis_type,
            model=generated.model,
            prompt_version=prompt.version,
            content=result_object(result),
            created_at=self.clock(),
        )
        self.repository.save_analysis(analysis)
        return analysis

    def create_conversation(self, paper_id: str) -> LiteratureAIConversation:
        self.literature.get_paper(paper_id)
        now = self.clock()
        conversation = LiteratureAIConversation(
            id=self.id_factory(),
            paper_id=paper_id,
            created_at=now,
            updated_at=now,
        )
        self.repository.create_conversation(conversation)
        return conversation

    def list_conversations(self, paper_id: str) -> tuple[LiteratureAIConversation, ...]:
        self.literature.get_paper(paper_id)
        return self.repository.list_conversations(paper_id)

    def list_messages(
        self,
        paper_id: str,
        conversation_id: str,
    ) -> tuple[LiteratureAIMessage, ...]:
        self._conversation(paper_id, conversation_id)
        return self.repository.list_messages(conversation_id)

    def ask_paper(
        self,
        paper_id: str,
        conversation_id: str,
        *,
        question: str,
    ) -> tuple[LiteratureAIMessage, LiteratureAIMessage]:
        self._conversation(paper_id, conversation_id)
        existing = self.repository.list_messages(conversation_id)
        context = self.context.build_ask_context(
            paper_id,
            question=question,
            messages=existing,
        )
        generated = self.provider.generate(ASK_PAPER, context)
        try:
            result = parse_ask_paper(generated.content)
        except ValueError as error:
            raise LiteratureAIInvalidResponseError(
                "The AI response did not match the expected answer schema"
            ) from error
        timestamp = self.clock()
        user_message = LiteratureAIMessage(
            id=self.id_factory(),
            conversation_id=conversation_id,
            role="user",
            content={"question": question},
            model=None,
            prompt_version=None,
            created_at=timestamp,
        )
        assistant_message = LiteratureAIMessage(
            id=self.id_factory(),
            conversation_id=conversation_id,
            role="assistant",
            content=result_object(result),
            model=generated.model,
            prompt_version=ASK_PAPER.version,
            created_at=timestamp,
        )
        self.repository.save_messages((user_message, assistant_message))
        return user_message, assistant_message

    def run_selection(
        self,
        paper_id: str,
        *,
        action: str,
        page_number: int,
        selected_text: str,
        context_before: str,
        context_after: str,
        question: str | None,
    ) -> LiteratureAIAnalysis:
        if action not in SELECTION_ACTIONS:
            raise ValueError("Unsupported selection action")
        self.literature.get_paper(paper_id)
        prompt = selection_prompt(action)
        context = self.context.build_selection_context(
            paper_id,
            page_number=page_number,
            selected_text=selected_text,
            context_before=context_before,
            context_after=context_after,
            question=question,
        )
        generated = self.provider.generate(prompt, context)
        try:
            result = parse_selection(generated.content, action)
        except ValueError as error:
            raise LiteratureAIInvalidResponseError(
                "The AI response did not match the expected selection schema"
            ) from error
        analysis = LiteratureAIAnalysis(
            id=self.id_factory(),
            paper_id=paper_id,
            analysis_type=f"selection_{action}",
            model=generated.model,
            prompt_version=prompt.version,
            content=result_object(result),
            created_at=self.clock(),
        )
        self.repository.save_analysis(analysis)
        return analysis

    def list_user_notes(self, paper_id: str) -> tuple[LiteratureUserNote, ...]:
        self.literature.get_paper(paper_id)
        return self.repository.list_user_notes(paper_id)

    def create_manual_note(self, paper_id: str, content: str) -> LiteratureUserNote:
        self.literature.get_paper(paper_id)
        return self._save_note(paper_id, content, "manual")

    def add_analysis_to_notes(
        self,
        paper_id: str,
        analysis_id: str,
    ) -> LiteratureUserNote:
        self.literature.get_paper(paper_id)
        analysis = self.repository.get_analysis(analysis_id)
        if analysis is None or analysis.paper_id != paper_id:
            raise LiteratureAIResourceNotFoundError("AI analysis was not found")
        source = {
            "overview": "ai_overview",
            "deep_read": "ai_deep_read",
        }.get(analysis.analysis_type, "ai_selection")
        return self._save_note(paper_id, _render_content(analysis.content), source)

    def add_message_to_notes(
        self,
        paper_id: str,
        message_id: str,
    ) -> LiteratureUserNote:
        self.literature.get_paper(paper_id)
        message = self.repository.get_message(message_id)
        if message is None or message.role != "assistant":
            raise LiteratureAIResourceNotFoundError("AI message was not found")
        conversation = self.repository.get_conversation(message.conversation_id)
        if conversation is None or conversation.paper_id != paper_id:
            raise LiteratureAIResourceNotFoundError("AI message was not found")
        return self._save_note(paper_id, _render_content(message.content), "ai_chat")

    def _conversation(
        self,
        paper_id: str,
        conversation_id: str,
    ) -> LiteratureAIConversation:
        self.literature.get_paper(paper_id)
        conversation = self.repository.get_conversation(conversation_id)
        if conversation is None or conversation.paper_id != paper_id:
            raise LiteratureAIResourceNotFoundError("AI conversation was not found")
        return conversation

    def _save_note(self, paper_id: str, content: str, source: str) -> LiteratureUserNote:
        text = content.strip()
        if not text:
            raise ValueError("Note content must not be empty")
        if source not in USER_NOTE_SOURCES:
            raise ValueError("Unsupported note source")
        now = self.clock()
        note = LiteratureUserNote(
            id=self.id_factory(),
            paper_id=paper_id,
            content=text,
            source=source,
            created_at=now,
            updated_at=now,
        )
        self.repository.save_user_note(note)
        return note


def _valid_analysis_type(value: str) -> bool:
    return value in ANALYSIS_TYPES or value.startswith("selection_")


def _render_content(content: dict[str, object]) -> str:
    lines: list[str] = []
    for key, value in content.items():
        label = key.replace("_", " ").title()
        if isinstance(value, list):
            lines.append(label + ":")
            lines.extend(f"- {item}" for item in value)
        elif isinstance(value, bool):
            lines.append(f"{label}: {'Yes' if value else 'No'}")
        elif value is not None:
            lines.append(f"{label}: {value}")
    return "\n".join(lines) if lines else json.dumps(content, ensure_ascii=False, indent=2)
