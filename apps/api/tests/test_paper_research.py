import copy
import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.modules.news.application.research import normalize_doi
from app.modules.news.application.service import NewsService
from app.modules.news.infrastructure.cache.sqlite import SQLiteNewsRepository


client = TestClient(app)
FIXTURE_PATH = Path(__file__).parent / "fixtures" / "paper_research_v1.json"


def test_real_fixture_contract_and_idempotent_persistence(tmp_path, override_service) -> None:
    payload = _fixture()
    database_path = tmp_path / "research-acceptance.db"
    repository = SQLiteNewsRepository(f"sqlite:///{database_path.as_posix()}")
    override_service(
        "news_service",
        NewsService(providers=(), repository=repository),
    )

    first = client.post("/api/news/papers/research/ingest", json=payload)
    first_counts = _research_counts(database_path)
    second = client.post("/api/news/papers/research/ingest", json=payload)
    second_counts = _research_counts(database_path)
    feed = client.get("/api/news/papers/research?limit=10")

    assert first.status_code == 200
    assert first.json() == {
        "status": "succeeded",
        "run_id": first.json()["run_id"],
        "created_run": True,
        "created_papers": 5,
        "updated_papers": 0,
        "created_recommendations": 5,
        "updated_recommendations": 0,
        "papers_found": 5,
        "papers_accepted": 5,
    }
    assert first_counts == (1, 5, 5)
    assert second.status_code == 200
    assert second.json()["run_id"] == first.json()["run_id"]
    assert second.json()["created_run"] is False
    assert second.json()["created_papers"] == 0
    assert second.json()["updated_papers"] == 5
    assert second.json()["created_recommendations"] == 0
    assert second.json()["updated_recommendations"] == 5
    assert second_counts == (1, 5, 5)
    assert feed.status_code == 200
    assert feed.json()["total"] == 5
    assert all(item["source"] == "research" for item in feed.json()["items"])
    assert all(item["metadata"]["recommendation_reason"] for item in feed.json()["items"])
    assert all(item["metadata"]["research_run"]["run_key"] == payload["run_key"] for item in feed.json()["items"])

    recreated = NewsService(
        providers=(),
        repository=SQLiteNewsRepository(f"sqlite:///{database_path.as_posix()}"),
    )
    override_service("news_service", recreated)
    recovered = client.get("/api/news/papers/research?limit=10")

    assert recovered.status_code == 200
    assert recovered.json()["total"] == 5
    assert {item["title"] for item in recovered.json()["items"]} == {
        paper["title"] for paper in payload["papers"]
    }


@pytest.mark.parametrize(
    "mutate",
    [
        lambda payload: payload.pop("agent"),
        lambda payload: payload["papers"][0].update(relevance_score=1.1),
        lambda payload: payload["papers"][0].update(doi="not-a-doi"),
        lambda payload: payload.update(papers=[]),
        lambda payload: payload.update(schema_version="2"),
        lambda payload: payload.update(database_id="client-controlled"),
        lambda payload: payload["papers"][0].update(
            doi=None,
            arxiv_id=None,
            openalex_id=None,
            url=None,
            pdf_url=None,
        ),
    ],
    ids=[
        "missing-field",
        "invalid-score",
        "malformed-doi",
        "empty-papers",
        "schema",
        "extra",
        "missing-location",
    ],
)
def test_research_ingest_rejects_invalid_contract(
    tmp_path,
    override_service,
    mutate,
) -> None:
    database_path = tmp_path / "invalid.db"
    override_service(
        "news_service",
        NewsService(
            providers=(),
            repository=SQLiteNewsRepository(f"sqlite:///{database_path.as_posix()}"),
        ),
    )
    payload = _fixture()
    mutate(payload)

    response = client.post("/api/news/papers/research/ingest", json=payload)

    assert response.status_code == 422
    assert not database_path.exists()


def test_doi_forms_normalize_and_deduplicate_across_runs(tmp_path, override_service) -> None:
    database_path = tmp_path / "doi.db"
    override_service(
        "news_service",
        NewsService(
            providers=(),
            repository=SQLiteNewsRepository(f"sqlite:///{database_path.as_posix()}"),
        ),
    )
    variants = (
        "https://doi.org/10.1234/ABC.Def",
        "doi:10.1234/abc.def",
        "10.1234/ABC.DEF",
    )

    assert [normalize_doi(value) for value in variants] == ["10.1234/abc.def"] * 3
    for index, doi in enumerate(variants):
        payload = _single_paper_payload(
            run_key=f"doi-run-{index}",
            title=f"DOI identity title {index}",
            doi=doi,
        )
        response = client.post("/api/news/papers/research/ingest", json=payload)
        assert response.status_code == 200

    assert _research_counts(database_path) == (3, 1, 3)
    with sqlite3.connect(database_path) as connection:
        doi = connection.execute("SELECT doi FROM news_papers").fetchone()[0]
    assert doi == "10.1234/abc.def"


