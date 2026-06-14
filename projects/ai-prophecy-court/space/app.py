"""AI Prophecy Court custom frontend and Gradio API server."""

from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from gradio import Server

from backend.repository import DocketRepository
from backend.runtime import ModalRuntime
from backend.service import CourtService

ROOT = Path(__file__).resolve().parent
FRONTEND_DIST = ROOT / "frontend" / "dist"
ASSETS_DIR = FRONTEND_DIST / "assets"

repository = DocketRepository.from_json(ROOT / "data" / "docket.json")
court = CourtService(repository, runtime=ModalRuntime.from_environment())
app = Server()


@app.get("/api/bootstrap")
def bootstrap() -> JSONResponse:
    return JSONResponse(court.bootstrap().model_dump(mode="json"))


@app.get("/api/leaders/{person_id}")
def leader_detail(person_id: str) -> JSONResponse:
    leader = court.leader_detail(person_id)
    if leader is None:
        raise HTTPException(status_code=404, detail="Leader not found")
    return JSONResponse(leader.model_dump(mode="json"))


@app.get("/api/cases/{case_id}")
def case_detail(case_id: str) -> JSONResponse:
    case = repository.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    return JSONResponse(case.model_dump(mode="json"))


@app.api(name="convene_trial")
def convene_trial(case_id: str, style: str, session_id: str = "") -> str:
    """Return a validated trial payload for Gradio's queued client."""
    payload = court.convene(case_id=case_id, style=style, session_id=session_id)
    return payload.model_dump_json()


@app.api(name="record_vote")
def record_vote(
    case_id: str,
    style: str,
    choice: str,
    session_id: str = "",
) -> str:
    """Record an anonymous local vote and reveal the competing models."""
    reveal = court.record_vote(
        case_id=case_id,
        style=style,
        choice=choice,
        session_id=session_id,
    )
    return reveal.model_dump_json()


@app.api(name="synthesize_verdict")
def synthesize_verdict(case_id: str, style: str, winner: str, text: str) -> str:
    """Return a VoxCPM2 asset when the optional Modal runtime is configured."""
    return court.voice_asset(
        case_id=case_id,
        style=style,
        winner=winner,
        text=text,
    ).model_dump_json()


if ASSETS_DIR.exists():
    app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="frontend-assets")


def frontend_response() -> FileResponse | JSONResponse:
    index = FRONTEND_DIST / "index.html"
    if index.exists():
        return FileResponse(index)

    return JSONResponse(
        {
            "status": "frontend_not_built",
            "message": "Run npm install && npm run build in space/frontend.",
            "api": {
                "bootstrap": "/api/bootstrap",
                "gradio": ["/convene_trial", "/record_vote", "/synthesize_verdict"],
            },
        },
        status_code=503,
    )


@app.get("/", response_model=None)
def homepage() -> FileResponse | JSONResponse:
    return frontend_response()


@app.get("/archive", response_model=None)
def archive_page() -> FileResponse | JSONResponse:
    return frontend_response()


@app.get("/people/{person_id}", response_model=None)
def dossier_page(person_id: str) -> FileResponse | JSONResponse:
    del person_id
    return frontend_response()


if __name__ == "__main__":
    app.launch(
        server_name=os.getenv("GRADIO_SERVER_NAME", "0.0.0.0"),
        server_port=int(os.getenv("GRADIO_SERVER_PORT", "7860")),
        show_error=True,
    )
