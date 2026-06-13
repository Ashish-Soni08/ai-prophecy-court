"""Unit tests for scripts/collect_x_browser_use.py (no network, no browser)."""

from __future__ import annotations

import argparse
import asyncio
import gzip
import hashlib
import importlib.util
import json
import sys
from datetime import date
from pathlib import Path

import jsonschema
import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "collect_x_browser_use.py"
spec = importlib.util.spec_from_file_location("collect_x_browser_use", SCRIPT)
collector = importlib.util.module_from_spec(spec)
# Register before exec so Pydantic can resolve postponed annotations.
sys.modules[spec.name] = collector
spec.loader.exec_module(collector)

SCHEMAS = Path(__file__).resolve().parents[1] / "schemas"
RAW_ENVELOPE_SCHEMA = json.loads(
    (SCHEMAS / "raw-envelope.schema.json").read_text(encoding="utf-8")
)
NORMALIZED_SCHEMA = json.loads(
    (SCHEMAS / "normalized-content.schema.json").read_text(encoding="utf-8")
)

PROFILE = collector.VERIFIED_PROFILES["sam-altman"]


def test_recover_x_timeline_clicks_and_can_reload() -> None:
    class FakePage:
        def __init__(self) -> None:
            self.reloaded = False

        async def evaluate(self, script):
            assert "see new posts" in script
            return "see_new_posts"

        async def reload(self):
            self.reloaded = True

    page = FakePage()
    action = asyncio.run(collector.recover_x_timeline(page, reload_page=True))

    assert action == "see_new_posts+reload"
    assert page.reloaded is True


def test_with_replies_url_keeps_verified_profile_origin() -> None:
    assert (
        collector.VERIFIED_PROFILES["satya-nadella"].profile_url.rstrip("/")
        + "/with_replies"
        == "https://x.com/satyanadella/with_replies"
    )


def make_post(**overrides) -> "collector.ExtractedPost":
    base = {
        "native_id": "100",
        "url": "https://x.com/sama/status/100",
        "content_type": "post",
        "text": "hello",
        "published_at": "2025-06-01T12:00:00+00:00",
        "author_handle": "sama",
        "author_name": "Sam Altman",
    }
    base.update(overrides)
    return collector.ExtractedPost(**base)


def make_batch(posts, **overrides) -> "collector.XExtractionBatch":
    base = {
        "displayed_handle": "sama",
        "displayed_name": "Sam Altman",
        "posts": posts,
        "stop_reason": "max_posts_reached",
    }
    base.update(overrides)
    return collector.XExtractionBatch(**base)


def make_record(**overrides) -> "collector.XPostRecord":
    base = {
        "person_id": "sam-altman",
        "person_name": "Sam Altman",
        "company": "OpenAI",
        "profile_url": "https://x.com/sama",
        "native_id": "100",
        "canonical_url": "https://x.com/sama/status/100",
        "content_type": "post",
        "text": "hello",
        "published_at": "2025-06-01T12:00:00+00:00",
        "author_handle": "sama",
        "author_name": "Sam Altman",
        "author_profile_image": None,
        "is_repost": False,
        "quoted_post": None,
        "reply_to": None,
        "media": collector.MediaInfo(),
        "external_url": None,
        "hashtags": [],
        "tagged_users": [],
        "engagement": collector.ExtractedEngagement(likes=5),
        "profile_metrics": collector.ExtractedProfileMetrics(followers=1),
        "extracted_at": "2026-06-12T00:00:00+00:00",
        "source_fields": {"native_id": "100"},
    }
    base.update(overrides)
    return collector.XPostRecord(**base)


def make_args(**overrides) -> argparse.Namespace:
    base = {
        "persons": None,
        "max_posts": None,
        "start_date": None,
        "end_date": None,
        "output": Path("out.jsonl.gz"),
        "headful": False,
        "max_steps": collector.DEFAULT_MAX_STEPS,
        "max_scrolls": collector.DEFAULT_MAX_SCROLLS,
        "resume": False,
        "conversation_log": None,
    }
    base.update(overrides)
    return argparse.Namespace(**base)