def test_different_runs_preserve_recommendation_history_and_query_latest(
    tmp_path,
    override_service,
) -> None:
    database_path = tmp_path / "history.db"
    override_service(
        "news_service",
        NewsService(
            providers=(),
            repository=SQLiteNewsRepository(f"sqlite:///{database_path.as_posix()}"),
        ),
    )
    first = _single_paper_payload(run_key="history-1", doi="10.1234/history")
    second = _single_paper_payload(run_key="history-2", doi="10.1234/history")
    second["generated_at"] = "2026-08-30T08:00:00Z"
    second["papers"][0]["recommendation_reason"] = "The newer run's recommendation."

    assert client.post("/api/news/papers/research/ingest", json=first).status_code == 200
    assert client.post("/api/news/papers/research/ingest", json=second).status_code == 200
    feed = client.get("/api/news/papers/research")

    assert _research_counts(database_path) == (2, 1, 2)
    assert feed.json()["total"] == 1
    assert feed.json()["items"][0]["metadata"]["recommendation_reason"] == (
        "The newer run's recommendation."
    )
    assert feed.json()["items"][0]["metadata"]["research_run"]["run_key"] == "history-2"


def test_identifier_conflict_rolls_back_entire_ingest(tmp_path, override_service) -> None:
    database_path = tmp_path / "rollback.db"
    override_service(
        "news_service",
        NewsService(
            providers=(),
            repository=SQLiteNewsRepository(f"sqlite:///{database_path.as_posix()}"),
        ),
    )
    first = _single_paper_payload(
        run_key="identity-a",
        doi="10.1234/identity-a",
        arxiv_id="2401.00001",
    )
    second = _single_paper_payload(
        run_key="identity-b",
        doi="10.1234/identity-b",
        arxiv_id="2401.00002",
    )
    second["papers"][0]["title"] = "Second established identity"
    assert client.post("/api/news/papers/research/ingest", json=first).status_code == 200
    assert client.post("/api/news/papers/research/ingest", json=second).status_code == 200
    before = _research_counts(database_path)

    conflicting = _single_paper_payload(run_key="conflicting-run", doi="10.1234/new-paper")
    conflicting["papers"].append(
        copy.deepcopy(conflicting["papers"][0])
    )
    conflicting["papers"][0]["title"] = "Would otherwise be inserted"
    conflicting["papers"][1].update(
        title="Conflicting established identities",
        doi="10.1234/identity-a",
        arxiv_id="2401.00002",
    )
    response = client.post("/api/news/papers/research/ingest", json=conflicting)

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "paper_research_identity_conflict"
    assert _research_counts(database_path) == before == (2, 2, 2)


def test_real_fixture_has_verified_titles_and_doi_urls() -> None:
    payload = _fixture()
    expected = {
        "All-optical machine learning using diffractive deep neural networks": "10.1126/science.aat8084",
        "Design of task-specific optical systems using broadband diffractive neural networks": "10.1038/s41377-019-0223-1",
        "Performing optical logic operations by a diffractive neural network": "10.1038/s41377-020-0303-2",
        "Space-efficient optical computing with an integrated chip diffractive neural network": "10.1038/s41467-022-28702-0",
        "Photonic machine learning with on-chip diffractive optics": "10.1038/s41467-022-35772-7",
    }

    assert len(payload["papers"]) == 5
    assert {
        paper["title"]: normalize_doi(paper["doi"])
        for paper in payload["papers"]
    } == expected
    assert all(paper["url"].startswith("https://") for paper in payload["papers"])
    assert all(paper["ai_summary"] and paper["recommendation_reason"] for paper in payload["papers"])


def _fixture() -> dict[str, object]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _single_paper_payload(
    *,
    run_key: str,
    doi: str,
    arxiv_id: str | None = None,
    title: str = "Identity test paper",
) -> dict[str, object]:
    payload = _fixture()
    payload["run_key"] = run_key
    payload["papers"] = [copy.deepcopy(payload["papers"][0])]
    payload["papers"][0].update(
        title=title,
        doi=doi,
        arxiv_id=arxiv_id,
        openalex_id=None,
        url=f"https://doi.org/{normalize_doi(doi)}",
    )
    return payload


def _research_counts(database_path: Path) -> tuple[int, int, int]:
    with sqlite3.connect(database_path) as connection:
        return tuple(
            connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "news_paper_research_runs",
                "news_papers",
                "news_paper_research_recommendations",
            )
        )
