from __future__ import annotations

from pathlib import Path

from pipeline.submission_audit import audit_project, parse_frontmatter, parse_parameter_count


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_parse_frontmatter_reads_space_metadata() -> None:
    metadata = parse_frontmatter(
        """---
sdk: gradio
tags:
  - custom-ui
---

# App
"""
    )

    assert metadata["sdk"] == "gradio"
    assert metadata["tags"] == ["custom-ui"]


def test_parse_parameter_count_normalizes_units_to_billions() -> None:
    assert parse_parameter_count("8B") == 8
    assert parse_parameter_count("33.4M") == 0.0334


def test_submission_audit_separates_build_failures_from_launch_warnings() -> None:
    checks = audit_project(PROJECT_ROOT)

    assert not [item for item in checks if item.status == "fail"]
    assert any(
        item.launch_gate and item.status == "warn"
        for item in checks
    )
