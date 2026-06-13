---
license: other
pretty_name: AI Prophecy Court Presence
tags:
- social-media
- ai-leaders
- linkedin
- twitter
- parquet
configs:
- config_name: linkedin
  data_files:
  - split: train
    path: data/linkedin/*.parquet
- config_name: x
  data_files:
  - split: train
    path: data/x/*.parquet
---

# AI Prophecy Court Presence

Exploration-ready normalized records for AI Prophecy Court, a playful
hackathon project examining the public statements and social presence of major
AI leaders.

## Dataset configurations

- `linkedin`: original authored LinkedIn posts from four verified profiles
- `x`: posts, replies, quotes, and visible reposts from six verified profiles

Each row retains its source URL, publication time, content type, engagement
metadata, collection ID, run ID, and raw-payload checksum. Exact browser
responses and run manifests are preserved locally by the project and are not
published.

## Coverage

The release contains 2,117 records collected on June 13, 2026:

- LinkedIn: 1,051 records
- X: 1,066 records

## Limitations

This is an accessible-timeline dataset, not a complete historical export.
X stops exposing older profile cards at different depths for different
accounts. Clement Delangue's LinkedIn coverage currently ends on September 9,
2024. Media binaries are not redistributed; source media URLs may expire.

Use the source URLs and timestamps when quoting or interpreting a record.
Engagement values are point-in-time observations and can change.