def convert(posts) -> tuple[list, list]:
    return collector.batch_to_records(
        make_batch(posts), PROFILE, "2026-06-12T00:00:00+00:00"
    )


# ---------------------------------------------------------------- validation


def test_record_requires_fixed_constants() -> None:
    record = make_record()
    assert record.schema_version == 1
    assert record.platform == "x"
    assert record.account_verified_manual is True
    assert record.collection_method == "browser-use"


def test_record_rejects_invalid_content_type() -> None:
    with pytest.raises(Exception):
        make_record(content_type="advertisement")


def test_record_rejects_invalid_published_at() -> None:
    with pytest.raises(Exception):
        make_record(published_at="yesterday")
    with pytest.raises(Exception):
        make_record(published_at=None)


def test_record_rejects_missing_identity_fields() -> None:
    with pytest.raises(Exception):
        make_record(native_id=None)
    with pytest.raises(Exception):
        make_record(canonical_url=None)
    with pytest.raises(Exception):
        make_record(canonical_url="https://evil.example.com/sama/status/100")
    with pytest.raises(Exception):
        make_record(author_handle=None)


def test_record_rejects_unknown_fields() -> None:
    with pytest.raises(Exception):
        collector.XPostRecord(**{**make_record().model_dump(), "surprise": 1})


def test_config_rejects_unverified_person() -> None:
    with pytest.raises(SystemExit):
        collector.build_config(make_args(persons=["jensen-huang"]))


def test_config_rejects_unknown_person() -> None:
    with pytest.raises(SystemExit):
        collector.build_config(make_args(persons=["nobody"]))


def test_config_defaults_to_sam_altman_and_three_posts() -> None:
    config = collector.build_config(make_args())
    assert config.persons == ["sam-altman"]
    assert config.max_posts == 3
    assert config.extraction_mode == "deterministic"


def test_config_all_requires_explicit_max_posts() -> None:
    with pytest.raises(SystemExit):
        collector.build_config(make_args(persons=["all"]))
    config = collector.build_config(make_args(persons=["all"], max_posts=5))
    assert sorted(config.persons) == sorted(collector.VERIFIED_PROFILES)


def test_config_rejects_nonpositive_max_posts() -> None:
    with pytest.raises(SystemExit):
        collector.build_config(make_args(max_posts=0))


def test_config_defaults_to_browser_use_llm() -> None:
    config = collector.build_config(make_args())
    assert config.llm_provider == "browser-use"
    assert config.llm_model is None


def test_config_accepts_openai_compatible_llm() -> None:
    config = collector.build_config(
        make_args(
            llm="openai-compatible",
            llm_model="Qwen/Qwen3.5-35B-A3B",
            llm_base_url="https://router.huggingface.co/v1",
        )
    )
    assert config.llm_provider == "openai-compatible"
    assert config.llm_model == "Qwen/Qwen3.5-35B-A3B"


def test_config_accepts_deterministic_extraction() -> None:
    config = collector.build_config(make_args(extraction_mode="deterministic"))
    assert config.extraction_mode == "deterministic"


def test_build_llm_openai_compatible_requires_key(monkeypatch) -> None:
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("HF_TOKEN", raising=False)
    config = collector.build_config(make_args(llm="openai-compatible"))
    with pytest.raises(SystemExit):
        collector.build_llm(config)


def test_execution_mode() -> None:
    cloud = collector.build_config(make_args())
    assert collector.execution_mode(cloud, True) == "cloud"
    assert collector.execution_mode(cloud, False) == "local-headless"
    headful = collector.build_config(make_args(headful=True))
    assert collector.execution_mode(headful, False) == "local-headful"


