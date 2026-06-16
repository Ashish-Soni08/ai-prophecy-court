# Deployment Status

Last checked: June 16, 2026.

## GitHub

- Draft PR: https://github.com/Ashish-Soni08/ai-prophecy-court/pull/1
- Head commit: `74c1da5f8baabbe5c821626208353d5bc8d0b0c0`
- CI: passing
- Coverage: Python tests, frontend unit tests, Vite production build, Playwright
  trial flow, verdict-card generation, keyboard navigation, and axe serious
  accessibility scan.

## Hugging Face Space

- Target Space: https://huggingface.co/spaces/build-small-hackathon/ai-prophecy-court
- Deployment PR: https://huggingface.co/spaces/build-small-hackathon/ai-prophecy-court/discussions/1
- Status: open, awaiting merge by an account with write permission on the
  `build-small-hackathon` Space.

The local CLI authenticated as `ashish-soni08`, confirmed membership in
`build-small-hackathon`, and successfully uploaded the deployment as a Space
pull request. Direct commit and merge attempts returned `403 Forbidden` because
the token has read access but lacks the required write permission for the org
Space.

## Next Action

Have an org maintainer merge Hugging Face Space PR #1, or provide a token with
write permission for `build-small-hackathon/ai-prophecy-court` and rerun:

```powershell
hf upload build-small-hackathon/ai-prophecy-court `
  projects/ai-prophecy-court/space . `
  --repo-type space `
  --exclude "frontend/node_modules/**" `
  --exclude "frontend/test-results/**" `
  --exclude "frontend/playwright-report/**" `
  --exclude "frontend/.vite/**" `
  --commit-message "Deploy AI Prophecy Court V1" `
  --commit-description "Deploy the custom Gradio Server app, built React frontend, typed backend, and reviewed docket.`n`nCo-authored-by: Codex <noreply@openai.com>"
```
