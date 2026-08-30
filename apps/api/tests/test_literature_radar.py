import copy
import json
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.modules.news.application.service import NewsService
from app.modules.news.infrastructure.cache.sqlite import SQLiteNewsRepository


client = TestClient(app)
FIXTURE_PATH = Path(__file__).parent / "fixtures" / "literature_radar_v2.json"


def test_real_radar_fixture_is_idempotent_and_persistent(
    tmp_path,
    override_service,
) -> None:
    payload = _fixture()
    database_path = tmp_path / "literature-radar.db"
    override_service("news_service", _service(database_path))

    first = client.post("/api/news/papers/research/ingest", json=payload)
    first_counts = _counts(database_path)
    second = client.post("/api/news/papers/research/ingest", json=payload)
    second_counts = _counts(database_path)
    latest = client.get("/api/news/papers/research/radar/latest")

    assert first.status_code == 200
    assert first.json()["created_run"] is True
    assert first.json()["created_papers"] == 9
    assert first.json()["created_recommendations"] == 9
    assert first.json()["candidate_count"] == 30
    assert first.json()["verified_candidate_count"] == 9
    assert first.json()["recommended_count"] == 5
    assert first_counts == (1, 9, 9)

    assert second.status_code == 200
    assert second.json()["run_id"] == first.json()["run_id"]
    assert second.json()["created_run"] is False
    assert second.json()["created_papers"] == 0
    assert second.json()["updated_papers"] == 0
    assert second.json()["created_recommendations"] == 0
    assert second.json()["updated_recommendations"] == 0
    assert second_counts == first_counts

    assert latest.status_code == 200
    run = latest.json()["run"]
    assert run["profile"]["key"] == "demo"
    assert run["search_window"] == {
        "from": "2026-06-30",
        "to": "2026-08-29",
        "lookback_days": 60,
    }
    assert run["candidate_count"] == 30
    assert run["verified_candidate_count"] == 9
    assert run["recommended_count"] == 5
    assert len(run["recommendations"]) == 5
    assert len(run["verified_alternatives"]) == 4
    assert run["recommendations"][0]["title"] == "Synthetic Recommended Paper 1"
    assert run["recommendations"][0]["selection_rank"] == 1
    assert run["recommendations"][0]["overall_score"] == 0.91
    assert run["recommendations"][0]["zotero_relationship"]["already_in_library"] is False
    assert run["recommendations"][0]["evidence"]["evidence_depth"] == "abstract"
    assert run["verified_alternatives"][0]["title"] == "Synthetic Verified Alternative 1"
    assert "near-tie" in run["verified_alternatives"][0]["recommendation_reason"]
    assert [source["status"] for source in run["source_status"]] == [
        "success",
        "degraded",
        "degraded",
        "success",
        "success",
    ]
    assert len(run["warnings"]) == 2
    assert "executable" not in run["zotero_context"]
    assert run["zotero_context"]["anchor_count"] == 3

    override_service("news_service", _service(database_path))
    recovered = client.get("/api/news/papers/research/radar/latest")
    assert recovered.status_code == 200
    assert recovered.json()["run"]["run_key"] == run["run_key"]
    assert len(recovered.json()["run"]["recommendations"]) == 5


def test_radar_identity_cannot_be_reused_with_different_content(
    tmp_path,
    override_service,
) -> None:
    payload = _fixture()
    database_path = tmp_path / "identity-conflict.db"
    override_service("news_service", _service(database_path))

    assert client.post("/api/news/papers/research/ingest", json=payload).status_code == 200
    conflicting = copy.deepcopy(payload)
    conflicting["warnings"].append("mutated after validation")

    response = client.post("/api/news/papers/research/ingest", json=conflicting)

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "paper_research_identity_conflict"
    assert _counts(database_path) == (1, 9, 9)


