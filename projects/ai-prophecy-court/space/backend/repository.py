"""Read-only repository for the versioned docket release."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import TypeAdapter

from backend.models import CaseFile, Leader


class DocketRepository:
    def __init__(self, leaders: list[Leader], cases: list[CaseFile]) -> None:
        self._leaders = {leader.id: leader for leader in leaders}
        self._cases = {case.id: case for case in cases}

    @classmethod
    def from_json(cls, path: Path) -> "DocketRepository":
        payload = json.loads(path.read_text(encoding="utf-8"))
        leaders = TypeAdapter(list[Leader]).validate_python(payload["leaders"])
        cases = TypeAdapter(list[CaseFile]).validate_python(payload["cases"])
        return cls(leaders=leaders, cases=cases)

    def leaders(self) -> list[Leader]:
        return list(self._leaders.values())

    def cases(self) -> list[CaseFile]:
        return list(self._cases.values())

    def get_leader(self, person_id: str) -> Leader | None:
        return self._leaders.get(person_id)

    def get_case(self, case_id: str) -> CaseFile | None:
        return self._cases.get(case_id)

    def cases_for(self, person_id: str) -> list[CaseFile]:
        return [case for case in self._cases.values() if case.person_id == person_id]

    def featured_case(self) -> CaseFile:
        featured = next((case for case in self._cases.values() if case.featured), None)
        if featured is None:
            raise RuntimeError("The docket must contain one featured case")
        return featured
