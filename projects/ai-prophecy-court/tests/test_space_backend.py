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

from backend.models import RoastStyle
from backend.repository import DocketRepository
from backend.runtime import RuntimeUnavailable
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
