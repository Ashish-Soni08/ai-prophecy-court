"""Browser Use collector for verified X profiles of AI leaders.

Collects authored posts only, as source material for the AI Prophecy Court
dataset. Output is gzip-compressed JSONL of raw envelopes (one envelope per
post, validating against schemas/raw-envelope.schema.json) plus a sibling
`<output>.manifest.json`. Nothing is uploaded anywhere; the envelopes feed
directly into the existing normalization and publishing pipeline.

Usage:
    uv run python scripts/collect_x_browser_use.py \
        --person sam-altman --max-posts 3 \
        --user-data-dir profiles/x \
        --output raw/browser-use/x/sam-altman.jsonl.gz

Deterministic Browser Use CDP extraction is the default. The optional
`--extraction-mode agent` path uses ChatBrowserUse or an OpenAI-compatible
model as a slower fallback for unusual layouts. Navigation is restricted to
x.com / twitter.com, and collection stops cleanly on login walls, CAPTCHAs,
or blocked pages.
"""

from __future__ import annotations

import argparse
import asyncio
import gzip
import hashlib
import json
import logging
import os
import re
import subprocess
import sys
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

import yaml

LOGGER = logging.getLogger("collect_x_browser_use")

SCHEMA_VERSION = 1
PLATFORM = "x"
COLLECTION_METHOD = "browser-use"
COLLECTOR_ID = "collect_x_browser_use"
ALLOWED_DOMAINS = ["x.com", "*.x.com", "twitter.com", "*.twitter.com"]
DEFAULT_MAX_POSTS = 3
DEFAULT_MAX_STEPS = 40
MAX_STEPS_CEILING = 200
DEFAULT_MAX_SCROLLS = 2_000
MAX_SCROLLS_CEILING = 10_000
API_KEY_ENV = "BROWSER_USE_API_KEY"
CLOUD_PROFILE_ENV = "BROWSER_USE_CLOUD_PROFILE_ID"
LLM_API_KEY_ENV = "LLM_API_KEY"
HF_TOKEN_ENV = "HF_TOKEN"
DEFAULT_OPEN_MODEL = "MiniMaxAI/MiniMax-M3"
DEFAULT_OPEN_BASE_URL = "https://router.huggingface.co/v1"
DEFAULT_USER_DATA_DIR = Path("profiles/x")
LOGIN_URL = "https://x.com/login"

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "pipeline" / "registry.yaml"

# Canonical X status URL: handle and numeric status ID are both mandatory.
X_STATUS_URL_RE = re.compile(
    r"^https://(?:www\.|mobile\.)?(?:x|twitter)\.com/"
    r"([A-Za-z0-9_]{1,15})/status(?:es)?/(\d+)(?:[/?#].*)?$"
)


def pipeline_version() -> str:
    try:
        from pipeline import __version__

        return __version__
    except Exception:  # standalone use without the installed package
        return "unknown"


class VerifiedProfile(BaseModel):
    """A manually verified X account. Only these may be scraped."""

    person_id: str
    person_name: str
    company: str
    profile_url: str
    handle: str
    start_date: date


# Manually verified accounts. Jensen Huang has no verified X account and is
# intentionally absent; the registry cross-check rejects anyone not listed
# here or not marked verified_active there.
VERIFIED_PROFILES: dict[str, VerifiedProfile] = {
    profile.person_id: profile
    for profile in (
        VerifiedProfile(
            person_id="sam-altman",
            person_name="Sam Altman",
            company="OpenAI",
            profile_url="https://x.com/sama",
            handle="sama",
            start_date=date(2022, 11, 30),
        ),
        VerifiedProfile(
            person_id="dario-amodei",
            person_name="Dario Amodei",
            company="Anthropic",
            profile_url="https://x.com/DarioAmodei",
            handle="DarioAmodei",
            start_date=date(2022, 11, 30),
        ),
        VerifiedProfile(
            person_id="sundar-pichai",
            person_name="Sundar Pichai",
            company="Google",
            profile_url="https://x.com/sundarpichai",
            handle="sundarpichai",
            start_date=date(2022, 11, 30),
        ),
        VerifiedProfile(
            person_id="satya-nadella",
            person_name="Satya Nadella",
            company="Microsoft",
            profile_url="https://x.com/satyanadella",
            handle="satyanadella",
            start_date=date(2022, 11, 30),
        ),
        VerifiedProfile(
            person_id="clement-delangue",
            person_name="Clement Delangue",
            company="Hugging Face",
            profile_url="https://x.com/ClementDelangue",
            handle="ClementDelangue",
            start_date=date(2024, 7, 1),
        ),
        VerifiedProfile(
            person_id="elon-musk",
            person_name="Elon Musk",
            company="xAI",
            profile_url="https://x.com/elonmusk",
            handle="elonmusk",
            start_date=date(2024, 7, 1),
        ),
    )
}


# --------------------------------------------------------------------------
# Extraction schema (what the Browser Use agent returns, via
# output_model_schema). Separate from the output record schema; never parsed
# from prose.
# --------------------------------------------------------------------------


class ExtractedQuotedPost(BaseModel):
    """The post quoted inside a quote post, as displayed."""

    author_handle: str | None = None
    author_name: str | None = None
    url: str | None = None
    text: str | None = None


class ExtractedEngagement(BaseModel):
    likes: int | None = None
    replies: int | None = None
    reposts: int | None = None
    quotes: int | None = None
    bookmarks: int | None = None
    views: int | None = None


class ExtractedProfileMetrics(BaseModel):
    followers: int | None = None
    following: int | None = None
    posts_count: int | None = None


class ExtractedPost(BaseModel):
    """One authored timeline item exactly as displayed. Unknown means null."""

    native_id: str | None = Field(
        default=None,
        description="Numeric status ID from the post URL, e.g. 1234567890",
    )
    url: str | None = Field(
        default=None, description="Canonical https://x.com/<handle>/status/<id> URL"
    )
    content_type: str | None = Field(
        default=None, description="One of: post, reply, repost, quote"
    )
    text: str | None = Field(
        default=None, description="Full visible post text, verbatim"
    )
    published_at: str | None = Field(
        default=None,
        description="ISO-8601 timestamp from the post's time element if visible",
    )
    timestamp_source: str | None = None
    author_handle: str | None = None
    author_name: str | None = None
    author_profile_image: str | None = None
    is_repost: bool | None = None
    quoted_post: ExtractedQuotedPost | None = None
    reply_to: str | None = Field(
        default=None, description="Handle or URL this post replies to, if a reply"
    )
    photos: list[str] = Field(default_factory=list)
    videos: list[str] = Field(default_factory=list)
    external_media_urls: list[str] = Field(default_factory=list)
    external_url: str | None = None
    hashtags: list[str] = Field(default_factory=list)
    tagged_users: list[str] = Field(default_factory=list)
    engagement: ExtractedEngagement | None = None


class XExtractionBatch(BaseModel):
    """Structured result for one profile visit."""

    displayed_handle: str | None = Field(
        default=None, description="The @handle shown on the visited profile page"
    )
    displayed_name: str | None = None
    profile_metrics: ExtractedProfileMetrics | None = None
    posts: list[ExtractedPost] = Field(default_factory=list)
    blocked: bool = Field(
        default=False,
        description="True if login wall, CAPTCHA, or block prevented collection",
    )
    block_reason: str | None = None
    stop_reason: str | None = Field(
        default=None,
        description=(
            "Why extraction stopped: max_posts_reached, start_date_crossed, "
            "no_new_posts, or blocked"
        ),
    )


# --------------------------------------------------------------------------
# Output record schema (JSONL)
# --------------------------------------------------------------------------


class MediaInfo(BaseModel):
    photos: list[str] = Field(default_factory=list)
    videos: list[str] = Field(default_factory=list)
    external_media_urls: list[str] = Field(default_factory=list)


