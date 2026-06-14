# Modal Runtime Contract

The Gradio Space is fully usable from curated docket assets without Modal.
Live services activate only when both Space secrets are configured:

```text
MODAL_RUNTIME_URL
MODAL_RUNTIME_TOKEN
```

The authenticated runtime exposes:

- `POST /roast-battle`: runs Nemotron 3 Nano 4B and MiniCPM4.1-8B in
  parallel against one immutable evidence packet.
- `POST /votes`: stores anonymous aggregate feedback in a single-writer
  SQLite database on a Modal Volume.
- `POST /voice`: synthesizes the selected judge introduction or winning roast
  with VoxCPM2.

FLUX and docket enrichment are offline jobs. They publish reviewed artifacts
to the derived Hugging Face docket dataset rather than blocking a visitor's
trial.

Every endpoint must require bearer authentication, validate the shared
Pydantic-compatible schema, and omit user identity, IP address, and free-form
user text from persistence.

## Deploy

Create a Modal Secret named `ai-prophecy-court-runtime`:

```text
AUTH_TOKEN=<random shared bearer token>
NEMOTRON_BASE_URL=<OpenAI-compatible base URL>
NEMOTRON_API_KEY=<provider token>
NEMOTRON_MODEL_ID=nvidia/NVIDIA-Nemotron-3-Nano-4B-BF16
MINICPM_BASE_URL=<OpenAI-compatible base URL>
MINICPM_API_KEY=<provider token>
MINICPM_MODEL_ID=openbmb/MiniCPM4.1-8B
```

Then deploy the gateway:

```powershell
uv sync --extra runtime
uv run modal deploy runtime/modal_app.py
```

Set the resulting base URL and the same `AUTH_TOKEN` as the Space secrets
`MODAL_RUNTIME_URL` and `MODAL_RUNTIME_TOKEN`. The gateway deliberately
returns `503` when either model endpoint is absent, allowing the Space to fall
back to its reviewed curated battle. The vote endpoint writes only aggregate
case/style/choice counts to a single-container SQLite database on a Modal
Volume.
