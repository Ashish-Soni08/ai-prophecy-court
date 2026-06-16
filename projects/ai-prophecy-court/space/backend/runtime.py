"""Authenticated client for optional Modal-hosted runtime services."""

from __future__ import annotations

import os
from typing import Protocol

import httpx

from backend.models import CaseFile, RoastStyle, RuntimeBattle, RuntimeVote, VoiceAsset


class RuntimeUnavailable(RuntimeError):
    """Raised when the optional live runtime cannot satisfy a request."""


class CourtRuntime(Protocol):
    def roast_battle(self, case: CaseFile, style: RoastStyle) -> RuntimeBattle: ...

    def record_vote(
        self,
        case_id: str,
        style: RoastStyle,
        choice: str,
    ) -> RuntimeVote: ...

    def synthesize_voice(
        self,
        case_id: str,
        style: RoastStyle,
        winner: str,
        text: str,
    ) -> VoiceAsset: ...


class ModalRuntime:
    def __init__(self, base_url: str, token: str, timeout_seconds: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout_seconds = timeout_seconds

    @classmethod
    def from_environment(cls) -> "ModalRuntime | None":
        base_url = os.getenv("MODAL_RUNTIME_URL", "").strip()
        token = os.getenv("MODAL_RUNTIME_TOKEN", "").strip()
        if not base_url or not token:
            return None
        return cls(base_url=base_url, token=token)

    def _post(self, path: str, payload: dict[str, object]) -> dict[str, object]:
        try:
            response = httpx.post(
                f"{self.base_url}{path}",
                json=payload,
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise RuntimeUnavailable(str(exc)) from exc
        if not isinstance(data, dict):
            raise RuntimeUnavailable("Runtime response was not a JSON object")
        return data

    def roast_battle(self, case: CaseFile, style: RoastStyle) -> RuntimeBattle:
        data = self._post(
            "/roast-battle",
            {"case": case.model_dump(mode="json"), "style": style.value},
        )
        return RuntimeBattle.model_validate(data)

    def record_vote(
        self,
        case_id: str,
        style: RoastStyle,
        choice: str,
    ) -> RuntimeVote:
        data = self._post(
            "/votes",
            {"case_id": case_id, "style": style.value, "choice": choice},
        )
        return RuntimeVote.model_validate(data)

    def synthesize_voice(
        self,
        case_id: str,
        style: RoastStyle,
        winner: str,
        text: str,
    ) -> VoiceAsset:
        data = self._post(
            "/voice",
            {
                "case_id": case_id,
                "style": style.value,
                "winner": winner,
                "text": text,
            },
        )
        return VoiceAsset.model_validate(data)
