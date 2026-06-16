"""Modal gateway for live roast battles, votes, and optional voice synthesis.

Deploy with:
    modal deploy runtime/modal_app.py

The ``ai-prophecy-court-runtime`` Modal Secret must contain ``AUTH_TOKEN``.
Optional OpenAI-compatible model endpoints use the environment variables
documented in ``runtime/README.md``.
"""

import asyncio
import hmac
import os
import sqlite3
from pathlib import Path
from typing import Literal

import modal

APP_NAME = "ai-prophecy-court-runtime"
STATE_DIR = Path("/state")
DATABASE_PATH = STATE_DIR / "feedback.sqlite3"

app = modal.App(APP_NAME)
state = modal.Volume.from_name("ai-prophecy-court-feedback", create_if_missing=True)
secret = modal.Secret.from_name("ai-prophecy-court-runtime")
image = modal.Image.debian_slim(python_version="3.11").pip_install(
    "fastapi[standard]>=0.115,<1",
    "httpx>=0.28,<1",
    "pydantic>=2.11,<3",
)


@app.function(
    image=image,
    secrets=[secret],
    volumes={str(STATE_DIR): state},
    max_containers=1,
    timeout=120,
)
@modal.asgi_app()
def runtime_api():
    import httpx
    from fastapi import Depends, FastAPI, HTTPException, status
    from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
    from pydantic import BaseModel, ConfigDict, Field

    api = FastAPI(title="AI Prophecy Court Runtime", version="1.0.0")
    bearer = HTTPBearer(auto_error=False)

    class StrictModel(BaseModel):
        model_config = ConfigDict(extra="forbid")

    class Evidence(StrictModel):
        content_id: str
        platform: str
        canonical_url: str
        published_at: str
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
        verdict: str
        review_status: str
        roastability: int = Field(ge=0, le=100)
        confidence: int = Field(ge=0, le=100)
        court_direction: str
        featured: bool = False

    class BattleRequest(StrictModel):
        case: CaseFile
        style: Literal["technical", "dark", "dad-joke"]

    class VoteRequest(StrictModel):
        case_id: str
        style: Literal["technical", "dark", "dad-joke"]
        choice: Literal["a", "b", "both", "dismissed"]

    class VoiceRequest(StrictModel):
        case_id: str
        style: Literal["technical", "dark", "dad-joke"]
        winner: str
        text: str = Field(min_length=1, max_length=1200)

    async def authorize(
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    ) -> None:
        expected = os.environ["AUTH_TOKEN"]
        if credentials is None or not hmac.compare_digest(
            credentials.credentials,
            expected,
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect bearer token",
                headers={"WWW-Authenticate": "Bearer"},
            )

    def initialize_database() -> None:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(DATABASE_PATH) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS votes (
                    case_id TEXT NOT NULL,
                    style TEXT NOT NULL,
                    choice TEXT NOT NULL,
                    count INTEGER NOT NULL,
                    PRIMARY KEY (case_id, style, choice)
                )
                """
            )
            connection.commit()

    async def generate_roast(
        *,
        base_url_env: str,
        token_env: str,
        model_env: str,
        fallback_model: str,
        request: BattleRequest,
    ) -> dict[str, object]:
        base_url = os.getenv(base_url_env, "").rstrip("/")
        token = os.getenv(token_env, "")
        model = os.getenv(model_env, fallback_model)
        if not base_url or not token:
            raise HTTPException(
                status_code=503,
                detail=f"{fallback_model} endpoint is not configured",
            )

        system = (
            "You are one advocate in AI Prophecy Court. Roast the rhetoric of a "
            "public claim without attacking identity, appearance, family, or private "
            "life. Stay faithful to the supplied evidence. Return one concise roast "
            "under 70 words, with no markdown and no invented facts."
        )
        user = (
            f"Style: {request.style}\n"
            f"Claim: {request.case.evidence.exact_text}\n"
            f"Charge: {request.case.charge}\n"
            f"Fair defense: {request.case.fair_defense}\n"
            f"Court direction: {request.case.court_direction}"
        )
        async with httpx.AsyncClient(timeout=28.0) as client:
            response = await client.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "model": model,
                    "temperature": 0.85,
                    "max_tokens": 160,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                },
            )
            response.raise_for_status()
            payload = response.json()
        text = payload["choices"][0]["message"]["content"].strip()
        return {"text": text, "model_id": model}

    @api.get("/health")
    async def health(_: None = Depends(authorize)) -> dict[str, str]:
        return {"status": "ok"}

    @api.post("/roast-battle")
    async def roast_battle(
        request: BattleRequest,
        _: None = Depends(authorize),
    ) -> dict[str, object]:
        try:
            first, second = await asyncio.gather(
                generate_roast(
                    base_url_env="NEMOTRON_BASE_URL",
                    token_env="NEMOTRON_API_KEY",
                    model_env="NEMOTRON_MODEL_ID",
                    fallback_model="nvidia/NVIDIA-Nemotron-3-Nano-4B-BF16",
                    request=request,
                ),
                generate_roast(
                    base_url_env="MINICPM_BASE_URL",
                    token_env="MINICPM_API_KEY",
                    model_env="MINICPM_MODEL_ID",
                    fallback_model="openbmb/MiniCPM4.1-8B",
                    request=request,
                ),
            )
        except (httpx.HTTPError, KeyError, TypeError, AttributeError) as exc:
            raise HTTPException(status_code=503, detail="Model chamber unavailable") from exc

        return {
            "judge_intro": (
                "The source is admitted. Both advocates received the same evidence "
                "packet and safety instructions."
            ),
            "roasts": [
                {
                    "slot": "A",
                    "text": first["text"],
                    "model_id": first["model_id"],
                    "cached": False,
                },
                {
                    "slot": "B",
                    "text": second["text"],
                    "model_id": second["model_id"],
                    "cached": False,
                },
            ],
        }

    @api.post("/votes")
    async def record_vote(
        request: VoteRequest,
        _: None = Depends(authorize),
    ) -> dict[str, object]:
        initialize_database()
        with sqlite3.connect(DATABASE_PATH, timeout=10) as connection:
            connection.execute(
                """
                INSERT INTO votes (case_id, style, choice, count)
                VALUES (?, ?, ?, 1)
                ON CONFLICT(case_id, style, choice)
                DO UPDATE SET count = count + 1
                """,
                (request.case_id, request.style, request.choice),
            )
            rows = connection.execute(
                "SELECT choice, count FROM votes WHERE case_id = ? AND style = ?",
                (request.case_id, request.style),
            ).fetchall()
            connection.commit()
        state.commit()
        return {"stored": True, "aggregate": dict(rows)}

    @api.post("/voice")
    async def synthesize_voice(
        request: VoiceRequest,
        _: None = Depends(authorize),
    ) -> dict[str, object]:
        return {
            "case_id": request.case_id,
            "style": request.style,
            "winner": request.winner,
            "status": "not-configured",
            "audio_url": None,
            "message": "VoxCPM2 adapter is reserved but not deployed.",
        }

    return api
