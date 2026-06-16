## Summary

- Replace the placeholder Space with a typed Gradio `Server` backend and a source-backed, human-reviewed docket.
- Add the custom React/TypeScript/Vite/shadcn/json-render courtroom UI with blind two-model roast battles, dossier pages, archive, verdict cards, and deterministic leader sigils.
- Add deterministic docket screening, Modal runtime interfaces, aggregate vote storage, voice-adapter placeholder, model-cap manifest, CI, and hackathon submission docs.
- Add a repeatable submission-readiness audit that separates build-readiness failures from final launch gates.

## Verification

- `uv run --extra dev --extra space --extra runtime pytest -q` passes with 113 tests.
- `npm run test` passes with 3 frontend test files and 6 tests.
- `npm run build` passes and produces the Space-served `frontend/dist` bundle.
- `npm run test:e2e` passes the trial-to-verdict-card flow, keyboard navigation, and axe serious accessibility checks.
- `uv run python scripts/audit_submission.py` passes build-readiness checks and reports the expected launch warnings.
- GitHub Actions `Test AI Prophecy Court` is passing on the PR branch.

## Deployment State

- Latest Hugging Face Space deployment PR: https://huggingface.co/spaces/build-small-hackathon/ai-prophecy-court/discussions/2
- Latest uploaded Space commit: `238d88ab8ebad0e8010fb10ceb4198eeb2ef2b93`.

## Intentionally Pending Before Final Hackathon Submission

- Merge Hugging Face Space PR #2, or provide a token with write permission to the org Space.
- Upload and link the final demo video.
- Publish and link one social-media showcase post.
- Optional: deploy live Modal model endpoints and configure VoxCPM2 audio. The app already works without those secrets through reviewed curated fallbacks.

All implementation commits include the Codex co-author trailer.
