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

MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "collect_linkedin_browser_use.py"
)
spec = importlib.util.spec_from_file_location(
    "collect_linkedin_browser_use", MODULE_PATH
)
collector = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = collector
spec.loader.exec_module(collector)

SCHEMAS = Path(__file__).resolve().parents[1] / "schemas"
RAW_ENVELOPE_SCHEMA = json.loads(
    (SCHEMAS / "raw-envelope.schema.json").read_text(encoding="utf-8")
)
NORMALIZED_SCHEMA = json.loads(
    (SCHEMAS / "normalized-content.schema.json").read_text(encoding="utf-8")
)

PERSON = collector.RegistryPerson(
    person_id="satya-nadella",
    name="Satya Nadella",
    company="Microsoft",
    profile_url="https://www.linkedin.com/in/satyanadella/",
)

WINDOW = {"start": date(2022, 11, 30), "end": date(2026, 6, 12)}


def make_post(**overrides) -> "collector.ExtractedPost":
    base = {
        "activity_id": "7000000000000000001",
        "canonical_url": (
            "https://www.linkedin.com/posts/satyanadella_ai-activity-"
            "7000000000000000001-abcd"
        ),
        "content_type": "post",
        "text": "AI will change everything.",
        "published_at": "2025-05-01T12:00:00Z",
        "author_name": "Satya Nadella",
        "author_profile_url": "https://www.linkedin.com/in/satyanadella/",
    }
    base.update(overrides)
    return collector.ExtractedPost(**base)


def make_extraction(posts) -> "collector.LinkedInExtraction":
    return collector.LinkedInExtraction(
        profile_identity_confirmed=True,
        profile_name_seen="Satya Nadella",
        posts=posts,
        stop_reason="max_posts_reached",
    )


def select(posts, *, max_posts=3, existing_keys=frozenset()):
    return collector.select_records(
        make_extraction(posts),
        PERSON,
        start=WINDOW["start"],
        end=WINDOW["end"],
        max_posts=max_posts,
        existing_keys=set(existing_keys),
        extracted_at="2026-06-12T00:00:00+00:00",
    )


def make_record(**post_overrides) -> "collector.LinkedInRecord":
    return collector.build_record(
        make_post(**post_overrides),
        PERSON,
        collector.ExtractedProfileMetrics(),
        "2026-06-12T00:00:00+00:00",
    )


def envelope_for(record, run_id="20260612T000000Z-abcd1234"):
    return collector.build_envelope(
        record,
        run_id=run_id,
        requested_at="2026-06-12T00:00:00+00:00",
        completed_at="2026-06-12T00:01:00+00:00",
    )


def read_gz_lines(path: Path) -> list[dict]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


# ---------------------------------------------------------------------------
# Pydantic validation
# ---------------------------------------------------------------------------


def test_record_requires_linkedin_canonical_url() -> None:
    record = make_record()
    assert record.platform == "linkedin"
    assert record.account_verified_manual is True
    assert record.collection_method == "browser-use"
    assert record.native_id == "7000000000000000001"
    assert record.source_fields["text"] == "AI will change everything."

    with pytest.raises(ValueError):
        collector.LinkedInRecord(
            person_id="satya-nadella",
            person_name="Satya Nadella",
            company="Microsoft",
            profile_url=PERSON.profile_url,
            canonical_url="https://evil.example.com/post/1",
            extracted_at="2026-06-12T00:00:00+00:00",
        )


def test_extraction_schema_defaults() -> None:
    extraction = collector.LinkedInExtraction()
    assert extraction.posts == []
    assert extraction.access_blocked is False
    assert extraction.stop_reason == "unknown"
    # round-trip through JSON, as Browser Use structured output does
    parsed = collector.LinkedInExtraction.model_validate_json(
        extraction.model_dump_json()
    )
    assert parsed == extraction


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------