class XPostRecord(BaseModel):
    """A fully verified authored X post.

    Identity (native ID, canonical URL, author handle) and the publication
    timestamp are mandatory: candidates that cannot be verified are rejected
    with a structured error instead of being written with nulls.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: int = SCHEMA_VERSION
    platform: Literal["x"] = PLATFORM
    person_id: str
    person_name: str
    company: str
    profile_url: str
    account_verified_manual: Literal[True] = True
    native_id: str = Field(min_length=1, pattern=r"^\d+$")
    canonical_url: str
    content_type: Literal["post", "reply", "repost", "quote"] | None
    text: str | None
    published_at: str
    author_handle: str = Field(min_length=1)
    author_name: str | None
    author_profile_image: str | None
    is_repost: bool | None
    quoted_post: ExtractedQuotedPost | None
    reply_to: str | None
    media: MediaInfo
    external_url: str | None
    hashtags: list[str]
    tagged_users: list[str]
    engagement: ExtractedEngagement
    profile_metrics: ExtractedProfileMetrics
    extracted_at: str
    collection_method: Literal["browser-use"] = COLLECTION_METHOD
    source_fields: dict[str, Any]

    @field_validator("canonical_url")
    @classmethod
    def _validate_canonical_url(cls, value: str) -> str:
        if not X_STATUS_URL_RE.match(value):
            raise ValueError(f"not an https x.com/twitter.com status URL: {value}")
        return value

    @field_validator("published_at")
    @classmethod
    def _validate_published_at(cls, value: str) -> str:
        parse_iso_datetime(value)
        return value


class RawEnvelope(BaseModel):
    """Raw archive envelope matching schemas/raw-envelope.schema.json."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    platform: Literal["x"] = PLATFORM
    person_id: str
    input_url: str
    requested_at: str
    completed_at: str
    source_extracted_at: str | None = None
    collector_id: str = COLLECTOR_ID
    collection_id: str
    collection_method: Literal["browser-use"] = COLLECTION_METHOD
    pipeline_version: str
    payload_sha256: str
    payload: dict[str, Any]


class StructuredError(BaseModel):
    person_id: str
    error_type: Literal[
        "auth_required",
        "captcha",
        "blocked",
        "handle_mismatch",
        "identity_unverified",
        "agent_failure",
        "no_structured_output",
        "invalid_record",
        "missing_timestamp",
    ]
    message: str
    url: str | None = None
    occurred_at: str


class PersonOutcome(BaseModel):
    person_id: str
    requested_max_posts: int
    effective_start_date: str
    effective_end_date: str
    record_count: int = 0
    duplicate_count: int = 0
    stop_reason: str = "not_started"


class RunManifest(BaseModel):
    run_id: str
    platform: Literal["x"] = PLATFORM
    collection_method: Literal["browser-use"] = COLLECTION_METHOD
    requested_profiles: list[dict[str, Any]]
    date_windows: dict[str, dict[str, str]]
    started_at: str
    completed_at: str
    browser_use_model: str
    execution_mode: Literal["cloud", "local-headful", "local-headless"]
    cloud_profile_configured: bool
    visited_urls: dict[str, list[str]]
    record_count_by_person: dict[str, int]
    duplicate_count: int
    stop_reason_by_person: dict[str, str]
    errors: list[StructuredError]
    output_path: str
    output_sha256: str | None
    git_commit: str | None


