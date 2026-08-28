import json
import logging

import httpx

from app.core.config import Settings
from app.modules.literature.application.ai.schemas import PaperContext, PromptSpec, ProviderResult
from app.modules.literature.application.errors import (
    LiteratureAIInvalidResponseError,
    LiteratureAINotConfiguredError,
    LiteratureAIProviderError,
    LiteratureAIRateLimitError,
)
from app.modules.literature.domain.ai_models import json_object


logger = logging.getLogger(__name__)


class DeepSeekLiteratureAIProvider:
    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        self._settings = settings
        self._client = client or httpx.Client(timeout=60.0)

    def generate(self, prompt: PromptSpec, context: PaperContext) -> ProviderResult:
        if not self._settings.deepseek_configured:
            raise LiteratureAINotConfiguredError("DeepSeek is not configured")
        try:
            response = self._client.post(
                f"{self._settings.deepseek_base_url.rstrip('/')}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._settings.deepseek_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self._settings.deepseek_model,
                    "messages": [
                        {"role": "system", "content": prompt.system_prompt},
                        {
                            "role": "user",
                            "content": "paper_context_json:\n"
                            + json.dumps(
                                context.payload,
                                ensure_ascii=False,
                                separators=(",", ":"),
                            ),
                        },
                    ],
                    "stream": False,
                    "thinking": {"type": "disabled"},
                    "temperature": 0.2,
                    "max_tokens": prompt.max_tokens,
                    "response_format": {"type": "json_object"},
                },
            )
        except httpx.TimeoutException as error:
            logger.warning("DeepSeek Literature AI request timed out")
            raise LiteratureAIProviderError("The AI provider timed out") from error
        except httpx.HTTPError as error:
            logger.warning("DeepSeek Literature AI request failed")
            raise LiteratureAIProviderError("The AI provider could not be reached") from error

        if response.status_code == 429:
            logger.warning("DeepSeek Literature AI request was rate limited")
            raise LiteratureAIRateLimitError("The AI provider rate limit was reached")
        if response.is_error:
            logger.warning(
                "DeepSeek Literature AI returned HTTP %s",
                response.status_code,
            )
            raise LiteratureAIProviderError("The AI provider returned an error")

        try:
            payload = response.json()
            content = payload["choices"][0]["message"]["content"]
            parsed = json_object(json.loads(content))
            response_model = payload.get("model")
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as error:
            logger.warning("DeepSeek Literature AI returned an invalid response")
            raise LiteratureAIInvalidResponseError(
                "The AI provider returned an invalid response"
            ) from error
        return ProviderResult(
            model=response_model if isinstance(response_model, str) else self._settings.deepseek_model,
            content=parsed,
        )
