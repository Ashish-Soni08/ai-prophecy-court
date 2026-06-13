import gzip
import json

import pyarrow.parquet as pq

from pipeline.normalize.records import _in_date_window, normalize_envelope, normalize_file


def test_normalizes_browser_use_envelope() -> None:
    row = normalize_envelope(
        {
            "run_id": "run-2",
            "platform": "x",
            "person_id": "sam-altman",
            "input_url": "https://x.com/sama",
            "collector_id": "collect_x_browser_use",
            "collection_id": "run-2",
            "collection_method": "browser-use",
            "payload_sha256": "b" * 64,
            "source_extracted_at": "2026-06-12T00:00:00Z",
            "payload": {
                "native_id": "42",
                "canonical_url": "https://x.com/sama/status/42",
                "content_type": "quote",
                "text": "browser-use payload",
                "published_at": "2025-02-01T00:00:00Z",
                "media": {"photos": ["https://pbs.twimg.com/media/a.jpg"]},
                "engagement": {"likes": 7, "views": 100},
                "profile_metrics": {"followers": 5},
            },
        }
    )
    assert row["content_id"] == "x:42"
    assert row["native_id"] == "42"
    assert row["canonical_url"] == "https://x.com/sama/status/42"
    assert row["content_type"] == "quote"
    assert row["collection_id"] == "run-2"
    assert row["extracted_at"] == "2026-06-12T00:00:00Z"
    assert '"likes": 7' in row["engagement_json"]
    assert '"author_followers": 5' in row["engagement_json"]
    assert "pbs.twimg.com" in row["media_json"]


def test_date_window() -> None:
    assert _in_date_window("2023-01-01T00:00:00Z", "2022-11-30", "2026-06-08")
    assert not _in_date_window(
        "2022-01-01T00:00:00Z", "2022-11-30", "2026-06-08"
    )


def test_normalize_file_writes_empty_input(tmp_path) -> None:
    source = tmp_path / "records.jsonl.gz"
    destination = tmp_path / "content.parquet"
    with gzip.open(source, "wt", encoding="utf-8") as handle:
        handle.write("")

    count, excluded, vendor_errors = normalize_file(source, destination)

    assert (count, excluded, vendor_errors) == (0, 0, 0)
    assert pq.read_table(destination).num_rows == 0