class CollectorConfig(BaseModel):
    persons: list[str]
    max_posts: int = Field(gt=0)
    start_date: date | None
    end_date: date
    output: Path
    headful: bool = False
    max_steps: int = Field(default=DEFAULT_MAX_STEPS, gt=0, le=MAX_STEPS_CEILING)
    max_scrolls: int = Field(
        default=DEFAULT_MAX_SCROLLS, gt=0, le=MAX_SCROLLS_CEILING
    )
    resume: bool = False
    conversation_log: Path | None = None
    llm_provider: Literal["browser-use", "openai-compatible"] = "browser-use"
    llm_model: str | None = None
    llm_base_url: str | None = None
    user_data_dir: Path | None = None
    extraction_mode: Literal["agent", "deterministic"] = "deterministic"

    @field_validator("persons")
    @classmethod
    def _validate_persons(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("At least one person is required")
        unknown = [p for p in value if p not in VERIFIED_PROFILES]
        if unknown:
            raise ValueError(
                f"No verified X account for: {', '.join(unknown)}. "
                f"Allowed: {', '.join(sorted(VERIFIED_PROFILES))}"
            )
        return value


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_iso_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def git_commit() -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalize_handle(handle: str | None) -> str | None:
    if handle is None:
        return None
    return handle.strip().lstrip("@").lower() or None


def cross_check_registry(person_ids: list[str]) -> None:
    """Refuse to run if the registry disagrees with the embedded profiles."""
    registry = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
    people = {person["id"]: person for person in registry["people"]}
    for person_id in person_ids:
        profile = VERIFIED_PROFILES[person_id]
        entry = people.get(person_id)
        if entry is None:
            raise ValueError(f"{person_id} is not present in pipeline/registry.yaml")
        account = entry["accounts"].get("x", {})
        if account.get("status") != "verified_active":
            raise ValueError(
                f"{person_id}/x is {account.get('status')!r} in the registry; "
                "refusing to scrape"
            )
        if account.get("url") != profile.profile_url:
            raise ValueError(
                f"{person_id} profile URL mismatch: registry has "
                f"{account.get('url')!r}, collector expects {profile.profile_url!r}"
            )


def effective_window(
    profile: VerifiedProfile, config: CollectorConfig
) -> tuple[date, date]:
    start = config.start_date or profile.start_date
    end = config.end_date
    if start > end:
        raise ValueError(
            f"{profile.person_id}: start date {start} is after end date {end}"
        )
    return start, end


def classify_content_type(
    post: ExtractedPost,
) -> Literal["post", "reply", "repost", "quote"] | None:
    declared = (post.content_type or "").strip().lower()
    if declared in {"post", "reply", "repost", "quote"}:
        return declared  # type: ignore[return-value]
    if post.is_repost:
        return "repost"
    if post.quoted_post is not None:
        return "quote"
    if post.reply_to:
        return "reply"
    if declared:
        # Unrecognized label and no corroborating signals: keep uncertainty.
        return None
    return "post" if post.text is not None else None


def parse_status_url(url: str | None) -> tuple[str, str] | None:
    """Return (handle, status_id) for a canonical X status URL, else None."""
    if not url:
        return None
    match = X_STATUS_URL_RE.match(url.strip())
    if not match:
        return None
    return match.group(1), match.group(2)


def timestamp_from_x_snowflake(status_id: str) -> str:
    """Decode the exact UTC creation millisecond embedded in an X status ID."""
    timestamp_ms = (int(status_id) >> 22) + 1288834974657
    return datetime.fromtimestamp(
        timestamp_ms / 1000, tz=timezone.utc
    ).isoformat(timespec="milliseconds")


def text_from_timeline_card(card_text: str | None, handle: str) -> str | None:
    """Extract post text from X's logged-out timeline card fallback."""
    if not card_text:
        return None
    lines = [line.strip() for line in card_text.splitlines() if line.strip()]
    expected = f"@{handle}".lower()
    try:
        handle_index = next(
            index for index, line in enumerate(lines) if line.lower() == expected
        )
    except StopIteration:
        return None
    # The next visible line is the timeline date/relative time. Everything
    # after it is the card's post body in this logged-out X layout.
    body = lines[handle_index + 2 :]
    if body and body[0].lower().startswith("replying to"):
        body = body[1:]
    for index, line in enumerate(body):
        if re.fullmatch(r"@[A-Za-z0-9_]{1,15}", line) and line.lower() != expected:
            # A quote card starts with the quoted author's display name and
            # handle. Exclude both from the authored post's main text.
            body = body[: max(0, index - 1)]
            break
    text = "\n".join(body).strip()
    return text or None


def timeline_card_has_quote(card_text: str | None, handle: str) -> bool:
    if not card_text:
        return False
    expected = f"@{handle}".lower()
    handles = [
        line.strip().lower()
        for line in card_text.splitlines()
        if re.fullmatch(r"@[A-Za-z0-9_]{1,15}", line.strip())
    ]
    return any(item != expected for item in handles)


def record_key(native_id: str | None, canonical_url: str | None) -> str | None:
    if native_id:
        return f"id:{native_id}"
    if canonical_url:
        return f"url:{canonical_url.rstrip('/').lower()}"
    return None


def validate_candidate(
    post: ExtractedPost,
    profile: VerifiedProfile,
    metrics: ExtractedProfileMetrics,
    extracted_at: str,
) -> tuple[XPostRecord | None, StructuredError | None]:
    """Verify one extracted post against the expected profile.

    Missing identity information is an invalid record, not uncertainty.
    Missing publication timestamps are rejected with missing_timestamp.
    """

    def reject(
        error_type: Literal["invalid_record", "missing_timestamp"], message: str
    ) -> tuple[None, StructuredError]:
        return None, StructuredError(
            person_id=profile.person_id,
            error_type=error_type,
            message=message,
            url=post.url,
            occurred_at=utc_now(),
        )

    expected = normalize_handle(profile.handle)
    if not post.url:
        return reject("invalid_record", "Missing canonical URL")
    parsed = parse_status_url(post.url)
    if parsed is None:
        return reject(
            "invalid_record", f"Not an https x.com/twitter.com status URL: {post.url}"
        )
    url_handle, url_status_id = parsed
    if normalize_handle(url_handle) != expected:
        return reject(
            "invalid_record",
            f"URL handle @{url_handle} does not match expected @{profile.handle}",
        )
    if post.native_id and post.native_id.strip() != url_status_id:
        return reject(
            "invalid_record",
            f"native_id {post.native_id!r} does not match URL status ID "
            f"{url_status_id}",
        )
    author = normalize_handle(post.author_handle)
    if author is None:
        return reject("invalid_record", "Missing author_handle")
    if author != expected:
        return reject(
            "invalid_record",
            f"author_handle @{post.author_handle} does not match expected "
            f"@{profile.handle}",
        )
    has_media = bool(post.photos or post.videos or post.external_media_urls)
    if not (post.text and post.text.strip()) and not has_media:
        return reject("invalid_record", "Post has neither text nor visible media")
    if not post.published_at:
        return reject(
            "missing_timestamp",
            "No exact publication timestamp could be read from the timeline "
            "or the status page",
        )
    try:
        parse_iso_datetime(post.published_at)
    except ValueError:
        return reject(
            "missing_timestamp",
            f"Unparseable publication timestamp: {post.published_at!r}",
        )

    record = XPostRecord(
        person_id=profile.person_id,
        person_name=profile.person_name,
        company=profile.company,
        profile_url=profile.profile_url,
        native_id=url_status_id,
        canonical_url=f"https://x.com/{url_handle}/status/{url_status_id}",
        content_type=classify_content_type(post),
        text=post.text,
        published_at=post.published_at,
        author_handle=post.author_handle,
        author_name=post.author_name,
        author_profile_image=post.author_profile_image,
        is_repost=post.is_repost,
        quoted_post=post.quoted_post,
        reply_to=post.reply_to,
        media=MediaInfo(
            photos=post.photos,
            videos=post.videos,
            external_media_urls=post.external_media_urls,
        ),
        external_url=post.external_url,
        hashtags=post.hashtags,
        tagged_users=post.tagged_users,
        engagement=post.engagement or ExtractedEngagement(),
        profile_metrics=metrics,
        extracted_at=extracted_at,
        source_fields=post.model_dump(mode="json"),
    )
    return record, None


def batch_to_records(
    batch: XExtractionBatch,
    profile: VerifiedProfile,
    extracted_at: str,
) -> tuple[list[XPostRecord], list[StructuredError]]:
    """Convert a batch into verified records, rejecting unverifiable posts."""
    records: list[XPostRecord] = []
    errors: list[StructuredError] = []
    metrics = batch.profile_metrics or ExtractedProfileMetrics()
    for post in batch.posts:
        try:
            record, error = validate_candidate(post, profile, metrics, extracted_at)
        except Exception as exc:  # pydantic.ValidationError and friends
            record, error = (
                None,
                StructuredError(
                    person_id=profile.person_id,
                    error_type="invalid_record",
                    message=f"Discarded unparseable extracted post: {exc}",
                    url=post.url,
                    occurred_at=utc_now(),
                ),
            )
        if error is not None:
            LOGGER.warning(
                "%s: rejected candidate (%s): %s",
                profile.person_id,
                error.error_type,
                error.message,
            )
            errors.append(error)
            continue
        assert record is not None
        records.append(record)
    return records, errors


def dedupe_records(
    records: list[XPostRecord], seen_keys: set[str]
) -> tuple[list[XPostRecord], int]:
    """Drop records whose key is already in seen_keys; mutates seen_keys.

    Validated records always carry a native ID, so every record has a
    stable identity key.
    """
    unique: list[XPostRecord] = []
    duplicates = 0
    for record in records:
        key = record_key(record.native_id, record.canonical_url)
        if key in seen_keys:
            duplicates += 1
            continue
        seen_keys.add(key)
        unique.append(record)
    return unique, duplicates


def filter_by_window(
    records: list[XPostRecord], start: date, end: date
) -> tuple[list[XPostRecord], int]:
    """Keep records inside [start, end], judged only on verified timestamps."""
    kept: list[XPostRecord] = []
    excluded = 0
    for record in records:
        published = parse_iso_datetime(record.published_at).date()
        if start <= published <= end:
            kept.append(record)
        else:
            excluded += 1
    return kept, excluded


def sort_newest_first(records: list[XPostRecord]) -> list[XPostRecord]:
    return sorted(
        records,
        key=lambda record: parse_iso_datetime(record.published_at),
        reverse=True,
    )


# --------------------------------------------------------------------------
# Raw envelope I/O (gzip JSONL, see schemas/raw-envelope.schema.json)
# --------------------------------------------------------------------------


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def build_envelope(
    record: XPostRecord,
    *,
    run_id: str,
    requested_at: str,
    completed_at: str,
) -> RawEnvelope:
    payload = record.model_dump(mode="json")
    return RawEnvelope(
        run_id=run_id,
        person_id=record.person_id,
        input_url=record.profile_url,
        requested_at=requested_at,
        completed_at=completed_at,
        source_extracted_at=record.extracted_at,
        collection_id=run_id,
        pipeline_version=pipeline_version(),
        payload_sha256=hashlib.sha256(canonical_json(payload)).hexdigest(),
        payload=payload,
    )


def load_existing_envelopes(
    path: Path,
) -> tuple[list[RawEnvelope], list[XPostRecord]]:
    """Read prior envelopes for --resume; payloads must be valid records."""
    if not path.exists():
        return [], []
    envelopes: list[RawEnvelope] = []
    records: list[XPostRecord] = []
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                envelope = RawEnvelope.model_validate_json(line)
                records.append(XPostRecord.model_validate(envelope.payload))
            except Exception as exc:
                raise ValueError(
                    f"Cannot resume: invalid envelope on line {line_number} "
                    f"of {path}: {exc}"
                ) from exc
            envelopes.append(envelope)
    return envelopes, records


def resume_keys(records: list[XPostRecord]) -> set[str]:
    keys: set[str] = set()
    for record in records:
        key = record_key(record.native_id, record.canonical_url)
        if key:
            keys.add(key)
        # Also index the canonical URL alone so URL-only duplicates are caught
        # even when the prior record carried a native ID.
        if record.canonical_url:
            keys.add(f"url:{record.canonical_url.rstrip('/').lower()}")
    return keys


def sort_envelopes_newest_first(envelopes: list[RawEnvelope]) -> list[RawEnvelope]:
    return sorted(
        envelopes,
        key=lambda env: parse_iso_datetime(env.payload["published_at"]),
        reverse=True,
    )


def write_envelopes_gz_atomic(path: Path, envelopes: list[RawEnvelope]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.tmp-{uuid.uuid4().hex[:8]}")
    try:
        with gzip.open(tmp_path, "wt", encoding="utf-8", newline="\n") as handle:
            for envelope in envelopes:
                handle.write(
                    json.dumps(envelope.model_dump(mode="json"), ensure_ascii=False)
                    + "\n"
                )
        os.replace(tmp_path, path)
    finally:
        tmp_path.unlink(missing_ok=True)
    return sha256_file(path)


def write_manifest(manifest: RunManifest, output: Path) -> Path:
    manifest_path = output.with_name(f"{output.name}.manifest.json")
    tmp_path = manifest_path.with_name(
        f"{manifest_path.name}.tmp-{uuid.uuid4().hex[:8]}"
    )
    try:
        tmp_path.write_text(
            json.dumps(manifest.model_dump(mode="json"), indent=2, ensure_ascii=False)
            + "\n",
            encoding="utf-8",
        )
        os.replace(tmp_path, manifest_path)
    finally:
        tmp_path.unlink(missing_ok=True)
    return manifest_path


# --------------------------------------------------------------------------
# Browser Use task
# --------------------------------------------------------------------------


def build_task(profile: VerifiedProfile, max_posts: int, start: date, end: date) -> str:
    return f"""\
Collect the most recent authored posts from one X (Twitter) profile.

Target profile: {profile.profile_url} (expected handle @{profile.handle})

Steps:
1. Go directly to {profile.profile_url}.
2. Confirm the page shows the handle @{profile.handle}. Record the displayed
   handle in displayed_handle. If the displayed handle does not match, stop
   immediately and return with blocked=false, posts=[] and
   stop_reason="handle_mismatch".
3. Read the profile metrics (followers, following, posts count) if visible.
4. Make sure the "Posts" tab of the profile timeline is selected.
5. Extract the visible posts authored by @{profile.handle}, newest first.
   Scroll down gradually and re-extract until ONE of these happens, then stop:
   - you have {max_posts} qualifying posts (stop_reason="max_posts_reached");
   - you reach posts published before {start.isoformat()}
     (stop_reason="start_date_crossed");
   - no new posts appear after 3 extra scrolls (stop_reason="no_new_posts");
   - access is blocked (stop_reason="blocked").
6. Only if a post's full text, exact timestamp, canonical URL, quoted-post
   details, or engagement numbers are not visible on the timeline, open that
   individual post page, read them, and go back.
7. Every post MUST have an exact publication timestamp; a post with
   published_at=null is discarded and does NOT count toward the {max_posts}
   posts. The reliable way to get all visible timestamps in one step is to
   run this JavaScript with the evaluate tool while the timeline is open:
     Array.from(document.querySelectorAll("article a time")).map(t =>
       [t.closest("a").href, t.getAttribute("datetime")])
   This returns [post URL, exact ISO-8601 timestamp] pairs; match them to
   posts by the status ID in the URL. If a timestamp is still missing, open
   that post's canonical status page and run the same JavaScript there. Only
   if that also fails, set published_at to null for that post; never estimate
   it from relative labels (like "2h" or "Mar 3"), status IDs, or memory.

Qualifying posts are ONLY items authored by @{profile.handle}: original
posts, replies written by @{profile.handle}, reposts by @{profile.handle},
and quote posts by @{profile.handle}. Label each with content_type as
"post", "reply", "repost", or "quote".

Never include: replies written by other users, recommended or suggested
posts, advertisements or promoted posts, trending content, "who to follow"
items, search results, or anything not authored by @{profile.handle}.
Only consider posts published between {start.isoformat()} and {end.isoformat()}
(inclusive).

For each qualifying post record exactly what the page displays:
- native_id: the numeric status ID from the post URL
- url: the canonical post URL (https://x.com/{profile.handle}/status/<id>)
- text: the complete post text, verbatim
- published_at: the ISO-8601 timestamp from the post's time element
- author handle, author display name, author profile image URL
- is_repost, quoted_post details, reply_to if applicable
- photo URLs, video URLs, external media URLs (do not download anything)
- external link URL, hashtags, tagged users
- engagement counts (likes, replies, reposts, quotes, bookmarks, views)

If any value is not visible, leave it null. Never guess, infer, or fabricate
values. Do not use search engines or any site other than x.com / twitter.com.

If you encounter a login wall, CAPTCHA, age gate, or any page that blocks
access: do NOT attempt to log in, solve the CAPTCHA, or work around the
block. Stop immediately and return blocked=true with a short block_reason
and whatever qualifying posts you already extracted.
"""


GUARDRAIL_SYSTEM_MESSAGE = (
    "You are collecting public source material for a research dataset. "
    "Stay strictly on x.com and twitter.com. Never attempt to authenticate, "
    "bypass CAPTCHAs, evade rate limits, or circumvent any access control. "
    "If blocked, finish immediately with blocked=true. Report only values "
    "actually displayed on the page; use null for anything not visible."
)


# --------------------------------------------------------------------------
# Collection
# --------------------------------------------------------------------------


def build_llm(config: CollectorConfig) -> Any:
    """Build the agent LLM for the configured provider."""
    if config.llm_provider == "browser-use":
        from browser_use import ChatBrowserUse

        return ChatBrowserUse()
    api_key = os.getenv(LLM_API_KEY_ENV) or os.getenv(HF_TOKEN_ENV)
    if not api_key:
        raise SystemExit(
            f"{LLM_API_KEY_ENV} or {HF_TOKEN_ENV} is required for "
            "--llm openai-compatible"
        )
    open_model_chat = _open_model_chat_class()
    return open_model_chat(
        model=config.llm_model or DEFAULT_OPEN_MODEL,
        base_url=config.llm_base_url or DEFAULT_OPEN_BASE_URL,
        api_key=api_key,
    )


def _open_model_chat_class() -> type:
    """ChatOpenAI variant for open endpoints such as MiniMax-M3 on the HF
    Inference Providers router.

    Such endpoints often reject the json_schema response_format, and open
    models sometimes wrap their JSON answer in prose. Structured calls embed
    the schema in the system prompt, request a plain completion, and leniently
    locate the JSON object before strict Pydantic validation. Values are never
    repaired or fabricated; unparseable output stays a failure.
    """
    from browser_use import ChatOpenAI
    from browser_use.llm.schema import SchemaOptimizer
    from browser_use.llm.views import ChatInvokeCompletion

    class OpenModelChat(ChatOpenAI):
        async def ainvoke(self, messages, output_format=None, **kwargs):  # type: ignore[override]
            if output_format is None:
                return await super().ainvoke(messages, None, **kwargs)
            schema = SchemaOptimizer.create_optimized_json_schema(output_format)
            schema_text = (
                "\n\nRespond with ONLY one JSON object that validates against "
                f"this JSON schema, with no surrounding prose:\n{json.dumps(schema)}"
            )
            patched = list(messages)
            if (
                patched
                and getattr(patched[0], "role", None) == "system"
                and isinstance(patched[0].content, str)
            ):
                patched[0] = patched[0].model_copy(
                    update={"content": patched[0].content + schema_text}
                )
            raw = await super().ainvoke(patched, None, **kwargs)
            text = raw.completion or ""
            start, end = text.find("{"), text.rfind("}")
            if start < 0 or end <= start:
                raise ValueError(
                    "Model response contained no JSON object for structured output"
                )
            parsed = output_format.model_validate_json(text[start : end + 1])
            return ChatInvokeCompletion(
                completion=parsed,
                usage=raw.usage,
                stop_reason=getattr(raw, "stop_reason", None),
            )

    return OpenModelChat


def execution_mode(config: CollectorConfig, use_cloud_browser: bool) -> str:
    if use_cloud_browser:
        return "cloud"
    return "local-headful" if config.headful else "local-headless"


def make_browser(
    config: CollectorConfig,
    use_cloud_browser: bool,
    cloud_profile_id: str | None,
) -> Any:
    """Create the Browser instance. Separated so tests can stub it."""
    # Imported lazily so unit tests and --help do not require the extra.
    from browser_use import Browser

    browser_kwargs: dict[str, Any] = {
        "allowed_domains": ALLOWED_DOMAINS,
        # The collector owns cleanup. Keeping the browser alive after the
        # agent stops lets the deterministic CDP fallback inspect the page.
        "keep_alive": True,
    }
    if use_cloud_browser:
        browser_kwargs["use_cloud"] = True
        if cloud_profile_id:
            browser_kwargs["cloud_profile_id"] = cloud_profile_id
    else:
        browser_kwargs["headless"] = not config.headful
        if config.user_data_dir:
            # Persistent local profile (see --setup-login): reuses a session
            # the user logged into manually; never holds raw credentials.
            browser_kwargs["user_data_dir"] = str(config.user_data_dir)
    return Browser(**browser_kwargs)


def make_agent(
    profile: VerifiedProfile,
    config: CollectorConfig,
    llm: Any,
    browser: Any,
) -> Any:
    """Create the Browser Use Agent. Separated so tests can stub it."""
    from browser_use import Agent

    start, end = effective_window(profile, config)
    agent_kwargs: dict[str, Any] = {
        "task": build_task(profile, config.max_posts, start, end),
        "llm": llm,
        "browser": browser,
        "output_model_schema": XExtractionBatch,
        "use_vision": "auto",
        "max_failures": 3,
        "llm_timeout": 120,
        "step_timeout": 150,
        "extend_system_message": GUARDRAIL_SYSTEM_MESSAGE,
    }
    if config.conversation_log:
        config.conversation_log.mkdir(parents=True, exist_ok=True)
        agent_kwargs["save_conversation_path"] = str(
            config.conversation_log / profile.person_id
        )
    return Agent(**agent_kwargs)


def decode_page_result(raw: Any) -> Any:
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw
    return raw


async def evaluate_page(page: Any, script: str) -> Any:
    return decode_page_result(await page.evaluate(script))


def parse_metric_count(value: str | None) -> int | None:
    if not value:
        return None
    match = re.search(
        r"(\d+(?:[.,]\d+)?)\s*([KMB])?",
        value.strip().replace(",", "").upper(),
    )
    if not match:
        return None
    number = float(match.group(1))
    multiplier = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}.get(
        match.group(2), 1
    )
    return int(number * multiplier)


def repair_mojibake(value: str | None) -> str | None:
    markers = ("\u00c3", "\u00e2", "\u00f0")
    if not value or not any(marker in value for marker in markers):
        return value
    try:
        return value.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return value


async def dismiss_x_cookie_consent(page: Any) -> str | None:
    result = await evaluate_page(
        page,
        """() => {
          const choices = [
            "Refuse non-essential cookies",
            "Reject non-essential cookies",
            "Accept all cookies"
          ];
          const elements = [...document.querySelectorAll("button, [role='button']")];
          for (const choice of choices) {
            const target = elements.find(el =>
              (el.innerText || el.textContent || "").trim() === choice
            );
            if (target) {
              target.click();
              return choice;
            }
          }
          return null;
        }""",
    )
    if isinstance(result, str) and result:
        LOGGER.info("Dismissed X cookie consent with: %s", result)
        await asyncio.sleep(2)
        return result
    return None


async def recover_x_timeline(page: Any, *, reload_page: bool = False) -> str:
    result = await evaluate_page(
        page,
        """() => {
          const elements = [...document.querySelectorAll(
            "button, [role='button'], a[role='tab'], a"
          )];
          const text = node =>
            (node.innerText || node.textContent || "").trim().toLowerCase();
          const newPosts = elements.find(node => text(node) === "see new posts");
          if (newPosts) {
            newPosts.click();
            return "see_new_posts";
          }
          const postsTab = elements.find(node =>
            text(node) === "posts" && (
              node.getAttribute("role") === "tab" ||
              (node.getAttribute("href") || "").match(/^\/[^/]+\/?$/)
            )
          );
          if (postsTab) {
            postsTab.click();
            return "posts_tab";
          }
          window.scrollBy({top: 2, behavior: "instant"});
          return "viewport_nudge";
        }""",
    )
    action = result if isinstance(result, str) else "unknown"
    if reload_page:
        await page.reload()
        return f"{action}+reload"
    return action


async def wait_for_x_timeline(
    page: Any, timeout_seconds: int = 45
) -> dict[str, Any]:
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    last_state: dict[str, Any] = {}
    attempts = 0
    reloaded = False
    while asyncio.get_running_loop().time() < deadline:
        await dismiss_x_cookie_consent(page)
        state = await evaluate_page(
            page,
            """() => ({
              url: location.href,
              title: document.title,
              articles: document.querySelectorAll("article").length,
              statusLinks: document.querySelectorAll('a[href*="/status/"]').length,
              body: (document.body?.innerText || "").slice(0, 500)
            })""",
        )
        if isinstance(state, dict):
            last_state = state
            url = str(state.get("url") or "")
            body = str(state.get("body") or "").lower()
            if "/login" in url or "/i/flow/login" in url:
                raise PermissionError("X redirected to a login page")
            if "captcha" in body or "verify you are human" in body:
                raise PermissionError("X displayed a verification challenge")
            if state.get("articles", 0) > 0 and state.get("statusLinks", 0) > 0:
                return state
            attempts += 1
            if attempts in {5, 12, 20}:
                action = await recover_x_timeline(
                    page, reload_page=attempts == 20 and not reloaded
                )
                reloaded = reloaded or "+reload" in action
                LOGGER.info("X timeline recovery action: %s", action)
                await asyncio.sleep(3)
        await asyncio.sleep(1)
    raise RuntimeError(f"X timeline did not hydrate: {last_state}")


async def extract_x_timeline_cards(
    page: Any, expected_handle: str
) -> list[dict[str, Any]]:
    result = await evaluate_page(
        page,
        """() => {
          const expected = %s;
          const rows = [];
          for (const article of document.querySelectorAll("article")) {
            const times = [...article.querySelectorAll("time")];
            const time = times[0];
            const timeLink = time?.closest("a");
            const href = timeLink?.href ||
              [...article.querySelectorAll('a[href*="/status/"]')]
                .map(a => a.href)
                .find(h => h && h.toLowerCase().includes(`/${expected}/status/`));
            if (!href || !href.toLowerCase().includes(`/${expected}/status/`)) {
              continue;
            }
            const texts = [...article.querySelectorAll('[data-testid="tweetText"]')];
            const text = texts[0]?.innerText?.trim() || null;
            const body = article.innerText || "";
            const links = [...article.querySelectorAll("a")]
              .map(a => a.href)
              .filter(Boolean);
            const statusLinks = links.filter(h => /\\/(?:status|statuses)\\/\\d+/.test(h));
            const quotedLink = statusLinks.find(h =>
              !h.toLowerCase().includes(`/${expected}/status/`)
            ) || null;
            const quotedText = texts.length > 1
              ? texts[texts.length - 1]?.innerText?.trim() || null
              : null;
            const quotedAuthor = quotedLink?.match(
              /^https:\\/\\/(?:www\\.)?(?:x|twitter)\\.com\\/([^/]+)\\/status\\/(\\d+)/i
            )?.[1] || null;
            const photos = [...article.querySelectorAll("img")]
              .map(img => img.src)
              .filter(src => src && src.includes("pbs.twimg.com/media"));
            const videos = [...article.querySelectorAll("video")]
              .map(video => video.src || video.poster)
              .filter(Boolean);
            const externalUrls = links.filter(h =>
              !h.includes("x.com/") &&
              !h.includes("twitter.com/") &&
              !h.includes("t.co/")
            );
            const metric = testId => {
              const node = article.querySelector(`[data-testid="${testId}"]`);
              return node?.getAttribute("aria-label") ||
                node?.innerText?.trim() || null;
            };
            const viewsLink = [...article.querySelectorAll("a")]
              .find(a => (a.href || "").includes("/analytics"));
            const replyMatch = body.match(/Replying to\\s+(@[A-Za-z0-9_]+)/i);
            const reposted = /\\bReposted\\b/i.test(body);
            rows.push({
              url: href,
              text,
              published_at: time?.getAttribute("datetime") || null,
              body,
              pinned: /(^|\\n)Pinned(\\n|$)/i.test(body),
              is_repost: reposted,
              reply_to: replyMatch ? replyMatch[1] : null,
              has_quote: texts.length > 1 || times.length > 1 || Boolean(quotedLink),
              quoted_post: quotedText || quotedLink ? {
                author_handle: quotedAuthor,
                author_name: null,
                url: quotedLink,
                text: quotedText
              } : null,
              photos: [...new Set(photos)],
              videos: [...new Set(videos)],
              external_media_urls: [],
              external_url: externalUrls[0] || null,
              hashtags: [...new Set((text?.match(/#[A-Za-z0-9_]+/g) || []))],
              tagged_users: [...new Set((text?.match(/@[A-Za-z0-9_]+/g) || []))],
              metrics: {
                replies: metric("reply"),
                reposts: metric("retweet"),
                likes: metric("like") || metric("unlike"),
                bookmarks: metric("bookmark"),
                views: viewsLink?.getAttribute("aria-label") ||
                  viewsLink?.innerText?.trim() || null
              }
            });
          }
          return rows;
        }"""
        % json.dumps(expected_handle.lower()),
    )
    return result if isinstance(result, list) else []


async def extract_x_profile_identity(page: Any) -> dict[str, Any]:
    result = await evaluate_page(
        page,
        """() => {
          const userName = document.querySelector('[data-testid="UserName"]')
            ?.innerText || "";
          const title = document.title || "";
          const handle = userName.match(/@([A-Za-z0-9_]{1,15})/)?.[1] ||
            title.match(/@([A-Za-z0-9_]{1,15})/)?.[1] || null;
          const body = document.body?.innerText || "";
          const metric = label => {
            const match = body.match(new RegExp(
              "([0-9.,]+\\\\s*[KMB]?)\\\\s+" + label, "i"
            ));
            return match ? match[1] : null;
          };
          return {
            handle,
            name: userName.split("\\n")[0] || title.split(" (@")[0] || null,
            followers: metric("Followers"),
            following: metric("Following"),
            posts_count: body.match(/([0-9.,]+\\s*[KMB]?)\\s+posts/i)?.[1] || null
          };
        }""",
    )
    return result if isinstance(result, dict) else {}


async def advance_x_timeline(page: Any) -> dict[str, Any]:
    result = await evaluate_page(
        page,
        """() => {
          const articles = [...document.querySelectorAll("article")];
          const last = articles.at(-1);
          const before = window.scrollY;
          if (last) {
            last.scrollIntoView({block: "end", behavior: "instant"});
          }
          window.scrollBy({top: Math.max(window.innerHeight, 900), behavior: "instant"});
          return {
            before,
            after: window.scrollY,
            articles: articles.length,
            documentHeight: document.documentElement.scrollHeight
          };
        }""",
    )
    return result if isinstance(result, dict) else {}


async def wait_for_new_x_cards(
    page: Any,
    expected_handle: str,
    known_ids: set[str],
    timeout_seconds: int = 12,
) -> tuple[list[dict[str, Any]], bool]:
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    latest: list[dict[str, Any]] = []
    while asyncio.get_running_loop().time() < deadline:
        latest = await extract_x_timeline_cards(page, expected_handle)
        current_ids = {
            parsed[1]
            for card in latest
            if (parsed := parse_status_url(card.get("url")))
        }
        if current_ids - known_ids:
            return latest, True
        await asyncio.sleep(1)
    return latest, False


def x_card_to_post(
    card: dict[str, Any], profile: VerifiedProfile
) -> ExtractedPost | None:
    parsed = parse_status_url(card.get("url"))
    if (
        not parsed
        or normalize_handle(parsed[0]) != normalize_handle(profile.handle)
        or not card.get("published_at")
    ):
        return None
    content_type = (
        "repost"
        if card.get("is_repost")
        else (
            "reply"
            if card.get("reply_to")
            else ("quote" if card.get("has_quote") else "post")
        )
    )
    metrics = card.get("metrics") or {}
    quoted = card.get("quoted_post")
    return ExtractedPost(
        native_id=parsed[1],
        url=f"https://x.com/{profile.handle}/status/{parsed[1]}",
        content_type=content_type,
        text=repair_mojibake(card.get("text")),
        published_at=card["published_at"],
        timestamp_source="dom_datetime",
        author_handle=profile.handle,
        author_name=profile.person_name,
        is_repost=bool(card.get("is_repost")),
        quoted_post=ExtractedQuotedPost(**quoted) if quoted else None,
        reply_to=card.get("reply_to"),
        photos=card.get("photos") or [],
        videos=card.get("videos") or [],
        external_media_urls=card.get("external_media_urls") or [],
        external_url=card.get("external_url"),
        hashtags=card.get("hashtags") or [],
        tagged_users=card.get("tagged_users") or [],
        engagement=ExtractedEngagement(
            replies=parse_metric_count(metrics.get("replies")),
            reposts=parse_metric_count(metrics.get("reposts")),
            likes=parse_metric_count(metrics.get("likes")),
            bookmarks=parse_metric_count(metrics.get("bookmarks")),
            views=parse_metric_count(metrics.get("views")),
        ),
    )


async def deterministic_x_fallback(
    browser: Any,
    profile: VerifiedProfile,
    max_posts: int,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
    max_scrolls: int = DEFAULT_MAX_SCROLLS,
) -> XExtractionBatch | None:
    """Collect an authenticated X timeline with deterministic Browser Use CDP."""
    try:
        page = await browser.must_get_current_page()
        await page.goto(profile.profile_url)
        await dismiss_x_cookie_consent(page)
        try:
            await wait_for_x_timeline(page)
        except RuntimeError:
            replies_url = profile.profile_url.rstrip("/") + "/with_replies"
            LOGGER.info(
                "%s: main profile timeline did not hydrate; trying %s",
                profile.person_id,
                replies_url,
            )
            await page.goto(replies_url)
            await dismiss_x_cookie_consent(page)
            await wait_for_x_timeline(page)
        identity = await extract_x_profile_identity(page)
        posts: dict[str, ExtractedPost] = {}
        stagnant_scrolls = 0
        scrolls = 0
        crossed_start = False

        while len(posts) < max_posts and scrolls <= max_scrolls:
            cards = await extract_x_timeline_cards(page, profile.handle)
            for card in cards:
                post = x_card_to_post(card, profile)
                if post is None:
                    continue
                published = parse_iso_datetime(post.published_at).date()
                if start_date and published < start_date:
                    if not card.get("pinned"):
                        crossed_start = True
                    continue
                if end_date and published > end_date:
                    continue
                posts[post.native_id or ""] = post
            if len(posts) >= max_posts or crossed_start or scrolls == max_scrolls:
                break

            known_ids = set(posts)
            scroll_state = await advance_x_timeline(page)
            scrolls += 1
            new_cards, found_new = await wait_for_new_x_cards(
                page, profile.handle, known_ids
            )
            for card in new_cards:
                post = x_card_to_post(card, profile)
                if post is None:
                    continue
                published = parse_iso_datetime(post.published_at).date()
                if start_date and published < start_date:
                    if not card.get("pinned"):
                        crossed_start = True
                    continue
                if end_date and published > end_date:
                    continue
                posts[post.native_id or ""] = post
            LOGGER.info(
                "%s: deterministic scroll %d found_new=%s total=%d position=%s",
                profile.person_id,
                scrolls,
                found_new,
                len(posts),
                scroll_state.get("after"),
            )
            stagnant_scrolls = 0 if found_new else stagnant_scrolls + 1
            if crossed_start or stagnant_scrolls >= 3:
                break

        ordered = sorted(
            posts.values(),
            key=lambda post: parse_iso_datetime(post.published_at or ""),
            reverse=True,
        )[:max_posts]
        if not ordered:
            return None
        return XExtractionBatch(
            displayed_handle=identity.get("handle"),
            displayed_name=repair_mojibake(identity.get("name"))
            or profile.person_name,
            profile_metrics=ExtractedProfileMetrics(
                followers=parse_metric_count(identity.get("followers")),
                following=parse_metric_count(identity.get("following")),
                posts_count=parse_metric_count(identity.get("posts_count")),
            ),
            posts=ordered,
            blocked=False,
            stop_reason=(
                "start_date_crossed"
                if crossed_start
                else (
                    "max_posts_reached"
                    if len(ordered) >= max_posts
                    else (
                        "max_scrolls_reached"
                        if scrolls >= max_scrolls
                        else "no_new_posts"
                    )
                )
            ),
        )
    except PermissionError as exc:
        return XExtractionBatch(
            displayed_handle=None,
            posts=[],
            blocked=True,
            block_reason=str(exc),
            stop_reason="blocked",
        )
    except Exception:
        LOGGER.warning(
            "%s: deterministic CDP extraction failed",
            profile.person_id,
            exc_info=True,
        )
        return None


async def collect_person(
    profile: VerifiedProfile,
    config: CollectorConfig,
    *,
    llm: Any,
    use_cloud_browser: bool,
    cloud_profile_id: str | None,
) -> tuple[XExtractionBatch | None, list[str], list[StructuredError]]:
    """Run one Browser Use agent for one profile.

    Returns (batch, visited_urls, errors). batch is None on hard failure.
    The browser session is always killed, on every exit path.
    """
    errors: list[StructuredError] = []
    visited: list[str] = []
    start_date, end_date = effective_window(profile, config)

    browser = make_browser(config, use_cloud_browser, cloud_profile_id)
    try:
        if config.extraction_mode == "deterministic":
            try:
                await browser.start()
                batch = await deterministic_x_fallback(
                    browser,
                    profile,
                    config.max_posts,
                    start_date=start_date,
                    end_date=end_date,
                    max_scrolls=config.max_scrolls,
                )
            except Exception as exc:
                LOGGER.error(
                    "%s: deterministic collection failed: %s",
                    profile.person_id,
                    exc,
                )
                batch = None
            if batch is None:
                errors.append(
                    StructuredError(
                        person_id=profile.person_id,
                        error_type="agent_failure",
                        message="Deterministic browser extraction returned no posts",
                        url=profile.profile_url,
                        occurred_at=utc_now(),
                    )
                )
            return batch, [profile.profile_url], errors

        agent = make_agent(profile, config, llm, browser)
        try:
            history = await agent.run(max_steps=config.max_steps)
        except Exception as exc:
            LOGGER.error("%s: agent run failed: %s", profile.person_id, exc)
            fallback = await deterministic_x_fallback(
                browser,
                profile,
                config.max_posts,
                start_date=start_date,
                end_date=end_date,
                max_scrolls=config.max_scrolls,
            )
            if fallback is not None:
                return fallback, visited, errors
            errors.append(
                StructuredError(
                    person_id=profile.person_id,
                    error_type="agent_failure",
                    message=str(exc),
                    url=profile.profile_url,
                    occurred_at=utc_now(),
                )
            )
            return None, visited, errors

        try:
            visited = [str(url) for url in history.urls() if url]
        except Exception:  # diagnostics only; never fail the run on this
            visited = []

        batch: XExtractionBatch | None = getattr(history, "structured_output", None)
        if batch is None:
            final = history.final_result()
            if final:
                try:
                    batch = XExtractionBatch.model_validate_json(final)
                except Exception as exc:
                    LOGGER.error(
                        "%s: structured output missing/invalid: %s",
                        profile.person_id,
                        exc,
                    )
            if batch is None:
                fallback = await deterministic_x_fallback(
                    browser,
                    profile,
                    config.max_posts,
                    start_date=start_date,
                    end_date=end_date,
                    max_scrolls=config.max_scrolls,
                )
                if fallback is not None:
                    return fallback, visited, errors
                errors.append(
                    StructuredError(
                        person_id=profile.person_id,
                        error_type="no_structured_output",
                        message="Agent finished without a valid XExtractionBatch",
                        url=profile.profile_url,
                        occurred_at=utc_now(),
                    )
                )
                return None, visited, errors
        if not batch.blocked and not batch.posts:
            LOGGER.info(
                "%s: agent returned no posts; trying deterministic CDP fallback",
                profile.person_id,
            )
            fallback = await deterministic_x_fallback(
                browser,
                profile,
                config.max_posts,
                start_date=start_date,
                end_date=end_date,
                max_scrolls=config.max_scrolls,
            )
            if fallback is not None:
                batch = fallback
        return batch, visited, errors
    finally:
        # Cleanup failure may be logged but must never replace the result.
        try:
            await browser.kill()
        except Exception:
            LOGGER.warning(
                "%s: browser cleanup failed", profile.person_id, exc_info=True
            )


def classify_block(
    reason: str | None,
) -> Literal["auth_required", "captcha", "blocked"]:
    lowered = (reason or "").lower()
    if "captcha" in lowered or "challenge" in lowered:
        return "captcha"
    if (
        "log in" in lowered
        or "login" in lowered
        or "sign in" in lowered
        or "auth" in lowered
    ):
        return "auth_required"
    return "blocked"


async def run_collection(config: CollectorConfig) -> RunManifest:
    if (
        config.extraction_mode == "agent"
        and config.llm_provider == "browser-use"
        and not os.getenv(API_KEY_ENV)
    ):
        raise SystemExit(f"{API_KEY_ENV} is required")
    llm = build_llm(config) if config.extraction_mode == "agent" else None
    # Cloud browser is the production default; a local browser is used when
    # there is no Browser Use API key (possible only in openai-compatible
    # mode), in --headful debugging, or with a persistent --user-data-dir.
    use_cloud_browser = (
        not config.headful
        and config.user_data_dir is None
        and bool(os.getenv(API_KEY_ENV))
    )
    if not use_cloud_browser and not config.headful and not os.getenv(API_KEY_ENV):
        LOGGER.warning(
            "%s is not set; using a local headless browser instead of "
            "Browser Use Cloud",
            API_KEY_ENV,
        )
    cloud_profile_id = os.getenv(CLOUD_PROFILE_ENV) or None
    cross_check_registry(config.persons)

    run_id = f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:8]}"
    started_at = utc_now()
    LOGGER.info("Run %s starting for: %s", run_id, ", ".join(config.persons))

    existing_envelopes: list[RawEnvelope] = []
    existing_records: list[XPostRecord] = []
    if config.resume:
        existing_envelopes, existing_records = load_existing_envelopes(config.output)
    seen: set[str] = resume_keys(existing_records)
    if existing_records:
        LOGGER.info(
            "Resume: %d existing envelopes, %d dedupe keys",
            len(existing_envelopes),
            len(seen),
        )

    new_envelopes: list[RawEnvelope] = []
    errors: list[StructuredError] = []
    visited_urls: dict[str, list[str]] = {}
    outcomes: dict[str, PersonOutcome] = {}
    duplicate_total = 0
    date_windows: dict[str, dict[str, str]] = {}

    for person_id in config.persons:
        profile = VERIFIED_PROFILES[person_id]
        start, end = effective_window(profile, config)
        date_windows[person_id] = {
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
        }
        outcome = PersonOutcome(
            person_id=person_id,
            requested_max_posts=config.max_posts,
            effective_start_date=start.isoformat(),
            effective_end_date=end.isoformat(),
        )
        outcomes[person_id] = outcome
        LOGGER.info(
            "%s: collecting up to %d posts (%s..%s)",
            person_id,
            config.max_posts,
            start,
            end,
        )

        requested_at = utc_now()
        batch, visited, person_errors = await collect_person(
            profile,
            config,
            llm=llm,
            use_cloud_browser=use_cloud_browser,
            cloud_profile_id=cloud_profile_id,
        )
        completed_at = utc_now()
        visited_urls[person_id] = visited
        errors.extend(person_errors)
        if batch is None:
            outcome.stop_reason = "agent_failure"
            continue

        if batch.blocked:
            error_type = classify_block(batch.block_reason)
            LOGGER.warning(
                "%s: access blocked (%s): %s",
                person_id,
                error_type,
                batch.block_reason,
            )
            errors.append(
                StructuredError(
                    person_id=person_id,
                    error_type=error_type,
                    message=batch.block_reason or "Access blocked",
                    url=profile.profile_url,
                    occurred_at=utc_now(),
                )
            )

        displayed = normalize_handle(batch.displayed_handle)
        expected = normalize_handle(profile.handle)
        if displayed is None:
            LOGGER.error(
                "%s: agent did not report a displayed handle; "
                "discarding extracted posts",
                person_id,
            )
            errors.append(
                StructuredError(
                    person_id=person_id,
                    error_type="identity_unverified",
                    message=(
                        "Agent reported no displayed handle; records cannot be "
                        "attributed to a verified profile"
                    ),
                    url=profile.profile_url,
                    occurred_at=utc_now(),
                )
            )
            outcome.stop_reason = "blocked" if batch.blocked else "identity_unverified"
            continue
        if displayed != expected:
            LOGGER.error(
                "%s: handle mismatch: expected @%s, page showed @%s; "
                "discarding extracted posts",
                person_id,
                profile.handle,
                batch.displayed_handle,
            )
            errors.append(
                StructuredError(
                    person_id=person_id,
                    error_type="handle_mismatch",
                    message=(
                        f"Expected @{profile.handle}, page displayed "
                        f"@{batch.displayed_handle}"
                    ),
                    url=profile.profile_url,
                    occurred_at=utc_now(),
                )
            )
            outcome.stop_reason = "handle_mismatch"
            continue

        records, conversion_errors = batch_to_records(batch, profile, utc_now())
        errors.extend(conversion_errors)
        records, excluded = filter_by_window(records, start, end)
        if excluded:
            LOGGER.info(
                "%s: excluded %d records outside %s..%s",
                person_id,
                excluded,
                start,
                end,
            )
        records = sort_newest_first(records)
        records, duplicates = dedupe_records(records, seen)
        records = records[: config.max_posts]
        duplicate_total += duplicates
        outcome.record_count = len(records)
        outcome.duplicate_count = duplicates
        if batch.posts and not records:
            outcome.stop_reason = (
                "no_new_records" if duplicates else "validation_failure"
            )
        else:
            outcome.stop_reason = (
                "blocked" if batch.blocked else (batch.stop_reason or "completed")
            )
        new_envelopes.extend(
            build_envelope(
                record,
                run_id=run_id,
                requested_at=requested_at,
                completed_at=completed_at,
            )
            for record in records
        )
        if records:
            checkpoint = sort_envelopes_newest_first(
                existing_envelopes + new_envelopes
            )
            checkpoint_sha = write_envelopes_gz_atomic(config.output, checkpoint)
            LOGGER.info(
                "%s: checkpointed %d total envelopes (sha256=%s)",
                person_id,
                len(checkpoint),
                checkpoint_sha,
            )
        LOGGER.info(
            "%s: kept %d records (%d duplicates), stop_reason=%s",
            person_id,
            len(records),
            duplicates,
            outcome.stop_reason,
        )

    final_envelopes = sort_envelopes_newest_first(existing_envelopes + new_envelopes)
    failed_without_records = not new_envelopes and bool(errors)
    if failed_without_records and config.output.exists() and not config.resume:
        output_sha256 = sha256_file(config.output)
        LOGGER.error(
            "Run accepted no records and reported errors; preserving existing "
            "archive %s (sha256=%s)",
            config.output,
            output_sha256,
        )
    else:
        output_sha256 = write_envelopes_gz_atomic(config.output, final_envelopes)
        LOGGER.info(
            "Wrote %d raw envelopes to %s (sha256=%s)",
            len(final_envelopes),
            config.output,
            output_sha256,
        )

    manifest = RunManifest(
        run_id=run_id,
        requested_profiles=[
            {
                "person_id": pid,
                "profile_url": VERIFIED_PROFILES[pid].profile_url,
                "max_posts": config.max_posts,
                "max_scrolls": config.max_scrolls,
            }
            for pid in config.persons
        ],
        date_windows=date_windows,
        started_at=started_at,
        completed_at=utc_now(),
        browser_use_model=(
            "deterministic-cdp"
            if config.extraction_mode == "deterministic"
            else getattr(llm, "model", type(llm).__name__)
        ),
        execution_mode=execution_mode(config, use_cloud_browser),
        cloud_profile_configured=bool(cloud_profile_id),
        visited_urls=visited_urls,
        record_count_by_person={
            pid: outcome.record_count for pid, outcome in outcomes.items()
        },
        duplicate_count=duplicate_total,
        stop_reason_by_person={
            pid: outcome.stop_reason for pid, outcome in outcomes.items()
        },
        errors=errors,
        output_path=str(config.output),
        output_sha256=output_sha256,
        git_commit=git_commit(),
    )
    manifest_path = write_manifest(manifest, config.output)
    LOGGER.info("Manifest written to %s", manifest_path)
    return manifest


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Browser Use collector for verified X profiles",
    )
    parser.add_argument(
        "--person",
        action="append",
        dest="persons",
        metavar="PERSON_ID",
        help=(
            "Registry person id; may be repeated, or 'all' for every verified "
            "profile (default: sam-altman)"
        ),
    )
    parser.add_argument(
        "--max-posts",
        type=int,
        default=None,
        help=f"Maximum posts per person (default: {DEFAULT_MAX_POSTS})",
    )
    parser.add_argument("--start-date", help="Override start date (YYYY-MM-DD)")
    parser.add_argument(
        "--end-date", help="Override end date (YYYY-MM-DD, default: today UTC)"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help=(
            "Raw-envelope destination path (gzip JSONL, e.g. "
            "sam-altman.jsonl.gz). Required unless --setup-login is used."
        ),
    )
    parser.add_argument(
        "--headful",
        action="store_true",
        help="Use a local visible browser for debugging instead of cloud",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=DEFAULT_MAX_STEPS,
        help=f"Maximum Browser Use agent steps per person (default: {DEFAULT_MAX_STEPS})",
    )
    parser.add_argument(
        "--max-scrolls",
        type=int,
        default=DEFAULT_MAX_SCROLLS,
        help=(
            "Maximum deterministic timeline scrolls per person "
            f"(default: {DEFAULT_MAX_SCROLLS})"
        ),
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Skip posts whose canonical URL is already in the output file",
    )
    parser.add_argument(
        "--conversation-log",
        type=Path,
        default=None,
        help="Directory for Browser Use conversation logs",
    )
    parser.add_argument(
        "--llm",
        choices=["browser-use", "openai-compatible"],
        default="browser-use",
        help=(
            "Agent LLM: 'browser-use' (ChatBrowserUse, default) or "
            "'openai-compatible' (open-weights model via an OpenAI-compatible "
            "endpoint, authenticated with LLM_API_KEY or HF_TOKEN)"
        ),
    )
    parser.add_argument(
        "--extraction-mode",
        choices=["agent", "deterministic"],
        default="deterministic",
        help=(
            "Use deterministic Browser Use CDP extraction (default) or the "
            "slower LLM agent workflow."
        ),
    )
    parser.add_argument(
        "--llm-model",
        default=None,
        help=(f"Model id for --llm openai-compatible (default: {DEFAULT_OPEN_MODEL})"),
    )
    parser.add_argument(
        "--llm-base-url",
        default=None,
        help=(
            "OpenAI-compatible base URL for --llm openai-compatible "
            f"(default: {DEFAULT_OPEN_BASE_URL})"
        ),
    )
    parser.add_argument(
        "--user-data-dir",
        type=Path,
        default=None,
        help=(
            "Persistent local browser profile directory. Create it once with "
            "--setup-login, then pass it on collection runs to reuse the "
            "logged-in session (forces a local browser instead of cloud)."
        ),
    )
    parser.add_argument(
        "--setup-login",
        action="store_true",
        help=(
            "Open a visible local browser on the X login page so YOU can log "
            "in manually; the session is stored in --user-data-dir (default: "
            f"{DEFAULT_USER_DATA_DIR}) and no collection is performed."
        ),
    )
    return parser.parse_args(argv)