def test_extract_activity_id_variants() -> None:
    assert (
        collector.extract_activity_id("urn:li:activity:7123456789012345678")
        == "7123456789012345678"
    )
    assert (
        collector.extract_activity_id(
            "https://www.linkedin.com/posts/x_y-activity-7123456789012345678-ab/"
        )
        == "7123456789012345678"
    )
    assert (
        collector.extract_activity_id("https://www.linkedin.com/in/satyanadella/")
        is None
    )
    assert collector.extract_activity_id(None) is None


def test_dedup_prefers_activity_id_over_url() -> None:
    first = make_post()
    same_id_other_url = make_post(
        canonical_url="https://www.linkedin.com/feed/update/urn:li:activity:7000000000000000001/"
    )
    records, duplicates = select([first, same_id_other_url])
    assert len(records) == 1
    assert duplicates == 1


def test_dedup_falls_back_to_canonical_url() -> None:
    no_id_a = make_post(
        activity_id=None,
        canonical_url="https://www.linkedin.com/pulse/some-article-satya/",
    )
    no_id_b = make_post(
        activity_id=None,
        canonical_url="https://www.linkedin.com/pulse/some-article-satya?utm=1",
    )
    records, duplicates = select([no_id_a, no_id_b])
    assert len(records) == 1
    assert duplicates == 1


# ---------------------------------------------------------------------------
# Authored-post filtering
# ---------------------------------------------------------------------------


def test_drops_posts_from_other_authors() -> None:
    other = make_post(
        activity_id="7000000000000000002",
        canonical_url=(
            "https://www.linkedin.com/posts/someoneelse_activity-7000000000000000002-xy"
        ),
        author_name="Someone Else",
        author_profile_url="https://www.linkedin.com/in/someone-else/",
    )
    records, _ = select([make_post(), other])
    assert [r.native_id for r in records] == ["7000000000000000001"]


def test_author_name_fallback_when_profile_url_missing() -> None:
    assert collector.is_authored_by(
        make_post(author_profile_url=None, author_name="  satya nadella "), PERSON
    )
    assert not collector.is_authored_by(
        make_post(author_profile_url=None, author_name="Jensen Huang"), PERSON
    )
    assert not collector.is_authored_by(
        make_post(author_profile_url=None, author_name=None), PERSON
    )


def test_reposts_are_excluded_even_when_profile_owner_reshared_them() -> None:
    repost = make_post(content_type="repost", is_repost=True)
    records, duplicates = select([repost])
    assert records == []
    assert duplicates == 0


def test_compact_linkedin_activity_decodes_numeric_page_result() -> None:
    class FakePage:
        async def evaluate(self, script):
            assert "codexCompacted" in script
            return "4"

    assert asyncio.run(collector.compact_linkedin_activity_v2(FakePage())) == 4


def test_build_deterministic_posts_keeps_only_profile_owner_content() -> None:
    found = {
        "7000000000000000001": {
            "activity_id": "7000000000000000001",
            "canonical_url": (
                "https://www.linkedin.com/feed/update/"
                "urn:li:activity:7000000000000000001/"
            ),
            "text": "Original post",
            "author_name": "Satya Nadella",
            "author_profile_url": PERSON.profile_url,
            "images": [],
        },
        "7000000000000000002": {
            "activity_id": "7000000000000000002",
            "canonical_url": (
                "https://www.linkedin.com/feed/update/"
                "urn:li:activity:7000000000000000002/"
            ),
            "text": "Recommended post",
            "author_name": "Someone Else",
            "author_profile_url": "https://www.linkedin.com/in/someone-else/",
            "images": [],
        },
    }

    posts = collector.build_deterministic_posts_v2(found, PERSON, max_posts=10)

    assert [post.activity_id for post in posts] == ["7000000000000000001"]
    assert posts[0].is_repost is False


# ---------------------------------------------------------------------------
# Date filtering
# ---------------------------------------------------------------------------