def test_radar_new_run_reuses_paper_by_canonical_title(
    tmp_path,
    override_service,
) -> None:
    first = _fixture()
    database_path = tmp_path / "paper-dedup.db"
    override_service("news_service", _service(database_path))
    assert client.post("/api/news/papers/research/ingest", json=first).status_code == 200

    second = copy.deepcopy(first)
    second["run_key"] = "radar-demo-20260830t120000z-title-fallback"
    second["ingest_identity"] = f"sha256:{'b' * 64}"
    second["generated_at"] = "2026-08-30T12:00:00Z"
    paper = second["papers"][0]
    paper["doi"] = None
    paper["arxiv_id"] = None
    second["papers"] = [paper]
    second["candidate_count"] = 1
    second["verified_candidate_count"] = 1
    second["recommended_count"] = 1

    response = client.post("/api/news/papers/research/ingest", json=second)

    assert response.status_code == 200
    assert response.json()["created_run"] is True
    assert response.json()["created_papers"] == 0
    assert response.json()["created_recommendations"] == 1
    assert _counts(database_path) == (2, 9, 10)


def test_radar_same_formal_doi_can_correct_stale_arxiv_id(
    tmp_path,
    override_service,
) -> None:
    first = _fixture()
    first_paper = first["papers"][0]
    first_paper["doi"] = "10.1000/arxiv-correction"
    first_paper["arxiv_id"] = "2601.08197"
    database_path = tmp_path / "arxiv-correction.db"
    override_service("news_service", _service(database_path))
    assert client.post("/api/news/papers/research/ingest", json=first).status_code == 200

    second = copy.deepcopy(first)
    second["run_key"] = "radar-demo-20260830t130000z-arxiv-correction"
    second["ingest_identity"] = f"sha256:{'c' * 64}"
    second["generated_at"] = "2026-08-30T13:00:00Z"
    second["papers"][0]["arxiv_id"] = "2601.07574"

    response = client.post("/api/news/papers/research/ingest", json=second)

    assert response.status_code == 200
    assert response.json()["created_run"] is True
    latest = client.get("/api/news/papers/research/radar/latest").json()["run"]
    assert latest["recommendations"][0]["doi"] == "10.1000/arxiv-correction"
    assert latest["recommendations"][0]["arxiv_id"] == "2601.07574"


def test_radar_review_status_persists_and_rejects_unknown_recommendation(
    tmp_path,
    override_service,
) -> None:
    database_path = tmp_path / "review.db"
    override_service("news_service", _service(database_path))
    assert client.post(
        "/api/news/papers/research/ingest",
        json=_fixture(),
    ).status_code == 200
    run = client.get("/api/news/papers/research/radar/latest").json()["run"]
    recommendation_id = run["recommendations"][0]["recommendation_id"]

    updated = client.patch(
        f"/api/news/papers/research/recommendations/{recommendation_id}/review",
        json={"status": "interested"},
    )
    missing = client.patch(
        "/api/news/papers/research/recommendations/missing/review",
        json={"status": "seen"},
    )
    invalid = client.patch(
        f"/api/news/papers/research/recommendations/{recommendation_id}/review",
        json={"status": "archived"},
    )

    assert updated.status_code == 200
    assert updated.json()["review_status"] == "interested"
    assert missing.status_code == 404
    assert invalid.status_code == 422

    override_service("news_service", _service(database_path))
    recovered = client.get("/api/news/papers/research/radar/latest").json()["run"]
    assert recovered["recommendations"][0]["review_status"] == "interested"


def _fixture() -> dict[str, object]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _service(database_path: Path) -> NewsService:
    return NewsService(
        providers=(),
        repository=SQLiteNewsRepository(f"sqlite:///{database_path.as_posix()}"),
    )


def _counts(database_path: Path) -> tuple[int, int, int]:
    with sqlite3.connect(database_path) as connection:
        return tuple(
            connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "news_paper_research_runs",
                "news_papers",
                "news_paper_research_recommendations",
            )
        )
