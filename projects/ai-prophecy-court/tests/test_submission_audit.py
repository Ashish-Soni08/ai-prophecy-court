from __future__ import annotations

import json
from pathlib import Path

from pipeline.submission_audit import audit_project, parse_frontmatter, parse_parameter_count


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


def test_submission_audit_separates_build_failures_from_launch_warnings(
    tmp_path: Path,
) -> None:
    (tmp_path / "space" / "frontend" / "dist" / "assets").mkdir(parents=True)
    (tmp_path / "space" / "data").mkdir(parents=True)
    (tmp_path / "runtime").mkdir()
    (tmp_path / "docs").mkdir()

    (tmp_path / "space" / "README.md").write_text(
        """---
sdk: gradio
app_file: app.py
tags:
  - custom-ui
  - build-small-hackathon
  - thousand-token-wood
models:
  - model/a
---

Demo video and social showcase links will be added before final submission.
""",
        encoding="utf-8",
    )
    (tmp_path / "space" / "app.py").write_text(
        "from gradio import Server\napp = Server()\n",
        encoding="utf-8",
    )
    (tmp_path / "space" / "frontend" / "dist" / "index.html").write_text(
        "<div></div>",
        encoding="utf-8",
    )
    (tmp_path / "space" / "frontend" / "dist" / "assets" / "app.js").write_text(
        "console.log('ok')",
        encoding="utf-8",
    )
    (tmp_path / "runtime" / "model-manifest.yaml").write_text(
        "models:\n  - id: model/a\n    parameters: 8B\n",
        encoding="utf-8",
    )
    leaders = [
        {
            "id": f"leader-{index}",
            "name": f"Leader {index}",
            "company": "Example",
            "presence": [{"platform": "x", "status": "verified-active"}],
        }
        for index in range(7)
    ]
    (tmp_path / "space" / "data" / "docket.json").write_text(
        """{
  "leaders": %s,
  "cases": [
    {
      "id": "case-1",
      "featured": true,
      "evidence": {"canonical_url": "https://example.com/source"}
    }
  ]
}
"""
        % json.dumps(leaders),
        encoding="utf-8",
    )
    for name in [
        "product-spec.md",
        "demo-script.md",
        "social-post-drafts.md",
    ]:
        (tmp_path / "docs" / name).write_text("# doc\n", encoding="utf-8")
    (tmp_path / "docs" / "deployment-status.md").write_text(
        "Status: open, awaiting merge\n",
        encoding="utf-8",
    )

    checks = audit_project(tmp_path)

    assert not [item for item in checks if item.status == "fail"]
    assert any(
        item.launch_gate and item.status == "warn"
        for item in checks
    )