def test_classify_content_type() -> None:
    post = collector.ExtractedPost(text="t", content_type="Quote")
    assert collector.classify_content_type(post) == "quote"
    assert (
        collector.classify_content_type(
            collector.ExtractedPost(text="t", is_repost=True)
        )
        == "repost"
    )
    assert (
        collector.classify_content_type(
            collector.ExtractedPost(text="t", reply_to="@x")
        )
        == "reply"
    )
    assert collector.classify_content_type(collector.ExtractedPost(text="t")) == "post"
    # Unrecognized label with no corroborating signal stays unknown.
    assert (
        collector.classify_content_type(
            collector.ExtractedPost(text="t", content_type="ad")
        )
        is None
    )


# ------------------------------------------------ candidate verification gate


def test_accepts_fully_verified_candidate() -> None:
    records, errors = convert([make_post()])
    assert errors == []
    record = records[0]
    assert record.native_id == "100"
    assert record.canonical_url == "https://x.com/sama/status/100"
    assert record.published_at == "2025-06-01T12:00:00+00:00"
    assert record.source_fields["url"] == "https://x.com/sama/status/100"


def test_normalizes_twitter_url_to_canonical_x_form() -> None:
    records, errors = convert(
        [make_post(url="https://twitter.com/Sama/status/100?s=20", native_id=None)]
    )
    assert errors == []
    assert records[0].canonical_url == "https://x.com/Sama/status/100"
    assert records[0].native_id == "100"


def test_rejects_missing_canonical_url() -> None:
    records, errors = convert([make_post(url=None)])
    assert records == []
    assert errors[0].error_type == "invalid_record"
    assert "canonical URL" in errors[0].message


def test_rejects_non_status_url() -> None:
    for url in (
        "http://x.com/sama/status/100",  # not https
        "https://x.com/sama",  # not a status URL
        "https://example.com/sama/status/100",  # wrong domain
        "https://x.com/sama/status/abc",  # non-numeric id
    ):
        records, errors = convert([make_post(url=url)])
        assert records == [], url
        assert errors[0].error_type == "invalid_record"


def test_rejects_url_for_another_handle() -> None:
    records, errors = convert([make_post(url="https://x.com/elonmusk/status/100")])
    assert records == []
    assert errors[0].error_type == "invalid_record"
    assert "URL handle" in errors[0].message


def test_rejects_mismatched_native_id() -> None:
    records, errors = convert([make_post(native_id="999")])
    assert records == []
    assert errors[0].error_type == "invalid_record"
    assert "native_id" in errors[0].message


def test_rejects_missing_or_mismatched_author_handle() -> None:
    records, errors = convert([make_post(author_handle=None)])
    assert records == []
    assert errors[0].error_type == "invalid_record"
    assert "author_handle" in errors[0].message

    records, errors = convert([make_post(author_handle="elonmusk")])
    assert records == []
    assert errors[0].error_type == "invalid_record"


def test_rejects_missing_timestamp() -> None:
    records, errors = convert([make_post(published_at=None)])
    assert records == []
    assert errors[0].error_type == "missing_timestamp"

    records, errors = convert([make_post(published_at="2 hours ago")])
    assert records == []
    assert errors[0].error_type == "missing_timestamp"


def test_decodes_exact_timestamp_from_x_snowflake() -> None:
    assert (
        collector.timestamp_from_x_snowflake("1955094792804720660")
        == "2025-08-12T02:31:37.166+00:00"
    )


def test_extracts_text_from_logged_out_timeline_card() -> None:
    card = (
        "Sam Altman\n@sama\nFeb 10, 2025\n"
        "no thank you but we will buy twitter for $9.74 billion if you want"
    )
    assert collector.text_from_timeline_card(card, "sama") == (
        "no thank you but we will buy twitter for $9.74 billion if you want"
    )


def test_timeline_card_text_requires_expected_handle() -> None:
    assert collector.text_from_timeline_card("Sam\n@other\nToday\nhello", "sama") is None


