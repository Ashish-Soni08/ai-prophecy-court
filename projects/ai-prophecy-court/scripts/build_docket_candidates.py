"""Create reproducible model-enrichment inputs from normalized Parquet."""

from __future__ import annotations

import argparse
from pathlib import Path

from pipeline.docket import build_candidates


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("hf-release/presence/data"),
        help="Root containing normalized platform Parquet files.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("derived/docket/candidates.jsonl"),
    )
    parser.add_argument("--minimum-score", type=int, default=18)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    candidates = build_candidates(args.input, args.output, args.minimum_score)
    print(f"Wrote {len(candidates)} candidates to {args.output}")


if __name__ == "__main__":
    main()
