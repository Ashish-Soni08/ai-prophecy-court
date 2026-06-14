"""Prepare bounded source records for model-assisted docket enrichment."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from pathlib import Path

import pyarrow.parquet as pq
from pydantic import BaseModel, ConfigDict, Field

CLAIM_MARKERS = {
    "future": 16,
    "will": 14,
    "most": 10,
    "every": 14,
    "no more": 12,
    "obvious conclusion": 12,
    "within": 10,
    "by 20": 12,
    "believe": 7,
    "expect": 7,
    "should": 5,
}


class CandidateRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content_id: str
    person_id: str
    platform: str
    canonical_url: str
    published_at: str | None
    exact_text: str
    heuristic_score: int = Field(ge=0, le=100)
    matched_markers: list[str]


def score_text(text: str) -> tuple[int, list[str]]:
    normalized = re.sub(r"\s+", " ", text.lower())
    matches = [marker for marker in CLAIM_MARKERS if marker in normalized]
    score = sum(CLAIM_MARKERS[marker] for marker in matches)
    if len(text) >= 180:
        score += 5
    if any(character.isdigit() for character in text):
        score += 6
    if "!" in text:
        score += 3
    return min(score, 100), matches


def iter_records(parquet_root: Path) -> Iterable[dict[str, object]]:
    columns = [
        "content_id",
        "person_id",
        "platform",
        "canonical_url",
        "published_at",
        "text",
    ]
    for path in sorted(parquet_root.rglob("*.parquet")):
        yield from pq.read_table(path, columns=columns).to_pylist()


def build_candidates(
    parquet_root: Path,
    output_path: Path,
    minimum_score: int = 18,
) -> list[CandidateRecord]:
    candidates: list[CandidateRecord] = []
    seen: set[str] = set()
    for row in iter_records(parquet_root):
        content_id = str(row["content_id"])
        text = str(row.get("text") or "").strip()
        if not text or content_id in seen:
            continue
        score, markers = score_text(text)
        if score < minimum_score:
            continue
        seen.add(content_id)
        candidates.append(
            CandidateRecord(
                content_id=content_id,
                person_id=str(row["person_id"]),
                platform=str(row["platform"]),
                canonical_url=str(row["canonical_url"]),
                published_at=(
                    str(row["published_at"]) if row.get("published_at") else None
                ),
                exact_text=text,
                heuristic_score=score,
                matched_markers=markers,
            )
        )

    candidates.sort(key=lambda item: (-item.heuristic_score, item.content_id))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        for candidate in candidates:
            handle.write(candidate.model_dump_json())
            handle.write("\n")
    return candidates
