# AI Prophecy Court V1 Product Specification

Status: implemented baseline, June 14, 2026.

## Product Promise

AI Prophecy Court turns preserved public AI predictions into a delightful
source-linked trial. Two small models receive the same evidence and roast
profile. Visitors vote before model identities are revealed.

The experience is a rhetorical court, not a factual adjudication system.

## Primary Journey

1. The homepage opens with one featured, human-reviewed case.
2. The visitor reads the exact source excerpt, charge, fair defense, and court
   rationale.
3. The visitor chooses `technical`, `dark`, or `dad-joke`.
4. `Convene Court` requests two roasts with an immutable shared evidence packet.
5. The interface labels the outputs only `A` and `B`.
6. The visitor votes `A`, `B`, `both`, or `dismissed`.
7. The app reveals the model identities and aggregate reaction state.
8. When configured, a visitor who chose A or B can request a voice rendition.

## Routes

| Route | Responsibility |
| --- | --- |
| `/` | Featured evidence, roast battle, jury vote, leader directory |
| `/people/:personId` | One leader's source presence and reviewed case files |
| `/archive` | Human-reviewed precedent available in the current docket |

All routes must work when opened directly, not only after client navigation.

## Backend Contract

Read endpoints:

- `GET /api/bootstrap`
- `GET /api/leaders/{person_id}`
- `GET /api/cases/{case_id}`

Queued Gradio API functions:

- `/convene_trial(case_id, style, session_id)`
- `/record_vote(case_id, style, choice, session_id)`
- `/synthesize_verdict(case_id, style, winner, text)`

Pydantic models reject unknown fields at the backend boundary. Zod validates
the same payloads before the frontend uses them.

## Evidence Rules

- Every case identifies a stable `content_id`.
- Exact source text and a display excerpt are stored separately.
- Every quote has a canonical source URL and publication time.
- Only `human-reviewed` cases may be featured or added to precedent.
- Model-generated enrichment may propose metadata but cannot silently rewrite
  source text or promote a case.
- X data represents the accessible profile timeline, not complete history.

## Model Roles

| Role | Model | Parameters | Execution |
| --- | --- | --- | --- |
| Roast A | NVIDIA Nemotron 3 Nano 4B | 4B | Optional live Modal endpoint |
| Roast B and offline analysis | MiniCPM4.1 | 8B | Optional live Modal endpoint |
| Screening and court direction | MiniCPM5 | 1B | Offline enrichment |
| Verdict voice | VoxCPM2 | 2B | Reserved Modal adapter |
| Portrait/card artwork | FLUX.2 Klein | 4B | Offline, human-reviewed |
| Similarity and deduplication | BGE small English | 33.4M | Offline batch |

Every model is strictly below the 32B hackathon cap.

## Runtime Behavior

The Gradio Space is the public application boundary. Modal is optional.

When `MODAL_RUNTIME_URL` and `MODAL_RUNTIME_TOKEN` exist:

- the Space asks the authenticated Modal gateway for both roasts;
- both model calls use the same evidence and safety instructions;
- the gateway targets a 28-second provider timeout;
- aggregate votes are persisted in single-writer SQLite on a Modal Volume.

When live inference is missing, slow, malformed, or unavailable:

- the Space returns a reviewed curated battle;
- it identifies the fallback in the typed response;
- the visitor can still complete the full trial and reveal flow.

No visitor identity, IP address, cookie, or free-form visitor text is stored.

## Roast Guardrails

Roasts may challenge:

- scope inflation;
- vague timelines;
- benchmark overreach;
- rhetorical certainty;
- contradiction inside the admitted evidence.

Roasts may not target:

- protected identity;
- appearance or disability;
- family or private relationships;
- health, sexuality, or private life;
- invented behavior or unverified allegations.

The guarded-dark profile changes theatrical tone, not safety boundaries.

## Frontend Architecture

- React 19 and TypeScript
- Vite production build
- React Router with lazy route loading
- TanStack Query for read state
- shadcn-style local primitives for stable controls
- `json-render` for evidence and battle scenes
- Framer Motion for short state transitions
- `@gradio/client` for queued mutation calls

The shell remains conventional React. AI-generated JSON cannot select arbitrary
components, inject HTML, navigate, or execute code.

## Acceptance Criteria

- Homepage, archive, and every leader dossier return `200` directly.
- Bootstrap contains seven leaders and one featured human-reviewed case.
- Each roast profile returns exactly two schema-valid candidates.
- Model identities are absent from rendered battle cards until voting.
- Invalid case IDs, vote choices, and roast styles are rejected.
- A runtime outage completes through the curated fallback.
- Source URLs remain visible and clickable.
- Python tests, frontend tests, and the Vite production build pass.
- CI builds `frontend/dist` before creating the Hugging Face Space subtree.
- Demo and social links remain visibly pending until real URLs exist.

## Deliberately Deferred

- Full-dataset automatic case publication
- External fact checking
- User-submitted targets or free-form roast prompts
- Shareable verdict card generation
- Reviewed FLUX leader portraits
- Deployed VoxCPM2 synthesis
- Multilingual verdicts
- Roast-style fine-tuning
