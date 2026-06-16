from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
from jsonschema import validate

PROJECT = Path(__file__).resolve().parents[1]
SPACE = PROJECT / "space"
sys.path.insert(0, str(SPACE))

from backend.models import RoastCandidate, RoastStyle, RuntimeBattle, RuntimeVote, VoiceAsset
from backend.repository import DocketRepository
from backend.runtime import ModalRuntime, RuntimeUnavailable
from backend.service import MODEL_A, MODEL_B, CourtService


@pytest.fixture()
def court() -> CourtService:
    repository = DocketRepository.from_json(SPACE / "data" / "docket.json")
    return CourtService(repository)


def test_bootstrap_contains_featured_case_and_seven_leaders(court: CourtService) -> None:
    payload = court.bootstrap()

    assert payload.featured_case.id == "local-model-majority"
    assert len(payload.leaders) == 7
    assert payload.model_battle == [MODEL_A, MODEL_B]


@pytest.mark.parametrize("style", list(RoastStyle))
def test_curated_trial_is_schema_valid(court: CourtService, style: RoastStyle) -> None:
    payload = court.convene("local-model-majority", style, "test-session")

    assert payload.style == style
    assert [roast.slot for roast in payload.roasts] == ["A", "B"]
    assert all(roast.cached for roast in payload.roasts)
    assert payload.case.evidence.content_id == "linkedin:7469805686659641344"


def test_vote_reveals_models_and_counts_feedback(court: CourtService) -> None:
    first = court.record_vote("local-model-majority", "technical", "a", "one")
    second = court.record_vote("local-model-majority", "technical", "a", "two")

    assert first.model_a == MODEL_A
    assert first.model_b == MODEL_B
    assert second.aggregate["a"] == 2
    assert second.stored is False


def test_unknown_case_is_rejected(court: CourtService) -> None:
    with pytest.raises(ValueError, match="Unknown case"):
        court.convene("missing", "technical", "test-session")


class FailingRuntime:
    def roast_battle(self, case, style):
        raise RuntimeUnavailable("test outage")

    def record_vote(self, case_id, style, choice):
        raise RuntimeUnavailable("test outage")

    def synthesize_voice(self, case_id, style, winner, text):
        raise RuntimeUnavailable("test outage")


def test_runtime_outage_uses_curated_fallback() -> None:
    repository = DocketRepository.from_json(SPACE / "data" / "docket.json")
    service = CourtService(repository, runtime=FailingRuntime())

    payload = service.convene("local-model-majority", "technical", "session")

    assert payload.live is False
    assert payload.fallback_reason == "Live chamber unavailable: test outage"
    assert len(payload.roasts) == 2


class SuccessfulRuntime:
    def roast_battle(self, case, style):
        return RuntimeBattle(
            judge_intro="Live court is in session.",
            roasts=[
                RoastCandidate(
                    slot="A",
                    text="Live roast A",
                    model_id="live-a",
                    cached=False,
                ),
                RoastCandidate(
                    slot="B",
                    text="Live roast B",
                    model_id="live-b",
                    cached=False,
                ),
            ],
        )

    def record_vote(self, case_id, style, choice):
        return RuntimeVote(stored=True, aggregate={choice: 3})

    def synthesize_voice(self, case_id, style, winner, text):
        return VoiceAsset(
            case_id=case_id,
            style=style,
            winner=winner,
            status="ready",
            audio_url="https://example.com/verdict.wav",
            message="Voice ready.",
        )


def test_successful_runtime_replaces_curated_fallback() -> None:
    repository = DocketRepository.from_json(SPACE / "data" / "docket.json")
    service = CourtService(repository, runtime=SuccessfulRuntime())

    payload = service.convene("local-model-majority", "technical", "session")
    reveal = service.record_vote("local-model-majority", "technical", "a", "session")
    voice = service.voice_asset(
        case_id="local-model-majority",
        style="technical",
        winner="a",
        text=payload.roasts[0].text,
    )

    assert payload.live is True
    assert payload.roasts[0].cached is False
    assert payload.roasts[0].model_id == "live-a"
    assert reveal.stored is True
    assert reveal.aggregate == {"a": 3}
    assert voice.audio_url == "https://example.com/verdict.wav"


def test_modal_runtime_reads_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MODAL_RUNTIME_URL", raising=False)
    monkeypatch.delenv("MODAL_RUNTIME_TOKEN", raising=False)
    assert ModalRuntime.from_environment() is None

    monkeypatch.setenv("MODAL_RUNTIME_URL", "https://runtime.example.com/")
    monkeypatch.setenv("MODAL_RUNTIME_TOKEN", "secret")
    runtime = ModalRuntime.from_environment()

    assert runtime is not None
    assert runtime.base_url == "https://runtime.example.com"
    assert runtime.token == "secret"


def test_modal_runtime_posts_authorized_payload(
    monkeypatch: pytest.MonkeyPatch,
    court: CourtService,
) -> None:
    case = court.bootstrap().featured_case
    captured: dict[str, object] = {}

    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "judge_intro": "Live court.",
                "roasts": [
                    {"slot": "A", "text": "A", "model_id": "m-a", "cached": False},
                    {"slot": "B", "text": "B", "model_id": "m-b", "cached": False},
                ],
            }

    def fake_post(url, json, headers, timeout):
        captured.update(
            {
                "url": url,
                "json": json,
                "headers": headers,
                "timeout": timeout,
            }
        )
        return Response()

    monkeypatch.setattr("backend.runtime.httpx.post", fake_post)
    runtime = ModalRuntime("https://runtime.example.com/", "secret", timeout_seconds=7)

    battle = runtime.roast_battle(case, RoastStyle.TECHNICAL)

    assert captured["url"] == "https://runtime.example.com/roast-battle"
    assert captured["headers"] == {"Authorization": "Bearer secret"}
    assert captured["timeout"] == 7
    assert captured["json"]["case"]["id"] == "local-model-majority"
    assert captured["json"]["style"] == "technical"
    assert battle.roasts[0].model_id == "m-a"


def test_modal_runtime_rejects_malformed_runtime_response(
    monkeypatch: pytest.MonkeyPatch,
    court: CourtService,
) -> None:
    case = court.bootstrap().featured_case

    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> list[str]:
            return ["not", "a", "dict"]

    monkeypatch.setattr("backend.runtime.httpx.post", lambda *args, **kwargs: Response())
    runtime = ModalRuntime("https://runtime.example.com", "secret")

    with pytest.raises(RuntimeUnavailable, match="not a JSON object"):
        runtime.roast_battle(case, RoastStyle.TECHNICAL)


def test_docket_json_matches_published_schema() -> None:
    schema = json.loads((PROJECT / "schemas" / "docket.schema.json").read_text())
    docket = json.loads((SPACE / "data" / "docket.json").read_text())

    validate(instance=docket, schema=schema)


def test_voice_fallback_preserves_requested_winner(court: CourtService) -> None:
    asset = court.voice_asset(
        case_id="local-model-majority",
        style="technical",
        winner="a",
        text="The winning roast.",
    )

    assert asset.winner == "a"
    assert asset.audio_url is None
    assert asset.status == "curated-only"
