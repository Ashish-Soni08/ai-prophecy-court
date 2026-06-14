"""Typed contracts shared by the court repository and API service."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RoastStyle(StrEnum):
    TECHNICAL = "technical"
    DARK = "dark"
    DAD_JOKE = "dad-joke"


class ReviewStatus(StrEnum):
    HUMAN_REVIEWED = "human-reviewed"
    AI_SCREENED = "ai-screened"


class Verdict(StrEnum):
    GUILTY = "guilty"
    NOT_GUILTY = "not-guilty"
    JURY_OUT = "jury-still-out"


class PlatformPresence(StrictModel):
    platform: str
    status: str
    url: HttpUrl | None = None
    absence_quip: str | None = None


class Leader(StrictModel):
    id: str
    name: str
    company: str
    portrait_url: str | None = None
    character_brief: str
    presence: list[PlatformPresence]
    case_ids: list[str] = Field(default_factory=list)


class Evidence(StrictModel):
    content_id: str
    platform: str
    canonical_url: HttpUrl
    published_at: datetime
    exact_text: str
    excerpt: str


class CaseFile(StrictModel):
    id: str
    person_id: str
    title: str
    category: str
    evidence: Evidence
    charge: str
    fair_defense: str
    rationale: str
    verdict: Verdict
    review_status: ReviewStatus
    roastability: int = Field(ge=0, le=100)
    confidence: int = Field(ge=0, le=100)
    court_direction: str
    featured: bool = False


class RoastCandidate(StrictModel):
    slot: str
    text: str
    model_id: str
    cached: bool = True


class TrialPayload(StrictModel):
    case: CaseFile
    style: RoastStyle
    session_id: str
    judge_intro: str
    roasts: list[RoastCandidate]
    model_identities_hidden: bool = True
    live: bool = False
    fallback_reason: str | None = None


class RuntimeBattle(StrictModel):
    judge_intro: str
    roasts: list[RoastCandidate]


class VoteReveal(StrictModel):
    case_id: str
    choice: str
    model_a: str
    model_b: str
    stored: bool
    aggregate: dict[str, int]


class RuntimeVote(StrictModel):
    stored: bool
    aggregate: dict[str, int]


class VoiceAsset(StrictModel):
    case_id: str
    style: RoastStyle
    winner: str
    status: str
    audio_url: str | None = None
    message: str


class LeaderDetail(StrictModel):
    leader: Leader
    cases: list[CaseFile]


class BootstrapPayload(StrictModel):
    featured_case: CaseFile
    leaders: list[Leader]
    archive: list[CaseFile]
    roast_styles: list[RoastStyle]
    model_battle: list[str]
