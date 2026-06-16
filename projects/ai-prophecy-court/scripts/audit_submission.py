"""Run the AI Prophecy Court submission readiness audit."""

from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.submission_audit import main


if __name__ == "__main__":
    raise SystemExit(main(["--root", str(PROJECT_ROOT), *sys.argv[1:]]))