def test_timeline_card_trims_quoted_post() -> None:
    card = (
        "Sam Altman\n@sama\nAug 12, 2025\nmain comment\n"
        "Elon Musk\n@elonmusk\nAug 12, 2025\nquoted text\nReaders added context"
    )
    assert collector.text_from_timeline_card(card, "sama") == "main comment"
    assert collector.timeline_card_has_quote(card, "sama") is True


def test_rejects_empty_post_without_text_or_media() -> None:
    records, errors = convert([make_post(text=None)])
    assert records == []
    assert errors[0].error_type == "invalid_record"
    assert "neither text nor" in errors[0].message

    # Media-only posts are acceptable.
    records, errors = convert(
        [make_post(text=None, photos=["https://pbs.twimg.com/media/a.jpg"])]
    )
    assert errors == []
    assert len(records) == 1


def test_valid_records_survive_among_rejected_ones() -> None:
    records, errors = convert(
        [
            make_post(),
            make_post(native_id="101", url=None),
            make_post(
                native_id="102",
                url="https://x.com/sama/status/102",
                published_at=None,
            ),
        ]
    )
    assert [r.native_id for r in records] == ["100"]
    assert sorted(e.error_type for e in errors) == [
        "invalid_record",
        "missing_timestamp",
    ]


# ------------------------------------------------------------- deduplication


def test_dedupe_by_native_id() -> None:
    seen: set[str] = set()
    records = [
        make_record(native_id="1", canonical_url="https://x.com/sama/status/1"),
        make_record(native_id="1", canonical_url="https://x.com/sama/status/1"),
        make_record(native_id="2", canonical_url="https://x.com/sama/status/2"),
    ]
    unique, duplicates = collector.dedupe_records(records, seen)
    assert [r.native_id for r in unique] == ["1", "2"]
    assert duplicates == 1


# ------------------------------------------------------------- date filtering


def test_filter_by_window_bounds_inclusive() -> None:
    records = [
        make_record(native_id="1", published_at="2022-11-30T00:00:00+00:00"),
        make_record(native_id="2", published_at="2022-11-29T23:59:59+00:00"),
        make_record(native_id="3", published_at="2026-06-08T12:00:00Z"),
    ]
    kept, excluded = collector.filter_by_window(
        records, date(2022, 11, 30), date(2026, 6, 8)
    )
    assert [r.native_id for r in kept] == ["1", "3"]
    assert excluded == 1


def test_sort_newest_first() -> None:
    records = [
        make_record(native_id="1", published_at="2023-01-01T00:00:00+00:00"),
        make_record(native_id="3", published_at="2025-01-01T00:00:00+00:00"),
        make_record(native_id="2", published_at="2024-01-01T00:00:00+00:00"),
    ]
    ordered = collector.sort_newest_first(records)
    assert [r.native_id for r in ordered] == ["3", "2", "1"]


def test_effective_window_uses_profile_start() -> None:
    config = collector.build_config(make_args(persons=["elon-musk"]))
    profile = collector.VERIFIED_PROFILES["elon-musk"]
    start, end = collector.effective_window(profile, config)
    assert start == date(2024, 7, 1)
    assert end == config.end_date


def test_effective_window_rejects_inverted_dates() -> None:
    config = collector.build_config(
        make_args(start_date="2026-01-01", end_date="2025-01-01")
    )
    with pytest.raises(ValueError):
        collector.effective_window(collector.VERIFIED_PROFILES["sam-altman"], config)


# ----------------------------------------------------- raw envelopes (.gz)


def envelope_for(record, run_id="20260612T000000Z-abcd1234"):
    return collector.build_envelope(
        record,
        run_id=run_id,
        requested_at="2026-06-12T00:00:00+00:00",
        completed_at="2026-06-12T00:01:00+00:00",
    )


def test_envelope_validates_against_raw_envelope_schema() -> None:
    envelope = envelope_for(make_record())
    jsonschema.validate(envelope.model_dump(mode="json"), RAW_ENVELOPE_SCHEMA)