def test_date_window_filtering() -> None:
    too_old = make_post(
        activity_id="6000000000000000001",
        canonical_url=(
            "https://www.linkedin.com/posts/satyanadella_activity-6000000000000000001-aa"
        ),
        published_at="2021-01-01T00:00:00Z",
    )
    undated = make_post(
        activity_id="7000000000000000003",
        canonical_url=(
            "https://www.linkedin.com/posts/satyanadella_activity-7000000000000000003-bb"
        ),
        published_at=None,
    )
    records, _ = select([make_post(), too_old, undated])
    ids = {r.native_id for r in records}
    assert "6000000000000000001" not in ids
    assert {"7000000000000000001", "7000000000000000003"} <= ids


def test_sort_newest_first_with_undated_last() -> None:
    older = make_post(
        activity_id="7000000000000000004",
        canonical_url=(
            "https://www.linkedin.com/posts/satyanadella_activity-7000000000000000004-cc"
        ),
        published_at="2023-01-01T00:00:00Z",
    )
    undated = make_post(
        activity_id="7000000000000000005",
        canonical_url=(
            "https://www.linkedin.com/posts/satyanadella_activity-7000000000000000005-dd"
        ),
        published_at=None,
    )
    records, _ = select([older, undated, make_post()])
    assert [r.native_id for r in records] == [
        "7000000000000000001",  # 2025-05-01
        "7000000000000000004",  # 2023-01-01
        "7000000000000000005",  # undated, last
    ]


def test_max_posts_cap() -> None:
    posts = [
        make_post(
            activity_id=f"70000000000000001{i:02d}",
            canonical_url=(
                "https://www.linkedin.com/posts/satyanadella_activity-"
                f"70000000000000001{i:02d}-zz"
            ),
            published_at=f"2025-01-{i + 1:02d}T00:00:00Z",
        )
        for i in range(5)
    ]
    records, _ = select(posts, max_posts=3)
    assert len(records) == 3
    assert records[0].published_at == "2025-01-05T00:00:00Z"


# ---------------------------------------------------------------------------
# Raw envelopes and resume behavior
# ---------------------------------------------------------------------------


def test_envelope_validates_against_raw_envelope_schema() -> None:
    envelope = envelope_for(make_record())
    payload = envelope.model_dump(mode="json")
    jsonschema.validate(payload, RAW_ENVELOPE_SCHEMA)
    assert payload["collection_method"] == "browser-use"
    assert payload["collector_id"] == "collect_linkedin_browser_use"
    assert (
        payload["payload_sha256"]
        == hashlib.sha256(collector.canonical_json(payload["payload"])).hexdigest()
    )


def test_browser_use_envelopes_normalize(tmp_path) -> None:
    from pipeline.normalize.records import normalize_file

    source = tmp_path / "satya.jsonl.gz"
    collector.write_envelopes_gz_atomic(source, [envelope_for(make_record())])

    destination = tmp_path / "content.parquet"
    count, excluded, vendor_errors = normalize_file(source, destination)
    assert (count, excluded, vendor_errors) == (1, 0, 0)

    import pyarrow.parquet as pq

    row = pq.read_table(destination).to_pylist()[0]
    jsonschema.validate(row, NORMALIZED_SCHEMA)
    assert row["content_id"] == "linkedin:7000000000000000001"
    assert row["text"] == "AI will change everything."
    assert row["published_at"] == "2025-05-01T12:00:00Z"
    assert row["collection_id"] == "20260612T000000Z-abcd1234"


