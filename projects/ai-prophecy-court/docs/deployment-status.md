# Deployment Status

Last checked: June 16, 2026.

## GitHub

- PR: https://github.com/Ashish-Soni08/ai-prophecy-court/pull/1
- Head commit: see the current PR head on GitHub.
- CI: passing
- Coverage: Python tests, frontend unit tests, Vite production build,
  submission-readiness audit, Playwright trial flow, verdict-card generation,
  keyboard navigation, axe serious accessibility scan, and local demo-video
  recording.

## Hugging Face Space

- Target Space: https://huggingface.co/spaces/build-small-hackathon/ai-prophecy-court
- Latest deployment PR: https://huggingface.co/spaces/build-small-hackathon/ai-prophecy-court/discussions/2
- Superseded deployment PR: https://huggingface.co/spaces/build-small-hackathon/ai-prophecy-court/discussions/1
- Status: open, awaiting merge by an account with write permission on the
  `build-small-hackathon` Space.
- Latest uploaded Space commit: `238d88ab8ebad0e8010fb10ceb4198eeb2ef2b93`

The local CLI authenticated as `ashish-soni08`, confirmed membership in
`build-small-hackathon`. The `hf` executable currently points at a stale
uv-managed Python path, so the latest upload used `huggingface_hub.HfApi`
through the project uv environment. Direct commit and merge attempts returned
`403 Forbidden` because the token has read access but lacks the required write
permission for the org Space.

## Next Action

Have an org maintainer merge Hugging Face Space PR #2, or provide a token with
write permission for `build-small-hackathon/ai-prophecy-court` and rerun:

```powershell
cd C:\Users\Lenovo\Documents\build-small-hackathon\projects\ai-prophecy-court
npm --prefix space/frontend run build

$env:UV_CACHE_DIR=(Resolve-Path .uv-cache)
$env:UV_PYTHON_INSTALL_DIR=(Resolve-Path .uv-python)

@'
from huggingface_hub import HfApi

HfApi().upload_folder(
    repo_id="build-small-hackathon/ai-prophecy-court",
    repo_type="space",
    folder_path="space",
    path_in_repo=".",
    ignore_patterns=[
        "frontend/node_modules/**",
        "frontend/test-results/**",
        "frontend/playwright-report/**",
        "frontend/.vite/**",
        "frontend/demo-output/**",
    ],
    commit_message="Deploy AI Prophecy Court V1 polish",
    commit_description=(
        "Deploy the latest custom Gradio Server app with courtroom leader "
        "sigils, built React frontend, typed backend, and reviewed docket.\n\n"
        "Co-authored-by: Codex <noreply@openai.com>"
    ),
    create_pr=True,
)
'@ | uv run --with huggingface_hub python -
```