def test_envelope_provenance_and_payload_checksum() -> None:
    record = make_record()
    envelope = envelope_for(record)
    assert envelope.collection_method == "browser-use"
    assert envelope.collector_id == "collect_x_browser_use"
    assert envelope.collection_id == envelope.run_id
    payload = record.model_dump(mode="json")
    assert envelope.payload == payload
    assert (
        envelope.payload_sha256
        == hashlib.sha256(collector.canonical_json(payload)).hexdigest()
    )


def test_write_envelopes_gz_atomic_roundtrip(tmp_path: Path) -> None:
    output = tmp_path / "nested" / "out.jsonl.gz"
    envelopes = [
        envelope_for(
            make_record(native_id="1", canonical_url="https://x.com/sama/status/1")
        ),
        envelope_for(
            make_record(native_id="2", canonical_url="https://x.com/sama/status/2")
        ),
    ]
    digest = collector.write_envelopes_gz_atomic(output, envelopes)

    assert digest == hashlib.sha256(output.read_bytes()).hexdigest()
    with gzip.open(output, "rt", encoding="utf-8") as handle:
        lines = [json.loads(line) for line in handle if line.strip()]
    assert len(lines) == 2
    for line in lines:
        jsonschema.validate(line, RAW_ENVELOPE_SCHEMA)
    assert lines[0]["payload"]["native_id"] == "1"
    assert lines[0]["payload"]["collection_method"] == "browser-use"
    assert list(output.parent.glob("*.tmp-*")) == []


def test_browser_use_envelopes_normalize(tmp_path: Path) -> None:
    from pipeline.normalize.records import normalize_file

    source = tmp_path / "sam.jsonl.gz"
    record = make_record(
        media=collector.MediaInfo(photos=["https://pbs.twimg.com/media/a.jpg"]),
    )
    collector.write_envelopes_gz_atomic(source, [envelope_for(record)])

    destination = tmp_path / "content.parquet"
    count, excluded, vendor_errors = normalize_file(source, destination)
    assert (count, excluded, vendor_errors) == (1, 0, 0)

    import pyarrow.parquet as pq

    rows = pq.read_table(destination).to_pylist()
    row = rows[0]
    jsonschema.validate(row, NORMALIZED_SCHEMA)
    assert row["content_id"] == "x:100"
    assert row["native_id"] == "100"
    assert row["canonical_url"] == "https://x.com/sama/status/100"
    assert row["text"] == "hello"
    assert row["published_at"] == "2025-06-01T12:00:00+00:00"
    assert row["collection_id"] == "20260612T000000Z-abcd1234"
    assert json.loads(row["engagement_json"])["likes"] == 5
    assert json.loads(row["engagement_json"])["author_followers"] == 1
    assert "pbs.twimg.com" in row["media_json"]


# ------------------------------------------------------------------- resume


def test_resume_keys_skip_existing_urls(tmp_path: Path) -> None:
    output = tmp_path / "out.jsonl.gz"
    existing = [make_record(native_id="100")]
    collector.write_envelopes_gz_atomic(
        output, [envelope_for(record) for record in existing]
    )

    envelopes, loaded = collector.load_existing_envelopes(output)
    assert len(envelopes) == len(loaded) == 1
    seen = collector.resume_keys(loaded)

    new = [
        make_record(native_id="100"),  # same native id
        make_record(native_id="2", canonical_url="https://x.com/sama/status/2"),
    ]
    unique, duplicates = collector.dedupe_records(new, seen)
    assert [r.native_id for r in unique] == ["2"]
    assert duplicates == 1


def test_load_existing_envelopes_rejects_corrupt_lines(tmp_path: Path) -> None:
    output = tmp_path / "out.jsonl.gz"
    with gzip.open(output, "wt", encoding="utf-8") as handle:
        handle.write('{"not": "an envelope"}\n')
    with pytest.raises(ValueError):
        collector.load_existing_envelopes(output)