def test_resume_skips_existing_keys(tmp_path) -> None:
    output = tmp_path / "satya.jsonl.gz"
    collector.write_envelopes_gz_atomic(output, [envelope_for(make_record())])

    envelopes, existing = collector.load_existing_envelopes(output)
    assert len(envelopes) == len(existing) == 1
    keys = collector.existing_dedup_keys(existing)
    assert keys == {"activity:7000000000000000001"}

    new_post = make_post(
        activity_id="7000000000000000009",
        canonical_url=(
            "https://www.linkedin.com/posts/satyanadella_activity-7000000000000000009-ee"
        ),
    )
    records, duplicates = select([make_post(), new_post], existing_keys=keys)
    assert [r.native_id for r in records] == ["7000000000000000009"]
    assert duplicates == 1


# ---------------------------------------------------------------------------
# Gzip JSONL and manifest writing
# ---------------------------------------------------------------------------


def test_write_envelopes_gz_atomic_and_manifest(tmp_path) -> None:
    output = tmp_path / "out" / "satya.jsonl.gz"
    record = collector.build_record(
        make_post(),
        PERSON,
        collector.ExtractedProfileMetrics(followers=11000000),
        "2026-06-12T00:00:00+00:00",
    )
    sha = collector.write_envelopes_gz_atomic(output, [envelope_for(record)])
    assert sha == hashlib.sha256(output.read_bytes()).hexdigest()

    lines = read_gz_lines(output)
    assert len(lines) == 1
    jsonschema.validate(lines[0], RAW_ENVELOPE_SCHEMA)
    parsed = lines[0]["payload"]
    assert parsed["platform"] == "linkedin"
    assert parsed["person_id"] == "satya-nadella"
    assert parsed["profile_metrics"]["followers"] == 11000000
    assert not list(output.parent.glob("*.tmp-*"))

    manifest = collector.RunManifest(
        run_id="run-1",
        requested_people=["satya-nadella"],
        max_posts=3,
        max_steps=75,
        effective_start_date="2022-11-30",
        effective_end_date="2026-06-12",
        started_at="2026-06-12T00:00:00+00:00",
        completed_at="2026-06-12T00:05:00+00:00",
        execution_mode="cloud",
        cloud_profile_configured=True,
        record_count_by_person={"satya-nadella": 1},
        stop_reason_by_person={"satya-nadella": "max_posts_reached"},
        output_path=str(output),
        output_sha256=sha,
        git_commit="abc123",
    )
    manifest_path = collector.write_manifest(output, manifest)
    assert manifest_path == output.with_name("satya.jsonl.gz.manifest.json")
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert data["platform"] == "linkedin"
    assert data["browser_use_model"] == "bu-latest"
    assert data["output_sha256"] == sha


# ---------------------------------------------------------------------------
# CLI guard rails and registry resolution
# ---------------------------------------------------------------------------


def test_parse_args_defaults() -> None:
    args = collector.parse_args(["--output", "out.jsonl.gz"])
    assert args.person == ["satya-nadella"]
    assert args.max_posts == 3
    assert args.llm == "browser-use"
    assert args.llm_model is None
    assert args.extraction_mode == "deterministic"
    assert args.max_scrolls == collector.DEFAULT_MAX_SCROLLS


def test_parse_args_accepts_openai_compatible_llm() -> None:
    args = collector.parse_args(
        [
            "--output",
            "out.jsonl.gz",
            "--llm",
            "openai-compatible",
            "--llm-model",
            "MiniMaxAI/MiniMax-M3",
        ]
    )
    assert args.llm == "openai-compatible"
    assert args.llm_model == "MiniMaxAI/MiniMax-M3"


def test_build_llm_openai_compatible_requires_key(monkeypatch) -> None:
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("HF_TOKEN", raising=False)
    with pytest.raises(SystemExit):
        collector.build_llm("openai-compatible")


def test_parse_args_all_requires_explicit_max_posts() -> None:
    with pytest.raises(SystemExit):
        collector.parse_args(["--person", "all", "--output", "out.jsonl.gz"])
    args = collector.parse_args(
        ["--person", "all", "--max-posts", "3", "--output", "out.jsonl.gz"]
    )
    assert args.person == ["all"]


