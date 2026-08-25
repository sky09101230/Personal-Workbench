import json

import httpx
import pytest

from app.core.config import Settings
from app.modules.news.domain.models import FeedItem, FeedItemType
from app.modules.news.infrastructure.summarizers.deepseek import (
    MAX_ABSTRACT_CHARS,
    MAX_BATCH_ITEMS,
    DeepSeekPaperSummarizer,
)


def test_deepseek_maps_bounded_batch_request_and_summary() -> None:
    requests: list[httpx.Request] = []
    item = _paper("openalex:W1", "A" * (MAX_ABSTRACT_CHARS + 50))

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return _response({"summaries": [{"id": item.id, "summary": "研究提出一种紧凑方法，并验证了主要结果。"}]})

    summarized = _summarizer(handler).summarize((item,))[0]

    assert summarized.id == item.id
    assert summarized.summary == "研究提出一种紧凑方法，并验证了主要结果。"
    assert summarized.metadata["summary_kind"] == "ai"
    assert summarized.metadata["summary_provider"] == "deepseek"
    assert len(requests) == 1
    request = requests[0]
    assert request.url == "https://api.deepseek.com/chat/completions"
    assert request.headers["Authorization"] == "Bearer test-deepseek-key"
    body = json.loads(request.content)
    assert body["model"] == "deepseek-v4-flash"
    assert body["thinking"] == {"type": "disabled"}
    assert body["response_format"] == {"type": "json_object"}
    assert body["stream"] is False
    assert "untrusted source text" in body["messages"][0]["content"]
    source = json.loads(body["messages"][1]["content"].split("\n", 1)[1])
    assert len(source["papers"]) == 1
    assert len(source["papers"][0]["abstract"]) == MAX_ABSTRACT_CHARS
    assert "test-deepseek-key" not in request.content.decode()


def test_deepseek_processes_all_items_in_bounded_batches_with_partial_results() -> None:
    items = tuple(_paper(f"openalex:W{index}", f"Abstract {index}") for index in range(12))
    batch_ids: list[list[str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        source = json.loads(body["messages"][1]["content"].split("\n", 1)[1])
        ids = [paper["id"] for paper in source["papers"]]
        batch_ids.append(ids)
        return _response(
            {
                "summaries": [
                    {"id": item_id, "summary": f"{item_id} 的摘要。"}
                    for item_id in ids
                    if item_id != items[1].id
                ]
            }
        )

    summarized = _summarizer(handler).summarize(items)

    assert [len(batch) for batch in batch_ids] == [MAX_BATCH_ITEMS, 2]
    assert summarized[0].summary == "openalex:W0 的摘要。"
    assert summarized[1] == items[1]
    assert summarized[-1].summary == "openalex:W11 的摘要。"
    assert all(item.metadata.get("summary_kind") == "ai" for item in summarized[2:])


def test_deepseek_without_key_makes_no_request() -> None:
    called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return _response({"summaries": []})

    item = _paper("openalex:W1", "Original abstract")
    summarized = _summarizer(handler, api_key="").summarize((item,))

    assert summarized == (item,)
    assert called is False


@pytest.mark.parametrize("status_code", [401, 403, 429, 500])
def test_deepseek_http_failures_preserve_original_summary(status_code: int) -> None:
    item = _paper("openalex:W1", "Original abstract")
    summarizer = _summarizer(
        lambda request: httpx.Response(status_code, request=request, json={"private": "error"})
    )

    assert summarizer.summarize((item,)) == (item,)


def test_deepseek_timeout_preserves_original_summary() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("private timeout", request=request)

    item = _paper("openalex:W1", "Original abstract")

    assert _summarizer(handler).summarize((item,)) == (item,)


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, content=b"not-json"),
        httpx.Response(200, json={"choices": []}),
        None,
    ],
)
def test_deepseek_malformed_response_preserves_original_summary(
    response: httpx.Response | None,
) -> None:
    item = _paper("openalex:W1", "Original abstract")
    malformed = response or _response_text("not-json-content")

    assert _summarizer(lambda request: malformed).summarize((item,)) == (item,)


def test_deepseek_unexpected_content_shape_preserves_original_summary() -> None:
    item = _paper("openalex:W1", "Original abstract")

    assert _summarizer(lambda request: _response({"unexpected": []})).summarize((item,)) == (
        item,
    )


def _summarizer(handler, *, api_key: str = "test-deepseek-key") -> DeepSeekPaperSummarizer:
    return DeepSeekPaperSummarizer(
        Settings(
            database_url="sqlite:///./data/workbench.db",
            cors_origins=["http://localhost:5173"],
            zotero_user_id="",
            zotero_api_key="",
            deepseek_api_key=api_key,
        ),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def _paper(item_id: str, summary: str) -> FeedItem:
    return FeedItem(
        id=item_id,
        type=FeedItemType.PAPER,
        source="openalex",
        title="A diffractive optical paper",
        summary=summary,
        url="https://example.com/paper",
        metadata={"doi": "10.1000/example"},
    )


def _response(content: object) -> httpx.Response:
    return _response_text(json.dumps(content, ensure_ascii=False))


def _response_text(content: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={"choices": [{"message": {"role": "assistant", "content": content}}]},
    )