def test_load_existing_envelopes_missing_file(tmp_path: Path) -> None:
    assert collector.load_existing_envelopes(tmp_path / "missing.jsonl.gz") == ([], [])


# ------------------------------------------------------------------ manifest


def test_write_manifest_sibling_path(tmp_path: Path) -> None:
    output = tmp_path / "sam.jsonl.gz"
    manifest = collector.RunManifest(
        run_id="run-1",
        requested_profiles=[{"person_id": "sam-altman", "max_posts": 3}],
        date_windows={
            "sam-altman": {"start_date": "2022-11-30", "end_date": "2026-06-12"}
        },
        started_at="2026-06-12T00:00:00+00:00",
        completed_at="2026-06-12T00:01:00+00:00",
        browser_use_model="bu-latest",
        execution_mode="cloud",
        cloud_profile_configured=False,
        visited_urls={"sam-altman": ["https://x.com/sama"]},
        record_count_by_person={"sam-altman": 3},
        duplicate_count=0,
        stop_reason_by_person={"sam-altman": "max_posts_reached"},
        errors=[
            collector.StructuredError(
                person_id="sam-altman",
                error_type="captcha",
                message="CAPTCHA shown",
                url="https://x.com/sama",
                occurred_at="2026-06-12T00:00:30+00:00",
            )
        ],
        output_path=str(output),
        output_sha256="a" * 64,
        git_commit=None,
    )
    path = collector.write_manifest(manifest, output)
    assert path == tmp_path / "sam.jsonl.gz.manifest.json"
    parsed = json.loads(path.read_text(encoding="utf-8"))
    assert parsed["platform"] == "x"
    assert parsed["errors"][0]["error_type"] == "captcha"
    assert parsed["record_count_by_person"]["sam-altman"] == 3


# ----------------------------------------------------------- browser cleanup


class StubBrowser:
    def __init__(self, kill_raises: bool = False, page=None) -> None:
        self.kill_calls = 0
        self.kill_raises = kill_raises
        self.page = page

    async def kill(self) -> None:
        self.kill_calls += 1
        if self.kill_raises:
            raise RuntimeError("cleanup boom")

    async def must_get_current_page(self):
        if self.page is None:
            raise RuntimeError("no page")
        return self.page


class StubHistory:
    def __init__(self, structured_output=None, final=None) -> None:
        self.structured_output = structured_output
        self._final = final

    def urls(self) -> list[str]:
        return ["https://x.com/sama"]

    def final_result(self):
        return self._final


class StubAgent:
    def __init__(self, history=None, run_raises: Exception | None = None) -> None:
        self._history = history
        self._run_raises = run_raises

    async def run(self, max_steps: int):
        if self._run_raises is not None:
            raise self._run_raises
        return self._history


def run_collect_person(monkeypatch, browser: StubBrowser, agent: StubAgent):
    monkeypatch.setattr(collector, "make_browser", lambda *a, **k: browser)
    monkeypatch.setattr(collector, "make_agent", lambda *a, **k: agent)
    config = collector.build_config(make_args(extraction_mode="agent"))
    return asyncio.run(
        collector.collect_person(
            PROFILE,
            config,
            llm=None,
            use_cloud_browser=False,
            cloud_profile_id=None,
        )
    )


def test_browser_killed_after_success(monkeypatch) -> None:
    browser = StubBrowser()
    history = StubHistory(structured_output=make_batch([make_post()]))
    batch, visited, errors = run_collect_person(
        monkeypatch, browser, StubAgent(history)
    )
    assert browser.kill_calls == 1
    assert batch is not None
    assert errors == []
    assert visited == ["https://x.com/sama"]


def test_browser_killed_after_agent_failure(monkeypatch) -> None:
    browser = StubBrowser()
    batch, _, errors = run_collect_person(
        monkeypatch, browser, StubAgent(run_raises=RuntimeError("agent boom"))
    )
    assert browser.kill_calls == 1
    assert batch is None
    assert errors[0].error_type == "agent_failure"


