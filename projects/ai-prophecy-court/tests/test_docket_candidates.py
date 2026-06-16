from __future__ import annotations

from pipeline.docket.candidates import score_text


def test_claim_markers_prioritize_bounded_predictions() -> None:
    score, markers = score_text(
        "The future is multi-model and local systems will handle most tasks by 2028."
    )

    assert score >= 40
    assert {"future", "will", "most", "by 20"}.issubset(markers)


def test_non_claim_status_update_stays_low() -> None:
    score, markers = score_text("Thanks to the team for a great launch.")

    assert score < 18
    assert markers == []
