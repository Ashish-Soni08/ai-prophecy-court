# AI Prophecy Court

AI Prophecy Court is a Chapter Two Build Small Hackathon app that turns
preserved public AI predictions into source-linked roast battles. Two small
models receive the same evidence and safety profile; the visitor votes before
the model identities are revealed.

## Current Product

- Custom React/TypeScript interface served by `gradio.Server`
- One human-reviewed featured case and seven leader dossiers
- Technical, guarded-dark, and dad-joke roast profiles
- Blind Nemotron 4B versus MiniCPM 8B comparison
- Anonymous session votes with optional aggregate Modal persistence
- Downloadable 1200x1500 verdict cards with source IDs and social captions
- Reviewed curated fallback when live inference is unavailable
- Deterministic screening of 2,117 normalized social records into 483 docket
  candidates

## Run Locally

```powershell
cd projects/ai-prophecy-court

uv sync --extra dev --extra space
npm --prefix space/frontend ci
npm --prefix space/frontend run build
uv run python space/app.py
```

Open `http://127.0.0.1:7860`.

The app works without external secrets. To activate the optional live runtime,
copy `.env.example` and set:

```text
MODAL_RUNTIME_URL=
MODAL_RUNTIME_TOKEN=
```

## Test

```powershell
uv run pytest -q
npm --prefix space/frontend run test
npm --prefix space/frontend run build
npm --prefix space/frontend run test:e2e
```

## Submission Audit

Run the local readiness audit before uploading or submitting:

```powershell
uv run python scripts/audit_submission.py
```

The default audit fails only on build-readiness problems and reports launch
blockers, such as missing public demo/social links or an unmerged Space PR, as
warnings. Use `--strict-launch` when you want those warnings to fail the run.

## Build The Docket Queue

The reproducible heuristic pass keeps model processing bounded and auditable:

```powershell
uv run python scripts/build_docket_candidates.py
```

It reads the normalized public release and writes scored source records to
`derived/docket/candidates.jsonl`. A later offline enrichment job may propose
charges, defenses, and court directions, but no case becomes featured without
human review.

## Architecture

```text
Hugging Face presence dataset
        |
        v
deterministic candidate builder
        |
        v
reviewed docket JSON ---> Gradio Server API ---> React + json-render UI
                                  |
                                  +-- curated battle (always available)
                                  |
                                  +-- authenticated Modal runtime (optional)
                                      |- Nemotron 4B
                                      |- MiniCPM 8B
                                      |- aggregate vote store
                                      `- VoxCPM2 adapter
```

See:

- `docs/product-spec.md` for the experience contract
- `docs/partners/README.md` for partner choices
- `docs/submission-checklist.md` for hackathon readiness
- `docs/deployment-status.md` for the current GitHub and Hugging Face deploy state
- `docs/demo-script.md` for the repeatable demo-video recording flow
- `docs/social-post-drafts.md` for ready-to-fill social copy
- `runtime/README.md` for Modal deployment
- `runtime/model-manifest.yaml` for the parameter-cap audit

The Playwright suite runs the complete trial-to-verdict-card journey in
Chromium, checks direct routes, verifies keyboard navigation, and scans primary
pages for serious WCAG A/AA violations with axe.

## Retained Data

- LinkedIn: 1,051 original authored posts from four manually verified profiles
- X: 1,066 accessible profile-timeline records from six verified profiles
- Public dataset: `build-small-hackathon/ai-prophecy-court-presence`

Exact successful raw envelopes remain local under `raw/browser-use/`. Browser
profiles, cookies, failed runs, smoke tests, and legacy mixed archives are
excluded. X coverage is an accessible algorithmic timeline, not a complete
historical export.

## Deployment

GitHub is the canonical source. The deploy workflow tests and bundles the
frontend, creates a Space subtree commit, and pushes it to
`build-small-hackathon/ai-prophecy-court`. Generated assets are included only
in the Space deployment commit.
