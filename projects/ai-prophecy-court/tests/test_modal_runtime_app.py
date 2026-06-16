from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from runtime import modal_app


@pytest.fixture()
def runtime_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TestClient:
    class DummyState:
        def __init__(self) -> None:
            self.commits = 0

        def commit(self) -> None:
            self.commits += 1

    monkeypatch.setenv("AUTH_TOKEN", "test-token")
    monkeypatch.delenv("NEMOTRON_BASE_URL", raising=False)
    monkeypatch.delenv("NEMOTRON_API_KEY", raising=False)
    monkeypatch.delenv("MINICPM_BASE_URL", raising=False)
    monkeypatch.delenv("MINICPM_API_KEY", raising=False)
    monkeypatch.setattr(modal_app, "STATE_DIR", tmp_path)
    monkeypatch.setattr(modal_app, "DATABASE_PATH", tmp_path / "feedback.sqlite3")
    monkeypatch.setattr(modal_app, "state", DummyState())
    return TestClient(modal_app.runtime_api.local())


def auth_headers() -> dict[str, str]:
    return {"Authorization": "Bearer test-token"}


def case_payload() -> dict[str, object]:
    return {
        "id": "local-model-majority",
        "person_id": "clement-delangue",
        "title": "The Majority Report",
        "category": "Small models / deployment",
        "evidence": {
            "content_id": "linkedin:7469805686659641344",
            "platform": "linkedin",
            "canonical_url": "https://www.linkedin.com/feed/update/urn:li:activity:7469805686659641344/",
            "published_at": "2026-06-08T17:40:57.978+00:00",
            "exact_text": "The future is multi-model.",
            "excerpt": "The future is multi-model.",
        },
        "charge": "One benchmark is carrying a broad conclusion.",
        "fair_defense": "The claim reserves frontier APIs for harder tasks.",
        "rationale": "The court can examine the rhetoric.",
        "verdict": "jury-still-out",
        "review_status": "human-reviewed",
        "roastability": 91,
        "confidence": 88,
        "court_direction": "benchmark-cross-examination",
        "featured": True,
    }


def test_modal_gateway_requires_bearer_auth(runtime_client: TestClient) -> None:
    assert runtime_client.get("/health").status_code == 401
    assert runtime_client.get("/health", headers=auth_headers()).json() == {"status": "ok"}


def test_modal_gateway_rejects_unknown_vote_fields(runtime_client: TestClient) -> None:
    response = runtime_client.post(
        "/votes",
        headers=auth_headers(),
        json={
            "case_id": "case",
            "style": "technical",
            "choice": "a",
            "visitor_id": "must-not-be-accepted",
        },
    )

    assert response.status_code == 422


def test_modal_gateway_persists_aggregate_votes(runtime_client: TestClient) -> None:
    payload = {"case_id": "case", "style": "technical", "choice": "a"}

    first = runtime_client.post("/votes", headers=auth_headers(), json=payload)
    second = runtime_client.post("/votes", headers=auth_headers(), json=payload)

    assert first.status_code == 200
    assert second.json() == {"stored": True, "aggregate": {"a": 2}}
    assert modal_app.state.commits == 2


def test_modal_gateway_voice_adapter_placeholder(runtime_client: TestClient) -> None:
    response = runtime_client.post(
        "/voice",
        headers=auth_headers(),
        json={
            "case_id": "case",
            "style": "dad-joke",
            "winner": "a",
            "text": "Winning roast.",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "case_id": "case",
        "style": "dad-joke",
        "winner": "a",
        "status": "not-configured",
        "audio_url": None,
        "message": "VoxCPM2 adapter is reserved but not deployed.",
    }


def test_modal_gateway_reports_unconfigured_model_endpoints(
    runtime_client: TestClient,
) -> None:
    response = runtime_client.post(
        "/roast-battle",
        headers=auth_headers(),
        json={"case": case_payload(), "style": "technical"},
    )

    assert response.status_code == 503
    assert "endpoint is not configured" in response.json()["detail"]
