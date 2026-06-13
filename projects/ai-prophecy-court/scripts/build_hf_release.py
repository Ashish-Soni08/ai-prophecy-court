"""Build curated Hugging Face release folders for AI Prophecy Court."""

from __future__ import annotations

import gzip
import hashlib
import json
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELEASE_ROOT = ROOT / "hf-release"

LINKEDIN_STEMS = [
    "jensen-huang-full",
    "sundar-pichai-full",
    "satya-nadella-full",
    "clement-delangue-part-01",
    "clement-delangue-part-02",
    "clement-delangue-part-03",
    "clement-delangue-part-04",
]
X_STEMS = [
    "sam-altman-full",
    "dario-amodei-full",
    "sundar-pichai-full",
    "satya-nadella-full",
    "clement-delangue-full",
    "elon-musk-full",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def copy_file(
    source: Path,
    destination: Path,
    *,
    repository: str,
    repository_root: Path,
) -> dict[str, object]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return {
        "repository": repository,
        "path": destination.relative_to(repository_root).as_posix(),
        "bytes": destination.stat().st_size,
        "sha256": sha256(destination),
    }


def raw_stats(path: Path) -> dict[str, object]:
    people: Counter[str] = Counter()
    content_types: Counter[str] = Counter()
    dates: list[str] = []
    records = 0
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            envelope = json.loads(line)
            payload = envelope["payload"]
            records += 1
            people[payload["person_id"]] += 1
            content_types[payload.get("content_type") or "unknown"] += 1
            if payload.get("published_at"):
                dates.append(payload["published_at"])
    return {
        "records": records,
        "people": dict(sorted(people.items())),
        "content_types": dict(sorted(content_types.items())),
        "oldest_published_at": min(dates) if dates else None,
        "newest_published_at": max(dates) if dates else None,
    }


def reset_release_dir() -> Path:
    public_release = RELEASE_ROOT / "presence"
    public_release.mkdir(parents=True, exist_ok=True)
    for generated in ("data", "schemas"):
        generated_path = public_release / generated
        if generated_path.exists():
            shutil.rmtree(generated_path)
    (public_release / "pipeline-release.json").unlink(missing_ok=True)
    return public_release


def build() -> None:
    public_release = reset_release_dir()
    files: list[dict[str, object]] = []
    collections: list[dict[str, object]] = []

    for platform, stems in (("linkedin", LINKEDIN_STEMS), ("x", X_STEMS)):
        for stem in stems:
            raw_source = ROOT / "raw" / "browser-use" / platform / f"{stem}.jsonl.gz"
            parquet_source = (
                ROOT / "normalized" / "browser-use" / platform / f"{stem}.parquet"
            )
            for required in (raw_source, parquet_source):
                if not required.exists():
                    raise FileNotFoundError(required)

            parquet_destination = (
                public_release / "data" / platform / parquet_source.name
            )
            files.append(
                copy_file(
                    parquet_source,
                    parquet_destination,
                    repository="presence",
                    repository_root=public_release,
                )
            )
            collections.append(
                {
                    "platform": platform,
                    "archive": raw_source.name,
                    **raw_stats(raw_source),
                }
            )

    for schema in (ROOT / "schemas" / "normalized-content.schema.json",):
        files.append(
            copy_file(
                schema,
                public_release / "schemas" / schema.name,
                repository="presence",
                repository_root=public_release,
            )
        )

    generated_at = datetime.now(timezone.utc).isoformat()
    release = {
        "release_version": "2026-06-13-browser-use",
        "generated_at": generated_at,
        "collection_method": "browser-use deterministic CDP",
        "collections": collections,
        "total_records": sum(int(item["records"]) for item in collections),
        "files": files,
        "limitations": [
            "X profile timelines expose only a bounded algorithmic history.",
            "Clement Delangue LinkedIn coverage ends on 2024-09-09.",
            "No downloaded media binaries are included; source media URLs may expire.",
        ],
    }
    release_json = json.dumps(release, ensure_ascii=False, indent=2) + "\n"
    (public_release / "pipeline-release.json").write_text(
        release_json, encoding="utf-8", newline="\n"
    )
    print(json.dumps(release, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    build()
