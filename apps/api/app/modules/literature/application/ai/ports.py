from typing import Protocol

from app.modules.literature.application.ai.schemas import PaperContext, PromptSpec, ProviderResult
from app.modules.literature.domain.ai_models import (
    LiteratureAIAnalysis,
    LiteratureAIConversation,
    LiteratureAIMessage,
    LiteratureAIPaperTextPage,
    LiteratureUserNote,
)


class LiteratureAIProvider(Protocol):
    def generate(self, prompt: PromptSpec, context: PaperContext) -> ProviderResult:
        ...


class PaperContextProvider(Protocol):
    def build_analysis_context(self, paper_id: str, *, deep: bool) -> PaperContext:
        ...

    def build_ask_context(
        self,
        paper_id: str,
        *,
        question: str,
        messages: tuple[LiteratureAIMessage, ...],
    ) -> PaperContext:
        ...

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
        ...


class LiteratureAIRepository(Protocol):
    def list_analyses(
        self, paper_id: str, *, analysis_type: str | None = None
    ) -> tuple[LiteratureAIAnalysis, ...]:
        ...

    def get_analysis(self, analysis_id: str) -> LiteratureAIAnalysis | None:
        ...

    def save_analysis(self, analysis: LiteratureAIAnalysis) -> None:
        ...

    def create_conversation(self, conversation: LiteratureAIConversation) -> None:
        ...

    def get_conversation(self, conversation_id: str) -> LiteratureAIConversation | None:
        ...

    def list_conversations(self, paper_id: str) -> tuple[LiteratureAIConversation, ...]:
        ...

    def list_messages(self, conversation_id: str) -> tuple[LiteratureAIMessage, ...]:
        ...

    def get_message(self, message_id: str) -> LiteratureAIMessage | None:
        ...

    def save_message(self, message: LiteratureAIMessage) -> None:
        ...

    def save_messages(self, messages: tuple[LiteratureAIMessage, ...]) -> None:
        ...

    def list_paper_text(self, paper_id: str) -> tuple[LiteratureAIPaperTextPage, ...]:
        ...

    def replace_paper_text(
        self, paper_id: str, pages: tuple[LiteratureAIPaperTextPage, ...]
    ) -> None:
        ...

    def list_user_notes(self, paper_id: str) -> tuple[LiteratureUserNote, ...]:
        ...

    def save_user_note(self, note: LiteratureUserNote) -> None:
        ...
