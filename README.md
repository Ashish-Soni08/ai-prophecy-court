# Build Small Hackathon Workspace

This repository contains two separate projects:

[AI Prophecy Court on Hugging Face](https://huggingface.co/spaces/build-small-hackathon/ai-prophecy-court)
·
[Normalized presence dataset](https://huggingface.co/datasets/build-small-hackathon/ai-prophecy-court-presence)

## AI Prophecy Court

Location: `projects/ai-prophecy-court/`

The AI leader roast dashboard, Open Design mockup, Browser Use collection
pipeline, schemas, tests, and Hugging Face publication tools live together in
this folder. Collected raw and normalized data remain local and are excluded
from Git.

```powershell
cd projects\ai-prophecy-court
uv sync --extra dev --extra browser --extra space
uv run python -m pytest
```

## StudyFlow AI

Location: `projects/studyflow-ai/`

The Josephine study dashboard, local server, screenshots, design reviews, and
Open Design reference assets live together in this folder. It is maintained as
its own Git repository and is intentionally excluded from this parent repo.

```powershell
cd projects\studyflow-ai
node server.js
```
