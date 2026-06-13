# AI Prophecy Court Data

Reproducible Browser Use collectors and normalized data for the public social
activity used by AI Prophecy Court.

## Retained dataset

- LinkedIn: 1,051 original authored posts from four manually verified profiles
- X: 1,066 accessible profile-timeline records from six verified profiles
- Public dataset:
  `build-small-hackathon/ai-prophecy-court-presence`

The exact successful raw envelopes and run manifests remain local under
`raw/browser-use/`. Browser profiles, cookies, failed runs, smoke tests, and
legacy mixed archives are intentionally excluded.

## Setup

```powershell
uv sync --extra dev --extra browser
$env:HF_TOKEN = "..."
```

Create a local authenticated browser profile only when another collection is
needed:

```powershell
uv run python scripts/collect_x_browser_use.py --setup-login
uv run python scripts/collect_linkedin_browser_use.py --setup-login
```

## Collect

```powershell
uv run python scripts/collect_x_browser_use.py `
  --person sam-altman `
  --max-posts 1000 `
  --max-scrolls 4000 `
  --user-data-dir profiles/x `
  --output raw/browser-use/x/sam-altman-full.jsonl.gz

uv run python scripts/collect_linkedin_browser_use.py `
  --person satya-nadella `
  --max-posts 1000 `
  --max-scrolls 2000 `
  --user-data-dir profiles/linkedin `
  --output raw/browser-use/linkedin/satya-nadella-full.jsonl.gz
```

Both collectors use deterministic CDP extraction by default. The optional
LLM agent mode remains available for unusual layouts.

## Normalize And Publish

`pipeline/normalize/records.py` converts raw envelopes to the stable Parquet
schema. `scripts/build_hf_release.py` builds the curated public release from
the normalized files.

```powershell
uv run python scripts/build_hf_release.py
.\scripts\hf.ps1 upload `
  build-small-hackathon/ai-prophecy-court-presence `
  hf-release\presence . `
  --type dataset
```

## Layout

```text
pipeline/registry.yaml          Verified people and source profiles
pipeline/normalize/             Raw-envelope normalization
scripts/collect_*               Browser Use collectors
scripts/build_hf_release.py     Curated release packaging
schemas/                        Raw and normalized schemas
raw/browser-use/                Successful local raw archives and manifests
normalized/browser-use/         Matching Parquet datasets
```

## Coverage Limitations

X exposes a bounded, algorithmic profile timeline even when authenticated, so
the X files are accessible-timeline captures rather than complete historical
exports. Clement Delangue's LinkedIn coverage currently reaches September 9,
2024. Media binaries are not downloaded, and source media URLs may expire.