def build_config(args: argparse.Namespace) -> CollectorConfig:
    persons = args.persons or ["sam-altman"]
    if "all" in persons:
        if len(persons) > 1:
            raise SystemExit("--person all cannot be combined with other persons")
        if args.max_posts is None:
            raise SystemExit(
                "--person all requires an explicit --max-posts; "
                "refusing an unbounded full run"
            )
        persons = sorted(VERIFIED_PROFILES)
    # Preserve order, drop repeats.
    persons = list(dict.fromkeys(persons))

    max_posts = args.max_posts if args.max_posts is not None else DEFAULT_MAX_POSTS
    if max_posts <= 0:
        raise SystemExit("--max-posts must be a positive integer")

    try:
        start_date = date.fromisoformat(args.start_date) if args.start_date else None
        end_date = (
            date.fromisoformat(args.end_date)
            if args.end_date
            else datetime.now(timezone.utc).date()
        )
    except ValueError as exc:
        raise SystemExit(f"Invalid date: {exc}") from exc

    try:
        return CollectorConfig(
            persons=persons,
            max_posts=max_posts,
            start_date=start_date,
            end_date=end_date,
            output=args.output,
            headful=args.headful,
            max_steps=args.max_steps,
            max_scrolls=getattr(args, "max_scrolls", DEFAULT_MAX_SCROLLS),
            resume=args.resume,
            conversation_log=args.conversation_log,
            llm_provider=getattr(args, "llm", "browser-use"),
            llm_model=getattr(args, "llm_model", None),
            llm_base_url=getattr(args, "llm_base_url", None),
            user_data_dir=getattr(args, "user_data_dir", None),
            extraction_mode=getattr(args, "extraction_mode", "deterministic"),
        )
    except Exception as exc:
        raise SystemExit(str(exc)) from exc


