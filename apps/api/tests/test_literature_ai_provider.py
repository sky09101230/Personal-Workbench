import json

import httpx
import pytest

from app.core.config import Settings
from app.modules.literature.application.ai.prompts import OVERVIEW
from app.modules.literature.application.ai.schemas import PaperContext
from app.modules.literature.application.errors import (
    LiteratureAIInvalidResponseError,
    LiteratureAINotConfiguredError,
    LiteratureAIProviderError,
    LiteratureAIRateLimitError,
)
from app.modules.literature.infrastructure.ai.deepseek_provider import (
    DeepSeekLiteratureAIProvider,
)


def test_deepseek_literature_provider_returns_json_and_provenance() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "model": "deepseek-test-response",
                "choices": [{"message": {"content": '{"research_question":"Why?"}'}}],
            },
        )

    provider = _provider(handler)
    result = provider.generate(OVERVIEW, PaperContext({"paper": {"title": "A"}}))

    assert result.model == "deepseek-test-response"
    assert result.content == {"research_question": "Why?"}
    request = seen[0]
    body = json.loads(request.content)
    assert request.url == "https://deepseek.invalid/chat/completions"
    assert request.headers["Authorization"] == "Bearer test-secret"
    assert body["model"] == "deepseek-test"
    assert body["response_format"] == {"type": "json_object"}
    assert OVERVIEW.version not in request.content.decode()
    assert "test-secret" not in request.content.decode()


def test_deepseek_literature_provider_rejects_missing_key_without_request() -> None:
    called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200)

    settings = Settings("sqlite:///unused.db", [], "", "")
    provider = DeepSeekLiteratureAIProvider(
        settings,
        httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(LiteratureAINotConfiguredError):
        provider.generate(OVERVIEW, PaperContext({"paper": {}}))
    assert called is False


@pytest.mark.parametrize("status_code", [400, 401, 500, 503])
def test_deepseek_literature_provider_maps_http_errors(status_code: int, caplog) -> None:
    provider = _provider(lambda request: httpx.Response(status_code, text="private raw error"))
    with pytest.raises(LiteratureAIProviderError, match="provider returned an error") as caught:
        provider.generate(OVERVIEW, PaperContext({"paper": {}}))
    assert "private raw error" not in str(caught.value)
    assert "private raw error" not in caplog.text
    assert "test-secret" not in caplog.text
    assert "Authorization" not in caplog.text


def test_deepseek_literature_provider_maps_rate_limit() -> None:
    provider = _provider(lambda request: httpx.Response(429, text="quota details"))
    with pytest.raises(LiteratureAIRateLimitError):
        provider.generate(OVERVIEW, PaperContext({"paper": {}}))


def test_deepseek_literature_provider_maps_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    with pytest.raises(LiteratureAIProviderError, match="timed out"):
        _provider(handler).generate(OVERVIEW, PaperContext({"paper": {}}))


@pytest.mark.parametrize(
    "payload",
    [
        {"choices": []},
        {"choices": [{"message": {"content": "not json"}}]},
        {"choices": [{"message": {"content": "[]"}}]},
    ],
)
def test_deepseek_literature_provider_rejects_malformed_response(payload) -> None:
    provider = _provider(lambda request: httpx.Response(200, json=payload))
    with pytest.raises(LiteratureAIInvalidResponseError):
        provider.generate(OVERVIEW, PaperContext({"paper": {}}))


def _provider(handler) -> DeepSeekLiteratureAIProvider:
    settings = Settings(
        "sqlite:///unused.db",
        [],
        "",
        "",
        deepseek_api_key="test-secret",
        deepseek_base_url="https://deepseek.invalid",
        deepseek_model="deepseek-test",
    )
    return DeepSeekLiteratureAIProvider(
        settings,
        httpx.Client(transport=httpx.MockTransport(handler)),
    )