def test_browser_killed_after_missing_structured_output(monkeypatch) -> None:
    browser = StubBrowser()
    batch, _, errors = run_collect_person(
        monkeypatch, browser, StubAgent(StubHistory(structured_output=None, final=None))
    )
    assert browser.kill_calls == 1
    assert batch is None
    assert errors[0].error_type == "no_structured_output"


def test_browser_cleanup_failure_does_not_replace_result(monkeypatch) -> None:
    browser = StubBrowser(kill_raises=True)
    history = StubHistory(structured_output=make_batch([make_post()]))
    batch, _, errors = run_collect_person(monkeypatch, browser, StubAgent(history))
    assert browser.kill_calls == 1
    assert batch is not None
    assert errors == []


class StubPage:
    def __init__(self) -> None:
        self.url = ""

    async def goto(self, url: str) -> None:
        self.url = url

    async def evaluate(self, _script: str) -> str:
        if self.url == PROFILE.profile_url:
            return json.dumps(["https://x.com/sama/status/101"])
        return json.dumps(
            {
                "url": "https://x.com/sama/status/101",
                "text": "fallback post",
                "published_at": "2026-06-01T12:00:00.000Z",
                "author_profile_image": None,
                "photos": [],
                "videos": [],
                "reply_to": None,
            }
        )


def test_zero_post_agent_result_uses_deterministic_fallback(
    monkeypatch,
) -> None:
    browser = StubBrowser(page=StubPage())
    history = StubHistory(structured_output=make_batch([], stop_reason="no_new_posts"))
    fallback = make_batch(
        [
            make_post(
                native_id="101",
                url="https://x.com/sama/status/101",
                text="fallback post",
                published_at="2026-06-01T12:00:00.000Z",
            )
        ]
    )

    async def fake_fallback(*args, **kwargs):
        return fallback

    monkeypatch.setattr(collector, "deterministic_x_fallback", fake_fallback)
    batch, _, errors = run_collect_person(monkeypatch, browser, StubAgent(history))
    assert errors == []
    assert batch is not None
    assert [post.native_id for post in batch.posts] == ["101"]
    assert batch.posts[0].published_at == "2026-06-01T12:00:00.000Z"
    assert browser.kill_calls == 1


def test_parse_metric_count() -> None:
    assert collector.parse_metric_count("1,234") == 1234
    assert collector.parse_metric_count("2.7K Likes") == 2700
    assert collector.parse_metric_count("1.5M Views") == 1_500_000
    assert collector.parse_metric_count(None) is None


def test_repair_mojibake() -> None:
    assert collector.repair_mojibake(
        "cell state \u00e2\u0080\u0094 how cells respond"
    ) == "cell state \u2014 how cells respond"


def test_x_card_to_post_extracts_quote_and_engagement() -> None:
    post = collector.x_card_to_post(
        {
            "url": "https://x.com/sama/status/123",
            "text": "hello @openai #ai",
            "published_at": "2026-06-01T12:00:00.000Z",
            "has_quote": True,
            "quoted_post": {
                "author_handle": "other",
                "author_name": None,
                "url": "https://x.com/other/status/122",
                "text": "quoted",
            },
            "tagged_users": ["@openai"],
            "hashtags": ["#ai"],
            "metrics": {"likes": "2.7K Likes", "views": "1.5M Views"},
        },
        PROFILE,
    )
    assert post is not None
    assert post.content_type == "quote"
    assert post.quoted_post is not None
    assert post.quoted_post.author_handle == "other"
    assert post.engagement is not None
    assert post.engagement.likes == 2700
    assert post.engagement.views == 1_500_000


# ------------------------------------------------- run-level identity gating