def setup_stderr_logging() -> None:
    """Route all logging (including browser_use's) to stderr, never stdout."""
    root = logging.getLogger()
    root.handlers = []
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-8s [%(name)s] %(message)s")
    )
    root.addHandler(handler)
    root.setLevel(logging.INFO)


async def interactive_login(user_data_dir: Path) -> None:
    """Open a visible browser so the user can log in manually.

    The session (cookies) persists in user_data_dir for later collection
    runs. No agent runs and no credentials ever pass through this script.
    """
    from browser_use import Browser

    user_data_dir.mkdir(parents=True, exist_ok=True)
    browser = Browser(
        headless=False,
        user_data_dir=str(user_data_dir),
        allowed_domains=ALLOWED_DOMAINS,
    )
    await browser.start()
    try:
        await browser.new_page(LOGIN_URL)
        LOGGER.info(
            "A browser window is open at %s. Log in manually there; nothing "
            "is collected and your credentials never touch this script.",
            LOGIN_URL,
        )
        await asyncio.to_thread(
            input, "When you are fully logged in, press Enter here to save... "
        )
        LOGGER.info("Session saved to %s", user_data_dir)
    finally:
        try:
            await browser.kill()
        except Exception:  # noqa: BLE001
            LOGGER.warning("Browser cleanup failed after login setup")


def main(argv: list[str] | None = None) -> int:
    # Configure stderr logging before browser_use is imported anywhere, so its
    # setup_logging() sees existing handlers and leaves stdout untouched.
    setup_stderr_logging()
    os.environ.setdefault("ANONYMIZED_TELEMETRY", "false")
    args = parse_args(argv)
    if args.setup_login:
        asyncio.run(interactive_login(args.user_data_dir or DEFAULT_USER_DATA_DIR))
        return 0
    if args.output is None:
        raise SystemExit("--output is required (unless using --setup-login)")
    config = build_config(args)
    manifest = asyncio.run(run_collection(config))
    failed = {
        pid: reason
        for pid, reason in manifest.stop_reason_by_person.items()
        if reason
        in {
            "agent_failure",
            "handle_mismatch",
            "identity_unverified",
            "blocked",
            "validation_failure",
        }
    }
    if failed:
        LOGGER.warning("Run finished with failures: %s", failed)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
