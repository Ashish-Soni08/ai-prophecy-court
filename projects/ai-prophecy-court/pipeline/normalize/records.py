from __future__ import annotations

import gzip
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

NORMALIZED_SCHEMA = pa.schema(
    [
        ("content_id", pa.string()),
        ("person_id", pa.string()),
        ("platform", pa.string()),
        ("native_id", pa.string()),
        ("canonical_url", pa.string()),
        ("content_type", pa.string()),
        ("text", pa.string()),
        ("text_html", pa.string()),
        ("title", pa.string()),
        ("published_at", pa.string()),
        ("media_json", pa.string()),
        ("engagement_json", pa.string()),
        ("extracted_at", pa.string()),
        ("run_id", pa.string()),
        ("collection_id", pa.string()),
        ("raw_payload_sha256", pa.string()),
    ]
)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _native_id(payload: dict) -> str | None:
    value = payload.get("native_id")
    return str(value) if value else None


def _content_id(platform: str, payload: dict) -> str:
    native_id = _native_id(payload)
    if native_id:
        return f"{platform}:{native_id}"
    basis = (
        payload.get("canonical_url")
        or payload.get("url")
        or payload.get("input")
        or _json(payload)
    )
    digest = hashlib.sha256(str(basis).encode("utf-8")).hexdigest()[:24]
    return f"{platform}:sha256:{digest}"


def _engagement(payload: dict) -> dict:
    engagement = dict(payload.get("engagement") or {})
    profile_metrics = payload.get("profile_metrics") or {}
    engagement.setdefault("author_followers", profile_metrics.get("followers"))
    return engagement


def _media(payload: dict) -> Any:
    return payload.get("media") or {}


def normalize_envelope(envelope: dict) -> dict:
    payload = envelope["payload"]
    platform = envelope["platform"]
    text = payload.get("text") or payload.get("title")
    return {
        "content_id": _content_id(platform, payload),
        "person_id": envelope["person_id"],
        "platform": platform,
        "native_id": _native_id(payload) or "",
        "canonical_url": payload.get("canonical_url") or envelope["input_url"],
        "content_type": payload.get("content_type"),
        "text": text,
        "text_html": payload.get("text_html"),
        "title": payload.get("title"),
        "published_at": payload.get("published_at"),
        "media_json": _json(_media(payload)),
        "engagement_json": _json(_engagement(payload)),
        "extracted_at": envelope.get("source_extracted_at")
        or payload.get("extracted_at"),
        "run_id": envelope["run_id"],
        "collection_id": envelope["collection_id"],
        "raw_payload_sha256": envelope["payload_sha256"],
    }


def _in_date_window(
    published_at: str | None, start_date: str | None, end_date: str | None
) -> bool:
    if not published_at or not start_date or not end_date:
        return True
    value = datetime.fromisoformat(published_at.replace("Z", "+00:00")).date()
    return datetime.fromisoformat(start_date).date() <= value <= datetime.fromisoformat(
        end_date
    ).date()


def normalize_file(
    source: Path,
    destination: Path,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
) -> tuple[int, int, int]:
    rows: list[dict] = []
    excluded = 0
    with gzip.open(source, "rt", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                envelope = json.loads(line)
                row = normalize_envelope(envelope)
                if _in_date_window(row["published_at"], start_date, end_date):
                    rows.append(row)
                else:
                    excluded += 1
    destination.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(rows, schema=NORMALIZED_SCHEMA), destination)
    return len(rows), excluded, 0