def run_collection_with_batch(monkeypatch, tmp_path: Path, batch):
    monkeypatch.setenv("BROWSER_USE_API_KEY", "test-key")
    monkeypatch.setattr(collector, "build_llm", lambda config: object())

    async def fake_collect_person(profile, config, **kwargs):
        return batch, [profile.profile_url], []

    monkeypatch.setattr(collector, "collect_person", fake_collect_person)
    output = tmp_path / "sam.jsonl.gz"
    config = collector.build_config(make_args(output=output))
    manifest = asyncio.run(collector.run_collection(config))
    with gzip.open(output, "rt", encoding="utf-8") as handle:
        lines = [json.loads(line) for line in handle if line.strip()]
    return manifest, lines


def test_run_rejects_missing_displayed_handle(monkeypatch, tmp_path: Path) -> None:
    batch = make_batch([make_post()], displayed_handle=None)
    manifest, lines = run_collection_with_batch(monkeypatch, tmp_path, batch)
    assert lines == []
    assert manifest.record_count_by_person == {"sam-altman": 0}
    assert manifest.stop_reason_by_person == {"sam-altman": "identity_unverified"}
    assert any(e.error_type == "identity_unverified" for e in manifest.errors)


def test_run_rejects_mismatched_displayed_handle(monkeypatch, tmp_path: Path) -> None:
    batch = make_batch([make_post()], displayed_handle="someoneelse")
    manifest, lines = run_collection_with_batch(monkeypatch, tmp_path, batch)
    assert lines == []
    assert manifest.stop_reason_by_person == {"sam-altman": "handle_mismatch"}
    assert any(e.error_type == "handle_mismatch" for e in manifest.errors)


def test_run_writes_envelopes_and_manifest_checksum(
    monkeypatch, tmp_path: Path
) -> None:
    batch = make_batch([make_post()])
    manifest, lines = run_collection_with_batch(monkeypatch, tmp_path, batch)
    assert len(lines) == 1
    jsonschema.validate(lines[0], RAW_ENVELOPE_SCHEMA)
    assert lines[0]["payload"]["canonical_url"] == "https://x.com/sama/status/100"
    output = tmp_path / "sam.jsonl.gz"
    assert manifest.output_sha256 == hashlib.sha256(output.read_bytes()).hexdigest()
    assert manifest.record_count_by_person == {"sam-altman": 1}
    assert manifest.stop_reason_by_person == {"sam-altman": "max_posts_reached"}


def test_run_marks_all_rejected_candidates_as_validation_failure(
    monkeypatch, tmp_path: Path
) -> None:
    batch = make_batch([make_post(text=None)])
    manifest, lines = run_collection_with_batch(monkeypatch, tmp_path, batch)
    assert lines == []
    assert manifest.stop_reason_by_person == {"sam-altman": "validation_failure"}


def test_resume_with_only_duplicates_is_not_validation_failure(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(collector, "build_llm", lambda config: object())
    output = tmp_path / "sam.jsonl.gz"
    existing = make_record()
    collector.write_envelopes_gz_atomic(output, [envelope_for(existing)])

    async def fake_collect_person(profile, config, **kwargs):
        return make_batch([make_post()]), [profile.profile_url], []

    monkeypatch.setattr(collector, "collect_person", fake_collect_person)
    config = collector.build_config(
        make_args(output=output, resume=True, extraction_mode="deterministic")
    )
    manifest = asyncio.run(collector.run_collection(config))
    assert manifest.stop_reason_by_person == {"sam-altman": "no_new_records"}
    assert manifest.duplicate_count == 1


# ------------------------------------------------------------ registry guard


def test_registry_cross_check_accepts_verified_people() -> None:
    collector.cross_check_registry(sorted(collector.VERIFIED_PROFILES))


def test_registry_cross_check_rejects_jensen_huang() -> None:
    # jensen-huang is in the registry but has no verified X account, and is
    # not an embedded verified profile either.
    assert "jensen-huang" not in collector.VERIFIED_PROFILES
