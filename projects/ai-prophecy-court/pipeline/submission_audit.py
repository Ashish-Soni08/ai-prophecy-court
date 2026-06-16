"""Submission readiness checks for AI Prophecy Court."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Literal

import yaml

Status = Literal["pass", "warn", "fail"]


@dataclass(frozen=True)
class AuditCheck:
    name: str
    status: Status
    detail: str
    launch_gate: bool = False


def parse_frontmatter(readme: str) -> dict[str, object]:
    if not readme.startswith("---\n"):
        return {}
    _, raw, _ = readme.split("---", 2)
    parsed = yaml.safe_load(raw) or {}
    if not isinstance(parsed, dict):
        return {}
    return parsed


def parse_parameter_count(value: object) -> float:
    text = str(value).strip().upper()
    match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)([BMG])", text)
    if match is None:
        raise ValueError(f"Unsupported parameter value: {value!r}")
    amount = float(match.group(1))
    unit = match.group(2)
    if unit == "B":
        return amount
    if unit == "M":
        return amount / 1_000
    return amount / 1_000_000


def check(condition: bool, name: str, pass_detail: str, fail_detail: str) -> AuditCheck:
    return AuditCheck(name=name, status="pass" if condition else "fail", detail=pass_detail if condition else fail_detail)


def audit_project(root: Path) -> list[AuditCheck]:
    root = root.resolve()
    space = root / "space"
    checks: list[AuditCheck] = []

    space_readme_path = space / "README.md"
    space_readme = space_readme_path.read_text(encoding="utf-8")
    metadata = parse_frontmatter(space_readme)
    tags = set(metadata.get("tags") or [])
    models = list(metadata.get("models") or [])

    checks.append(
        check(
            metadata.get("sdk") == "gradio" and metadata.get("app_file") == "app.py",
            "Space metadata declares a Gradio app",
            "Space README uses sdk: gradio and app_file: app.py.",
            "Space README must declare sdk: gradio and app_file: app.py.",
        )
    )
    checks.append(
        check(
            {"custom-ui", "build-small-hackathon", "thousand-token-wood"}.issubset(tags),
            "Space README has hackathon/custom UI tags",
            "Required Space tags are present.",
            "Missing one or more required Space tags.",
        )
    )

    app_py = (space / "app.py").read_text(encoding="utf-8")
    checks.append(
        check(
            "from gradio import Server" in app_py and "app = Server()" in app_py,
            "Backend is served by gradio.Server",
            "app.py imports and instantiates gradio.Server.",
            "app.py does not clearly instantiate gradio.Server.",
        )
    )

    dist = space / "frontend" / "dist"
    checks.append(
        check(
            (dist / "index.html").exists() and any((dist / "assets").glob("*.js")),
            "Custom frontend is built for Space upload",
            "frontend/dist contains index.html and JavaScript assets.",
            "Run npm --prefix space/frontend run build before uploading the Space.",
        )
    )

    manifest_path = root / "runtime" / "model-manifest.yaml"
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    model_rows = manifest.get("models", [])
    over_cap = [
        row["id"]
        for row in model_rows
        if parse_parameter_count(row.get("parameters", "999B")) >= 32
    ]
    checks.append(
        check(
            not over_cap and all(model in {row["id"] for row in model_rows} for model in models),
            "Selected models are below 32B",
            "Manifest model parameters are under the hackathon cap.",
            f"Model cap or README manifest mismatch: {', '.join(over_cap) or 'metadata mismatch'}.",
        )
    )

    docket = json.loads((space / "data" / "docket.json").read_text(encoding="utf-8"))
    leaders = docket.get("leaders", [])
    cases = docket.get("cases", [])
    featured = [case for case in cases if case.get("featured")]
    source_urls = [
        case.get("evidence", {}).get("canonical_url")
        for case in cases
        if case.get("evidence", {}).get("canonical_url")
    ]
    checks.append(
        check(
            len(leaders) == 7 and len(featured) == 1 and bool(source_urls),
            "Docket has seven leaders, one featured case, and source URLs",
            "Reviewed docket has the expected launch shape.",
            "Docket must include seven leaders, exactly one featured case, and source URLs.",
        )
    )
    checks.append(
        check(
            all(leader.get("presence") for leader in leaders),
            "Leader dossiers include platform presence",
            "Every leader includes platform presence records.",
            "One or more leaders lacks platform presence records.",
        )
    )

    docs = {
        "product spec": root / "docs" / "product-spec.md",
        "demo script": root / "docs" / "demo-script.md",
        "social drafts": root / "docs" / "social-post-drafts.md",
        "deployment status": root / "docs" / "deployment-status.md",
    }
    missing_docs = [name for name, path in docs.items() if not path.exists()]
    checks.append(
        check(
            not missing_docs,
            "Submission support docs exist",
            "Product, demo, social, and deployment docs are present.",
            f"Missing docs: {', '.join(missing_docs)}.",
        )
    )

    demo = space / "frontend" / "demo-output" / "ai-prophecy-court-demo.webm"
    checks.append(
        AuditCheck(
            name="Local demo video artifact exists",
            status="pass" if demo.exists() and demo.stat().st_size > 0 else "warn",
            detail=(
                f"Local recording exists at {demo.relative_to(root)}."
                if demo.exists()
                else "Run npm --prefix space/frontend run record:demo before final upload."
            ),
            launch_gate=True,
        )
    )

    launch_links_missing = "Demo video and social showcase links will be added" in space_readme
    checks.append(
        AuditCheck(
            name="Public demo and social links are attached",
            status="warn" if launch_links_missing else "pass",
            detail=(
                "Space README still has final-link placeholders."
                if launch_links_missing
                else "Space README includes final public demo/social links."
            ),
            launch_gate=True,
        )
    )

    deploy_status = (root / "docs" / "deployment-status.md").read_text(encoding="utf-8")
    checks.append(
        AuditCheck(
            name="Hugging Face Space deployment is merged",
            status="warn" if "Status: open, awaiting merge" in deploy_status else "pass",
            detail=(
                "Latest Space deployment PR is still awaiting maintainer merge."
                if "Status: open, awaiting merge" in deploy_status
                else "Deployment status doc no longer reports an open Space PR."
            ),
            launch_gate=True,
        )
    )

    return checks


def summarize(checks: Iterable[AuditCheck]) -> str:
    icons = {"pass": "PASS", "warn": "WARN", "fail": "FAIL"}
    lines = ["AI Prophecy Court submission audit", ""]
    for item in checks:
        suffix = " [launch]" if item.launch_gate else ""
        lines.append(f"{icons[item.status]} {item.name}{suffix}: {item.detail}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--strict-launch",
        action="store_true",
        help="Treat launch-gate warnings as failures.",
    )
    args = parser.parse_args(argv)

    checks = audit_project(args.root)
    print(summarize(checks))

    if any(item.status == "fail" for item in checks):
        return 1
    if args.strict_launch and any(item.status == "warn" and item.launch_gate for item in checks):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
