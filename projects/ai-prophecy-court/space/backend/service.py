"""Court orchestration with deterministic curated fallbacks."""

from __future__ import annotations

from collections import Counter, defaultdict
from threading import Lock

from backend.models import (
    BootstrapPayload,
    LeaderDetail,
    RoastCandidate,
    RoastStyle,
    TrialPayload,
    VoiceAsset,
    VoteReveal,
)
from backend.repository import DocketRepository
from backend.runtime import CourtRuntime, RuntimeUnavailable

MODEL_A = "nvidia/NVIDIA-Nemotron-3-Nano-4B-BF16"
MODEL_B = "openbmb/MiniCPM4.1-8B"

CURATED_ROASTS = {
    RoastStyle.TECHNICAL: (
        "The benchmark is doing useful work, but 'most tasks' just opened a pull request with no acceptance criteria.",
        "A 71.3% score became a universal deployment strategy so quickly that the missing 28.7% barely had time to file an objection.",
    ),
    RoastStyle.DARK: (
        "The frontier API was declared unnecessary by a post that still needed the frontier of the word 'most' to survive cross-examination.",
        "Nothing says confidence like turning one benchmark into a majority vote for every workload on Earth.",
    ),
    RoastStyle.DAD_JOKE: (
        "Local models handle most tasks now. The remaining tasks are apparently still trying to find parking in the cloud.",
        "The future is multi-model because even the conclusion needed several models of the word 'obvious'.",
    ),
}


class CourtService:
    def __init__(
        self,
        repository: DocketRepository,
        runtime: CourtRuntime | None = None,
    ) -> None:
        self.repository = repository
        self.runtime = runtime
        self._votes: dict[str, Counter[str]] = defaultdict(Counter)
        self._vote_lock = Lock()

    def bootstrap(self) -> BootstrapPayload:
        return BootstrapPayload(
            featured_case=self.repository.featured_case(),
            leaders=self.repository.leaders(),
            archive=[
                case
                for case in self.repository.cases()
                if case.featured and case.review_status == "human-reviewed"
            ],
            roast_styles=list(RoastStyle),
            model_battle=[MODEL_A, MODEL_B],
        )

    def leader_detail(self, person_id: str) -> LeaderDetail | None:
        leader = self.repository.get_leader(person_id)
        if leader is None:
            return None
        return LeaderDetail(leader=leader, cases=self.repository.cases_for(person_id))

    def convene(self, case_id: str, style: str, session_id: str) -> TrialPayload:
        case = self.repository.get_case(case_id)
        if case is None:
            raise ValueError(f"Unknown case: {case_id}")
        roast_style = RoastStyle(style)
        if self.runtime is not None:
            try:
                battle = self.runtime.roast_battle(case, roast_style)
                return TrialPayload(
                    case=case,
                    style=roast_style,
                    session_id=session_id,
                    judge_intro=battle.judge_intro,
                    roasts=battle.roasts,
                    live=True,
                )
            except RuntimeUnavailable as exc:
                fallback_reason = f"Live chamber unavailable: {exc}"
            else:
                fallback_reason = None
        else:
            fallback_reason = "Live chamber is not configured"
        roast_a, roast_b = CURATED_ROASTS[roast_style]
        return TrialPayload(
            case=case,
            style=roast_style,
            session_id=session_id,
            judge_intro=(
                "The source is admitted. The court will examine the confidence "
                "of the claim, not the character of the speaker."
            ),
            roasts=[
                RoastCandidate(slot="A", text=roast_a, model_id=MODEL_A),
                RoastCandidate(slot="B", text=roast_b, model_id=MODEL_B),
            ],
            fallback_reason=fallback_reason,
        )

    def record_vote(
        self,
        case_id: str,
        style: str,
        choice: str,
        session_id: str,
    ) -> VoteReveal:
        del session_id
        if self.repository.get_case(case_id) is None:
            raise ValueError(f"Unknown case: {case_id}")
        RoastStyle(style)
        allowed = {"a", "b", "both", "dismissed"}
        if choice not in allowed:
            raise ValueError(f"Unknown vote choice: {choice}")
        roast_style = RoastStyle(style)
        key = f"{case_id}:{style}"
        with self._vote_lock:
            self._votes[key][choice] += 1
            aggregate = dict(self._votes[key])
        stored = False
        if self.runtime is not None:
            try:
                runtime_vote = self.runtime.record_vote(case_id, roast_style, choice)
                stored = runtime_vote.stored
                aggregate = runtime_vote.aggregate
            except RuntimeUnavailable:
                pass
        return VoteReveal(
            case_id=case_id,
            choice=choice,
            model_a=MODEL_A,
            model_b=MODEL_B,
            stored=stored,
            aggregate=aggregate,
        )

    def voice_asset(
        self,
        case_id: str,
        style: str,
        winner: str,
        text: str,
    ) -> VoiceAsset:
        if self.repository.get_case(case_id) is None:
            raise ValueError(f"Unknown case: {case_id}")
        roast_style = RoastStyle(style)
        if self.runtime is not None:
            try:
                return self.runtime.synthesize_voice(
                    case_id=case_id,
                    style=roast_style,
                    winner=winner,
                    text=text,
                )
            except RuntimeUnavailable:
                pass
        return VoiceAsset(
            case_id=case_id,
            style=roast_style,
            winner=winner,
            status="curated-only",
            message="VoxCPM2 synthesis is not configured; the text verdict remains available.",
        )