def test_parse_args_rejects_nonpositive_max_posts() -> None:
    with pytest.raises(SystemExit):
        collector.parse_args(["--max-posts", "0", "--output", "out.jsonl.gz"])


def test_main_end_to_end_with_stubbed_agent(tmp_path, monkeypatch) -> None:
    """Full orchestration without a real browser: envelopes, manifest, resume."""
    monkeypatch.setenv("BROWSER_USE_API_KEY", "test-key")
    monkeypatch.delenv("BROWSER_USE_CLOUD_PROFILE_ID", raising=False)
    monkeypatch.setattr(collector, "build_llm", lambda *a, **k: object())
    output = tmp_path / "satya.jsonl.gz"

    extraction = collector.LinkedInExtraction(
        profile_identity_confirmed=True,
        profile_name_seen="Satya Nadella",
        posts=[make_post()],
        access_blocked=False,
        stop_reason="max_posts_reached",
    )

    async def fake_collect_person(person, **kwargs):
        return (
            extraction,
            [person.profile_url, person.profile_url + "recent-activity/all/"],
            None,
        )

    monkeypatch.setattr(collector, "collect_person", fake_collect_person)
    exit_code = collector.main(
        [
            "--person",
            "satya-nadella",
            "--max-posts",
            "3",
            "--output",
            str(output),
            "--extraction-mode",
            "agent",
        ]
    )
    assert exit_code == 0

    lines = read_gz_lines(output)
    assert len(lines) == 1
    jsonschema.validate(lines[0], RAW_ENVELOPE_SCHEMA)
    assert lines[0]["person_id"] == "satya-nadella"
    assert lines[0]["collection_method"] == "browser-use"
    assert lines[0]["payload"]["person_id"] == "satya-nadella"
    assert lines[0]["payload"]["account_verified_manual"] is True

    manifest = json.loads(
        output.with_name("satya.jsonl.gz.manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["record_count_by_person"] == {"satya-nadella": 1}
    assert manifest["stop_reason_by_person"] == {"satya-nadella": "max_posts_reached"}
    assert manifest["execution_mode"] == "cloud"
    assert manifest["errors"] == []
    assert manifest["duplicate_count"] == 0
    assert len(manifest["visited_urls"]) == 2
    assert (
        manifest["output_sha256"]
        == collector.hashlib.sha256(output.read_bytes()).hexdigest()
    )

    # Resume: the same post must be skipped as a duplicate.
    exit_code = collector.main(
        [
            "--person",
            "satya-nadella",
            "--max-posts",
            "3",
            "--output",
            str(output),
            "--resume",
            "--extraction-mode",
            "agent",
        ]
    )
    assert exit_code == 0
    assert len(read_gz_lines(output)) == 1
    manifest = json.loads(
        output.with_name("satya.jsonl.gz.manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["duplicate_count"] == 1
    assert manifest["record_count_by_person"] == {"satya-nadella": 0}


def test_main_records_structured_error_when_blocked(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BROWSER_USE_API_KEY", "test-key")
    monkeypatch.setattr(collector, "build_llm", lambda *a, **k: object())
    output = tmp_path / "satya.jsonl.gz"

    async def fake_collect_person(person, **kwargs):
        return (
            collector.LinkedInExtraction(
                profile_identity_confirmed=False,
                access_blocked=True,
                blocked_reason="LinkedIn authwall requires sign in",
                stop_reason="access_blocked",
            ),
            ["https://www.linkedin.com/authwall"],
            None,
        )

    monkeypatch.setattr(collector, "collect_person", fake_collect_person)
    exit_code = collector.main(
        [
            "--person",
            "satya-nadella",
            "--max-posts",
            "3",
            "--output",
            str(output),
            "--extraction-mode",
            "agent",
        ]
    )
    assert exit_code == 1
    manifest = json.loads(
        output.with_name("satya.jsonl.gz.manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["stop_reason_by_person"] == {"satya-nadella": "access_blocked"}
    assert manifest["errors"][0]["category"] == "auth_required"
    assert manifest["errors"][0]["person_id"] == "satya-nadella"
    assert read_gz_lines(output) == []


def test_blocked_batch_with_posts_yields_zero_records(tmp_path, monkeypatch) -> None:
    """access_blocked=True discards every extracted post, even with identity
    confirmed, and never calls select_records or mutates dedup state."""
    monkeypatch.setenv("BROWSER_USE_API_KEY", "test-key")
    monkeypatch.setattr(collector, "build_llm", lambda *a, **k: object())
    output = tmp_path / "satya.jsonl.gz"

    async def fake_collect_person(person, **kwargs):
        return (
            collector.LinkedInExtraction(
                profile_identity_confirmed=True,
                profile_name_seen="Satya Nadella",
                posts=[make_post()],
                access_blocked=True,
                blocked_reason="Sign in to see more posts",
                stop_reason="access_blocked",
            ),
            [person.profile_url],
            None,
        )

    def forbidden_select_records(*args, **kwargs):
        raise AssertionError("select_records must not run for blocked batches")

    monkeypatch.setattr(collector, "collect_person", fake_collect_person)
    monkeypatch.setattr(collector, "select_records", forbidden_select_records)
    exit_code = collector.main(
        [
            "--person",
            "satya-nadella",
            "--max-posts",
            "3",
            "--output",
            str(output),
            "--extraction-mode",
            "agent",
        ]
    )
    assert exit_code == 1
    assert read_gz_lines(output) == []
    manifest = json.loads(
        output.with_name("satya.jsonl.gz.manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["record_count_by_person"] == {"satya-nadella": 0}
    assert manifest["stop_reason_by_person"] == {"satya-nadella": "access_blocked"}
    assert manifest["errors"][0]["category"] == "auth_required"


def test_identity_mismatch_with_posts_yields_zero_records(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("BROWSER_USE_API_KEY", "test-key")
    monkeypatch.setattr(collector, "build_llm", lambda *a, **k: object())
    output = tmp_path / "satya.jsonl.gz"

    async def fake_collect_person(person, **kwargs):
        return (
            collector.LinkedInExtraction(
                profile_identity_confirmed=False,
                profile_name_seen="Someone Else",
                posts=[make_post()],
                access_blocked=False,
                stop_reason="identity_mismatch",
            ),
            [person.profile_url],
            None,
        )

    def forbidden_select_records(*args, **kwargs):
        raise AssertionError("select_records must not run for identity mismatches")

    monkeypatch.setattr(collector, "collect_person", fake_collect_person)
    monkeypatch.setattr(collector, "select_records", forbidden_select_records)
    exit_code = collector.main(
        [
            "--person",
            "satya-nadella",
            "--max-posts",
            "3",
            "--output",
            str(output),
            "--extraction-mode",
            "agent",
        ]
    )
    assert exit_code == 1
    assert read_gz_lines(output) == []
    manifest = json.loads(
        output.with_name("satya.jsonl.gz.manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["record_count_by_person"] == {"satya-nadella": 0}
    assert manifest["stop_reason_by_person"] == {"satya-nadella": "identity_mismatch"}
    assert manifest["errors"][0]["category"] == "identity_mismatch"


def test_resolve_people_rejects_unverified() -> None:
    registry = collector.load_registry()
    with pytest.raises(SystemExit):
        collector.resolve_people(["sam-altman"], registry)
    with pytest.raises(SystemExit):
        collector.resolve_people(["elon-musk"], registry)
    with pytest.raises(SystemExit):
        collector.resolve_people(["nobody"], registry)

    people = collector.resolve_people(["all"], registry)
    assert {p.person_id for p in people} == {
        "jensen-huang",
        "sundar-pichai",
        "clement-delangue",
        "satya-nadella",
    }
