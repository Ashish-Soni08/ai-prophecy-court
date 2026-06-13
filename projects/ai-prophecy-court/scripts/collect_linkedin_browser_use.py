"""Browser Use collector for manually verified LinkedIn profiles.

Collects publicly visible original LinkedIn posts authored by registry people
whose LinkedIn account status is ``verified_active``. Reposts, comments,
commenter profiles, media binaries, and uploads are excluded.
Output is gzip-compressed JSONL of raw envelopes (one per post, validating
against schemas/raw-envelope.schema.json) plus a sibling manifest, feeding
the existing normalization pipeline.

Usage (PowerShell):

    uv run python scripts/collect_linkedin_browser_use.py `
      --person satya-nadella `
      --max-posts 3 `
      --output raw/browser-use/linkedin/satya-nadella.jsonl.gz

The default LLM is ChatBrowserUse, which requires BROWSER_USE_API_KEY.
`--llm openai-compatible` instead drives the agent with an open-weights model
(default: MiniMaxAI/MiniMax-M3) through any OpenAI-compatible endpoint such as
the Hugging Face Inference Providers router, authenticated with LLM_API_KEY or
HF_TOKEN; without a Browser Use API key a local headless browser is used.
Optionally honours BROWSER_USE_CLOUD_PROFILE_ID for a user-authorized
authenticated LinkedIn browser profile. Operational logs go to stderr; stdout
stays clean.
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
import unicodedata
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

SCHEMA_VERSION = 1
PLATFORM = "linkedin"
COLLECTION_METHOD = "browser-use"
COLLECTOR_ID = "collect_linkedin_browser_use"
BROWSER_USE_MODEL = "bu-latest"
API_KEY_ENV = "BROWSER_USE_API_KEY"
CLOUD_PROFILE_ENV = "BROWSER_USE_CLOUD_PROFILE_ID"
LLM_API_KEY_ENV = "LLM_API_KEY"
HF_TOKEN_ENV = "HF_TOKEN"
DEFAULT_OPEN_MODEL = "MiniMaxAI/MiniMax-M3"
DEFAULT_OPEN_BASE_URL = "https://router.huggingface.co/v1"
DEFAULT_PERSON = "satya-nadella"
DEFAULT_MAX_POSTS = 3
DEFAULT_MAX_STEPS = 75
DEFAULT_MAX_SCROLLS = 2_000
DEFAULT_USER_DATA_DIR = Path("profiles/linkedin")
LOGIN_URL = "https://www.linkedin.com/login"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = PROJECT_ROOT / "pipeline" / "registry.yaml"

# LinkedIn plus its media/CDN domains only. Never widen this list at runtime.
ALLOWED_DOMAINS = [
    "linkedin.com",
    "*.linkedin.com",
    "licdn.com",
    "*.licdn.com",
]

logger = logging.getLogger("collect_linkedin_browser_use")

ACTIVITY_ID_RE = re.compile(
    r"(?:urn:li:(?:activity|share|ugcPost):|activity[-:])(\d{10,})"
)


# ---------------------------------------------------------------------------
# Pydantic models: extraction schema (Browser Use structured output)
# ---------------------------------------------------------------------------


class ExtractedRepost(BaseModel):
    """Original-post metadata when the profile owner reshared content."""

    original_author: str | None = None
    original_url: str | None = None
    original_text: str | None = None
    original_published_at: str | None = None


class ExtractedMedia(BaseModel):
    """Source media URLs and attachment metadata. Never download binaries."""

    images: list[str] = Field(default_factory=list)
    videos: list[str] = Field(default_factory=list)
    video_thumbnail: str | None = None
    video_duration_seconds: float | None = None
    documents: list[str] = Field(default_factory=list)
    document_cover_image: str | None = None
    document_page_count: int | None = None


class ExtractedEngagement(BaseModel):
    likes: int | None = None
    comments: int | None = None


class ExtractedProfileMetrics(BaseModel):
    followers: int | None = None
    connections: int | None = None
    posts: int | None = None
    articles: int | None = None


class ExtractedPost(BaseModel):
    """One visible LinkedIn activity item, exactly as seen on the page."""

    activity_id: str | None = None
    canonical_url: str | None = None
    content_type: (
        Literal["post", "repost", "article", "document", "image", "video"] | None
    ) = None
    title: str | None = None
    text: str | None = None
    text_html: str | None = None
    published_at: str | None = None
    timestamp_source: str | None = None
    raw_date_text: str | None = None
    author_name: str | None = None
    author_headline: str | None = None
    author_profile_image: str | None = None
    author_profile_url: str | None = None
    is_repost: bool | None = None
    repost: ExtractedRepost = Field(default_factory=ExtractedRepost)
    media: ExtractedMedia = Field(default_factory=ExtractedMedia)
    embedded_links: list[str] = Field(default_factory=list)
    hashtags: list[str] = Field(default_factory=list)
    tagged_people: list[str] = Field(default_factory=list)
    tagged_companies: list[str] = Field(default_factory=list)
    engagement: ExtractedEngagement = Field(default_factory=ExtractedEngagement)


class LinkedInExtraction(BaseModel):
    """Structured output returned by the Browser Use agent for one profile."""

    profile_identity_confirmed: bool = False
    profile_name_seen: str | None = None
    profile_metrics: ExtractedProfileMetrics = Field(
        default_factory=ExtractedProfileMetrics
    )
    posts: list[ExtractedPost] = Field(default_factory=list)
    access_blocked: bool = False
    blocked_reason: str | None = None
    stop_reason: str = "unknown"


# ---------------------------------------------------------------------------
# Pydantic models: output records, errors, manifest
# ---------------------------------------------------------------------------


class LinkedInRecord(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    schema_version: int = SCHEMA_VERSION
    platform: Literal["linkedin"] = PLATFORM
    person_id: str
    person_name: str
    company: str
    profile_url: str
    account_verified_manual: Literal[True] = True
    native_id: str | None = None
    canonical_url: str
    content_type: str | None = None
    title: str | None = None
    text: str | None = None
    text_html: str | None = None
    published_at: str | None = None
    author_name: str | None = None
    author_headline: str | None = None
    author_profile_image: str | None = None
    is_repost: bool | None = None
    repost: ExtractedRepost = Field(default_factory=ExtractedRepost)
    media: ExtractedMedia = Field(default_factory=ExtractedMedia)
    embedded_links: list[str] = Field(default_factory=list)
    hashtags: list[str] = Field(default_factory=list)
    tagged_people: list[str] = Field(default_factory=list)
    tagged_companies: list[str] = Field(default_factory=list)
    engagement: ExtractedEngagement = Field(default_factory=ExtractedEngagement)
    profile_metrics: ExtractedProfileMetrics = Field(
        default_factory=ExtractedProfileMetrics
    )
    extracted_at: str
    collection_method: Literal["browser-use"] = COLLECTION_METHOD
    source_fields: dict[str, Any] = Field(default_factory=dict)

    @field_validator("canonical_url")
    @classmethod
    def _canonical_url_must_be_linkedin(cls, value: str) -> str:
        if not re.match(r"^https://(?:[a-z0-9-]+\.)*linkedin\.com/", value):
            raise ValueError(f"canonical_url is not a linkedin.com URL: {value}")
        return value


class CollectorError(BaseModel):
    person_id: str
    category: Literal[
        "auth_required",
        "captcha",
        "blocked",
        "identity_mismatch",
        "navigation",
        "extraction",
        "validation",
        "runtime",
    ]
    message: str
    url: str | None = None
    occurred_at: str


class PersonRunSummary(BaseModel):
    person_id: str
    profile_url: str
    start_date: str
    end_date: str
    max_posts: int
    stop_reason: str
    new_records: int
    duplicates_skipped: int


class RunManifest(BaseModel):
    run_id: str
    platform: Literal["linkedin"] = PLATFORM
    collection_method: Literal["browser-use"] = COLLECTION_METHOD
    requested_people: list[str]
    max_posts: int
    max_steps: int
    max_scrolls: int = DEFAULT_MAX_SCROLLS
    effective_start_date: str
    effective_end_date: str
    started_at: str
    completed_at: str
    browser_use_model: str = BROWSER_USE_MODEL
    execution_mode: Literal["cloud", "local-headful", "local-headless"]
    cloud_profile_configured: bool
    visited_urls: list[str] = Field(default_factory=list)
    record_count_by_person: dict[str, int] = Field(default_factory=dict)
    duplicate_count: int = 0
    stop_reason_by_person: dict[str, str] = Field(default_factory=dict)
    person_runs: list[PersonRunSummary] = Field(default_factory=list)
    errors: list[CollectorError] = Field(default_factory=list)
    output_path: str
    output_sha256: str | None = None
    git_commit: str


class RawEnvelope(BaseModel):
    """Raw archive envelope matching schemas/raw-envelope.schema.json."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    platform: Literal["linkedin"] = PLATFORM
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


def pipeline_version() -> str:
    try:
        from pipeline import __version__

        return __version__
    except Exception:  # standalone use without the installed package
        return "unknown"


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class RegistryPerson(BaseModel):
    person_id: str
    name: str
    company: str
    profile_url: str


def load_registry(path: Path = REGISTRY_PATH) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def verified_linkedin_people(registry: dict[str, Any]) -> dict[str, RegistryPerson]:
    people: dict[str, RegistryPerson] = {}
    for person in registry["people"]:
        account = person["accounts"].get("linkedin", {})
        if account.get("status") == "verified_active" and account.get("url"):
            people[person["id"]] = RegistryPerson(
                person_id=person["id"],
                name=person["name"],
                company=person["company"],
                profile_url=account["url"],
            )
    return people


def resolve_people(
    requested: list[str], registry: dict[str, Any]
) -> list[RegistryPerson]:
    verified = verified_linkedin_people(registry)
    if requested == ["all"]:
        return list(verified.values())
    resolved: list[RegistryPerson] = []
    known_ids = {person["id"] for person in registry["people"]}
    for person_id in requested:
        if person_id not in known_ids:
            raise SystemExit(f"Unknown registry person: {person_id}")
        if person_id not in verified:
            raise SystemExit(
                f"{person_id} has no manually verified LinkedIn profile in the "
                "registry and must not be scraped"
            )
        if all(existing.person_id != person_id for existing in resolved):
            resolved.append(verified[person_id])
    return resolved


# ---------------------------------------------------------------------------
# Pure helpers: dedup, filtering, sorting
# ---------------------------------------------------------------------------


def extract_activity_id(value: str | None) -> str | None:
    if not value:
        return None
    match = ACTIVITY_ID_RE.search(value)
    return match.group(1) if match else None


def normalize_url(url: str) -> str:
    url = url.split("?", 1)[0].split("#", 1)[0]
    return url.rstrip("/")


def dedup_key(native_id: str | None, canonical_url: str) -> str:
    if native_id:
        return f"activity:{native_id}"
    return f"url:{normalize_url(canonical_url)}"


def profile_slug(profile_url: str) -> str:
    match = re.search(r"/in/([^/?#]+)", profile_url)
    return match.group(1).casefold() if match else ""


def fold_identity_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(char for char in normalized if not unicodedata.combining(char)).casefold()


def is_authored_by(post: ExtractedPost, person: RegistryPerson) -> bool:
    """True only for original posts by the verified profile owner."""
    if post.is_repost or post.content_type == "repost":
        return False
    expected_slug = profile_slug(person.profile_url)
    if post.author_profile_url:
        if profile_slug(post.author_profile_url) == expected_slug:
            return True
        return False
    if post.author_name:
        return post.author_name.strip().casefold() == person.name.strip().casefold()
    return False


def parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def timestamp_from_linkedin_activity_id(activity_id: str) -> str:
    """Decode the UTC creation millisecond embedded in a LinkedIn activity ID."""
    timestamp_ms = int(activity_id) >> 22
    return datetime.fromtimestamp(
        timestamp_ms / 1000, tz=timezone.utc
    ).isoformat(timespec="milliseconds")


def within_window(published_at: str | None, start: date, end: date) -> bool:
    """Keep undated items; never infer dates. Drop dated items outside window."""
    value = parse_iso_date(published_at)
    if value is None:
        return True
    return start <= value <= end


def sort_newest_first(records: list[LinkedInRecord]) -> list[LinkedInRecord]:
    """Dated records first, newest to oldest; undated records keep order at the end."""

    def key(record: LinkedInRecord) -> tuple[bool, str]:
        parsed = parse_iso_date(record.published_at)
        return (parsed is not None, parsed.isoformat() if parsed else "")

    return sorted(records, key=key, reverse=True)


def build_record(
    post: ExtractedPost,
    person: RegistryPerson,
    profile_metrics: ExtractedProfileMetrics,
    extracted_at: str,
) -> LinkedInRecord | None:
    canonical_url = post.canonical_url
    if not canonical_url:
        return None
    native_id = post.activity_id or extract_activity_id(canonical_url)
    return LinkedInRecord(
        person_id=person.person_id,
        person_name=person.name,
        company=person.company,
        profile_url=person.profile_url,
        native_id=native_id,
        canonical_url=canonical_url,
        content_type=post.content_type,
        title=post.title,
        text=post.text,
        text_html=post.text_html,
        published_at=post.published_at,
        author_name=post.author_name,
        author_headline=post.author_headline,
        author_profile_image=post.author_profile_image,
        is_repost=post.is_repost,
        repost=post.repost,
        media=post.media,
        embedded_links=post.embedded_links,
        hashtags=post.hashtags,
        tagged_people=post.tagged_people,
        tagged_companies=post.tagged_companies,
        engagement=post.engagement,
        profile_metrics=profile_metrics,
        extracted_at=extracted_at,
        source_fields=post.model_dump(mode="json"),
    )


def select_records(
    extraction: LinkedInExtraction,
    person: RegistryPerson,
    *,
    start: date,
    end: date,
    max_posts: int,
    existing_keys: set[str],
    extracted_at: str,
) -> tuple[list[LinkedInRecord], int]:
    """Filter to authored, in-window, deduplicated records, newest first."""
    records: list[LinkedInRecord] = []
    duplicates = 0
    seen = set(existing_keys)
    for post in extraction.posts:
        if not is_authored_by(post, person):
            logger.info("Dropping non-authored item: %s", post.canonical_url)
            continue
        if not within_window(post.published_at, start, end):
            logger.info("Dropping out-of-window item: %s", post.canonical_url)
            continue
        record = build_record(post, person, extraction.profile_metrics, extracted_at)
        if record is None:
            logger.info("Dropping item without canonical URL")
            continue
        key = dedup_key(record.native_id, record.canonical_url)
        if key in seen:
            duplicates += 1
            continue
        seen.add(key)
        records.append(record)
    records = sort_newest_first(records)[:max_posts]
    return records, duplicates


# ---------------------------------------------------------------------------
# Raw envelope (gzip JSONL) and manifest I/O
# ---------------------------------------------------------------------------


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def build_envelope(
    record: LinkedInRecord,
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
) -> tuple[list[RawEnvelope], list[LinkedInRecord]]:
    if not path.exists():
        return [], []
    envelopes: list[RawEnvelope] = []
    records: list[LinkedInRecord] = []
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                envelope = RawEnvelope.model_validate_json(line)
                records.append(LinkedInRecord.model_validate(envelope.payload))
            except Exception as exc:
                raise ValueError(
                    f"Cannot resume: invalid envelope on line {line_number} "
                    f"of {path}: {exc}"
                ) from exc
            envelopes.append(envelope)
    return envelopes, records


def existing_dedup_keys(records: list[LinkedInRecord]) -> set[str]:
    return {dedup_key(record.native_id, record.canonical_url) for record in records}


def sort_envelopes_newest_first(envelopes: list[RawEnvelope]) -> list[RawEnvelope]:
    """Dated payloads first, newest to oldest; undated keep order at the end."""

    def key(envelope: RawEnvelope) -> tuple[bool, str]:
        parsed = parse_iso_date(envelope.payload.get("published_at"))
        return (parsed is not None, parsed.isoformat() if parsed else "")

    return sorted(envelopes, key=key, reverse=True)


def write_envelopes_gz_atomic(path: Path, envelopes: list[RawEnvelope]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(path.name + f".tmp-{uuid.uuid4().hex[:8]}")
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
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_manifest(path: Path, manifest: RunManifest) -> Path:
    manifest_path = path.with_name(path.name + ".manifest.json")
    tmp_path = manifest_path.with_name(
        manifest_path.name + f".tmp-{uuid.uuid4().hex[:8]}"
    )
    tmp_path.write_text(
        json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    os.replace(tmp_path, manifest_path)
    return manifest_path


def git_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else "uncommitted"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Browser Use agent
# ---------------------------------------------------------------------------


def build_llm(
    provider: str, model: str | None = None, base_url: str | None = None
) -> Any:
    """Build the agent LLM: ChatBrowserUse (default) or an open model."""
    if provider == "browser-use":
        from browser_use import ChatBrowserUse

        return ChatBrowserUse(model=BROWSER_USE_MODEL)
    api_key = os.getenv(LLM_API_KEY_ENV) or os.getenv(HF_TOKEN_ENV)
    if not api_key:
        raise SystemExit(
            f"{LLM_API_KEY_ENV} or {HF_TOKEN_ENV} is required for "
            "--llm openai-compatible"
        )
    open_model_chat = _open_model_chat_class()
    return open_model_chat(
        model=model or DEFAULT_OPEN_MODEL,
        base_url=base_url or DEFAULT_OPEN_BASE_URL,
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


def build_task(
    person: RegistryPerson, *, max_posts: int, start: date, end: date
) -> str:
    return f"""\
You are collecting public LinkedIn posts for an auditable research dataset.
Accuracy and provenance matter more than volume. Follow these steps exactly.

1. Navigate directly to {person.profile_url}
2. Call confirm_profile_identity with expected_name="{person.name}" and
   expected_profile_slug="{profile_slug(person.profile_url)}". If the page is
   not that person's profile, stop and report it in the final output.
3. Open the profile's Activity / Posts view (for example
   {person.profile_url.rstrip("/")}/recent-activity/all/). Prefer the
   "Posts" filter so only authored items are listed, when the interface
   offers it.
4. Scroll gradually and read the visible posts. Expand "...see more" to get
   full text. Open an individual post detail page only when you need the full
   text, exact timestamp, canonical URL, attachments, or repost metadata.
5. Collect at most {max_posts} qualifying posts, newest first. Stop as soon as:
   - you have {max_posts} qualifying posts; or
   - the posts you reach were published before {start.isoformat()}; or
   - no new posts appear after 3 additional scroll attempts; or
   - access is blocked.
6. Keep only items authored or reshared by {person.name} (the profile owner).
   Exclude comments, reactions, commenter information, recommended posts,
   advertisements, "more relevant posts", and activity belonging to anyone
   else. Never use search-engine snippets.
7. Only include posts published between {start.isoformat()} and
   {end.isoformat()} when a date is visible. Record the exact visible date
   text in raw_date_text and an ISO-8601 timestamp in published_at when the
   page exposes one. If only a relative label like "2w" is visible, put it in
   raw_date_text and leave published_at null. Never guess or fabricate values;
   use null for anything you cannot see.
8. For each post fill in: activity_id (the digits from urn:li:activity:... or
   the /posts/ URL), canonical_url (a direct linkedin.com URL to the post),
   content_type (post, repost, article, document, image, or video), title,
   text, text_html only if directly available, author fields, is_repost and
   repost metadata for reshares, media URLs and attachment metadata (never
   download files), embedded_links, hashtags, tagged_people, tagged_companies,
   and visible like/comment counts.
9. Also record visible profile metrics: followers, connections, and post or
   article counts if shown.

Authentication and safety rules (mandatory):
- Never log in, create accounts, enter credentials, solve or bypass CAPTCHAs,
  or evade rate limits or access controls.
- If LinkedIn shows a login wall, CAPTCHA, authwall redirect, or blocked page
  that requires human action, stop immediately and return your final output
  with access_blocked=true and blocked_reason describing exactly what you saw.
- Stay on linkedin.com. Do not visit any other website.

Finish by returning the structured output with profile_identity_confirmed,
profile_name_seen, profile_metrics, the collected posts, access_blocked,
blocked_reason, and stop_reason (one of: max_posts_reached,
start_date_crossed, no_new_posts, access_blocked, identity_mismatch).
"""


async def collect_person_deterministic(
    person: RegistryPerson,
    *,
    user_data_dir: Path | None,
    max_posts: int,
    headful: bool,
) -> tuple[LinkedInExtraction | None, list[str], CollectorError | None]:
    """Collect authenticated activity cards directly through Browser Use CDP."""
    from browser_use import Browser

    browser_kwargs: dict[str, Any] = {
        "headless": not headful,
        "allowed_domains": list(ALLOWED_DOMAINS),
    }
    if user_data_dir:
        browser_kwargs["user_data_dir"] = str(user_data_dir)
    browser = Browser(**browser_kwargs)
    activity_url = person.profile_url.rstrip("/") + "/recent-activity/all/"
    visited = [activity_url]
    try:
        await browser.start()
        page = await browser.must_get_current_page()
        await page.goto(activity_url)
        await asyncio.sleep(8)
        identity_raw = await page.evaluate(
            """() => ({
              url: location.href,
              title: document.title,
              body: (document.body?.innerText || "").slice(0, 3000)
            })"""
        )
        identity = json.loads(identity_raw or "{}")
        current_url = identity.get("url") or ""
        body = identity.get("body") or ""
        if "/login" in current_url or "/authwall" in current_url:
            return (
                LinkedInExtraction(
                    access_blocked=True,
                    blocked_reason=f"Authenticated session redirected to {current_url}",
                    stop_reason="access_blocked",
                ),
                visited + [current_url],
                None,
            )
        confirmed = profile_slug(person.profile_url) == profile_slug(current_url)
        found: dict[str, dict[str, Any]] = {}
        for _ in range(8):
            cards_raw = await page.evaluate(
                """() => {
                  const nodes = [
                    ...document.querySelectorAll('[data-urn*="urn:li:activity:"]'),
                    ...document.querySelectorAll('[data-id*="urn:li:activity:"]'),
                    ...document.querySelectorAll(".feed-shared-update-v2"),
                    ...document.querySelectorAll('[data-view-name="feed-full-update"]')
                  ];
                  const posts = new Map();
                  for (const node of nodes) {
                    const html = node.outerHTML || "";
                    const urn = node.getAttribute("data-urn") ||
                      node.getAttribute("data-id") || html;
                    const idMatch = urn.match(/urn:li:activity:(\\d{10,})/);
                    if (!idMatch) continue;
                    const id = idMatch[1];
                    const author = [...node.querySelectorAll('a[href*="/in/"]')]
                      .find(a => !a.href.includes("/overlay/"));
                    const textNode = node.querySelector(
                      '.update-components-text, ' +
                      '.feed-shared-update-v2__description, ' +
                      '[data-test-id="main-feed-activity-card__commentary"], ' +
                      '.break-words'
                    );
                    const dateNode = node.querySelector(
                      'time, .update-components-actor__sub-description, ' +
                      '.feed-shared-actor__sub-description'
                    );
                    const images = [...node.querySelectorAll("img")]
                      .map(img => img.src)
                      .filter(src => src && src.includes("media.licdn.com"));
                    const links = [...node.querySelectorAll("a")]
                      .map(a => a.href)
                      .filter(href => href && /^https?:/.test(href));
                    const cardText = node.innerText || "";
                    const reactions = cardText.match(/([\\d,.]+)\\s+reactions?/i);
                    const comments = cardText.match(/([\\d,.]+)\\s+comments?/i);
                    posts.set(id, {
                      activity_id: id,
                      canonical_url: `https://www.linkedin.com/feed/update/urn:li:activity:${id}/`,
                      text: textNode?.innerText?.trim()
                        .replace(/\\n…more$/i, "")
                        .replace(/\\n\\.\\.\\.more$/i, "") || null,
                      raw_date_text: dateNode?.innerText?.trim() || null,
                      author_name: author?.innerText?.trim() || null,
                      author_profile_url: author?.href || null,
                      is_repost: /reposted this/i.test(cardText),
                      images: [...new Set(images)],
                      embedded_links: [...new Set(links)],
                      likes: reactions ? Number(reactions[1].replace(/[,\\.]/g, "")) : null,
                      comments: comments ? Number(comments[1].replace(/[,\\.]/g, "")) : null
                    });
                  }
                  return [...posts.values()];
                }"""
            )
            for item in json.loads(cards_raw or "[]"):
                found[item["activity_id"]] = item
            if len(found) >= max_posts:
                break
            await page.evaluate(
                """() => { window.scrollBy(0, Math.max(window.innerHeight * 1.5, 1200)); return window.scrollY; }"""
            )
            await asyncio.sleep(3)

        posts: list[ExtractedPost] = []
        for item in sorted(found.values(), key=lambda row: int(row["activity_id"]), reverse=True):
            if len(posts) >= max_posts:
                break
            author_url = item.get("author_profile_url")
            author_name = item.get("author_name")
            if author_url and profile_slug(author_url) != profile_slug(person.profile_url):
                continue
            if not author_url and (
                not author_name
                or author_name.strip().casefold() != person.name.strip().casefold()
            ):
                continue
            if not item.get("text") and not item.get("images"):
                continue
            posts.append(
                ExtractedPost(
                    activity_id=item["activity_id"],
                    canonical_url=item["canonical_url"],
                    content_type="repost" if item.get("is_repost") else "post",
                    text=item.get("text"),
                    published_at=timestamp_from_linkedin_activity_id(
                        item["activity_id"]
                    ),
                    timestamp_source="linkedin_activity_id",
                    raw_date_text=item.get("raw_date_text"),
                    author_name=person.name,
                    author_profile_url=person.profile_url,
                    is_repost=bool(item.get("is_repost")),
                    media=ExtractedMedia(images=item.get("images") or []),
                    embedded_links=item.get("embedded_links") or [],
                    engagement=ExtractedEngagement(
                        likes=item.get("likes"),
                        comments=item.get("comments"),
                    ),
                )
            )
        return (
            LinkedInExtraction(
                profile_identity_confirmed=confirmed,
                profile_name_seen=person.name if confirmed else None,
                posts=posts,
                stop_reason=(
                    "max_posts_reached"
                    if len(posts) >= max_posts
                    else "no_new_posts"
                ),
            ),
            visited + ([current_url] if current_url else []),
            None,
        )
    except Exception as exc:
        logger.exception("Deterministic LinkedIn run failed for %s", person.person_id)
        return (
            None,
            visited,
            CollectorError(
                person_id=person.person_id,
                category="runtime",
                message=str(exc)[:1000],
                url=activity_url,
                occurred_at=utc_now(),
            ),
        )
    finally:
        try:
            await browser.kill()
        except Exception:
            logger.warning("Browser cleanup failed for %s", person.person_id)


def decode_linkedin_page_result(raw: Any) -> Any:
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw
    return raw


async def evaluate_linkedin_page(page: Any, script: str) -> Any:
    return decode_linkedin_page_result(await page.evaluate(script))


async def dismiss_linkedin_consent(page: Any) -> str | None:
    result = await evaluate_linkedin_page(
        page,
        """() => {
          const labels = [
            "Reject non-essential",
            "Reject non-essential cookies",
            "Accept cookies",
            "Accept all"
          ];
          const nodes = [...document.querySelectorAll("button, [role='button']")];
          for (const label of labels) {
            const node = nodes.find(item =>
              (item.innerText || item.textContent || "").trim() === label
            );
            if (node) {
              node.click();
              return label;
            }
          }
          return null;
        }""",
    )
    if isinstance(result, str) and result:
        logger.info("Dismissed LinkedIn consent with: %s", result)
        await asyncio.sleep(2)
        return result
    return None


async def wait_for_linkedin_activity_v2(
    page: Any, timeout_seconds: int = 30
) -> dict[str, Any]:
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    last_state: dict[str, Any] = {}
    while asyncio.get_running_loop().time() < deadline:
        await dismiss_linkedin_consent(page)
        state = await evaluate_linkedin_page(
            page,
            """() => ({
              url: location.href,
              title: document.title,
              body: (document.body?.innerText || "").slice(0, 600),
              activities: document.querySelectorAll(
                '[data-urn*="urn:li:activity:"], ' +
                '[data-id*="urn:li:activity:"], ' +
                '.feed-shared-update-v2, ' +
                '[data-view-name="feed-full-update"]'
              ).length
            })""",
        )
        if isinstance(state, dict):
            last_state = state
            url = str(state.get("url") or "")
            body = str(state.get("body") or "").lower()
            if "/login" in url or "/authwall" in url:
                raise PermissionError(f"LinkedIn redirected to {url}")
            if "captcha" in body or "security verification" in body:
                raise PermissionError("LinkedIn displayed a verification challenge")
            if state.get("activities", 0) > 0:
                return state
        await asyncio.sleep(1)
    raise RuntimeError(f"LinkedIn activity feed did not hydrate: {last_state}")


async def extract_linkedin_cards_v2(page: Any) -> list[dict[str, Any]]:
    result = await evaluate_linkedin_page(
        page,
        """() => {
          const nodes = [
            ...document.querySelectorAll('[data-urn*="urn:li:activity:"]'),
            ...document.querySelectorAll('[data-id*="urn:li:activity:"]'),
            ...document.querySelectorAll(".feed-shared-update-v2"),
            ...document.querySelectorAll('[data-view-name="feed-full-update"]')
          ];
          const posts = new Map();
          for (const node of nodes) {
            const html = node.outerHTML || "";
            const urn = node.getAttribute("data-urn") ||
              node.getAttribute("data-id") || html;
            const idMatch = urn.match(/urn:li:activity:(\\d{10,})/);
            if (!idMatch) continue;
            const id = idMatch[1];
            const author = [...node.querySelectorAll('a[href*="/in/"]')]
              .find(a => !a.href.includes("/overlay/"));
            const textNode = node.querySelector(
              '.update-components-text, ' +
              '.feed-shared-update-v2__description, ' +
              '[data-test-id="main-feed-activity-card__commentary"], ' +
              '.break-words'
            );
            const dateNode = node.querySelector(
              'time, .update-components-actor__sub-description, ' +
              '.feed-shared-actor__sub-description'
            );
            const images = [...node.querySelectorAll("img")]
              .map(img => img.src)
              .filter(src => src && src.includes("media.licdn.com"));
            const videos = [...node.querySelectorAll("video")]
              .map(video => video.src || video.poster)
              .filter(Boolean);
            const documents = [...node.querySelectorAll('a[href*="/document/"]')]
              .map(a => a.href)
              .filter(Boolean);
            const links = [...node.querySelectorAll("a")]
              .map(a => a.href)
              .filter(href => href && /^https?:/.test(href));
            const cardText = node.innerText || "";
            const reactions = cardText.match(/([\\d,.]+)\\s+reactions?/i);
            const comments = cardText.match(/([\\d,.]+)\\s+comments?/i);
            const text = textNode?.innerText?.trim() || null;
            posts.set(id, {
              activity_id: id,
              canonical_url: `https://www.linkedin.com/feed/update/urn:li:activity:${id}/`,
              text,
              raw_date_text: dateNode?.innerText?.trim() || null,
              author_name: author?.innerText?.trim() || null,
              author_profile_url: author?.href || null,
              is_repost: /reposted this/i.test(cardText),
              pinned: /(^|\\n)pinned(\\n|$)/i.test(cardText),
              images: [...new Set(images)],
              videos: [...new Set(videos)],
              documents: [...new Set(documents)],
              embedded_links: [...new Set(links)],
              hashtags: [...new Set((text?.match(/#[A-Za-z0-9_]+/g) || []))],
              likes: reactions ? Number(reactions[1].replace(/[,\\.]/g, "")) : null,
              comments: comments ? Number(comments[1].replace(/[,\\.]/g, "")) : null
            });
          }
          return [...posts.values()];
        }""",
    )
    return result if isinstance(result, list) else []


async def advance_linkedin_activity_v2(page: Any) -> dict[str, Any]:
    result = await evaluate_linkedin_page(
        page,
        """() => {
          const cards = [
            ...document.querySelectorAll('[data-urn*="urn:li:activity:"]'),
            ...document.querySelectorAll('[data-id*="urn:li:activity:"]'),
            ...document.querySelectorAll(".feed-shared-update-v2"),
            ...document.querySelectorAll('[data-view-name="feed-full-update"]')
          ];
          const last = cards.at(-1);
          const before = window.scrollY;
          if (last) last.scrollIntoView({block: "end", behavior: "instant"});
          window.scrollBy({top: Math.max(window.innerHeight, 1000), behavior: "instant"});
          return {
            before,
            after: window.scrollY,
            cards: cards.length,
            documentHeight: document.documentElement.scrollHeight
          };
        }""",
    )
    return result if isinstance(result, dict) else {}


async def compact_linkedin_activity_v2(page: Any) -> int:
    """Replace old off-screen cards with fixed-height placeholders."""
    result = await evaluate_linkedin_page(
        page,
        """() => {
          const selector = [
            '[data-urn*="urn:li:activity:"]',
            '[data-id*="urn:li:activity:"]',
            ".feed-shared-update-v2",
            '[data-view-name="feed-full-update"]'
          ].join(",");
          const nodes = [...document.querySelectorAll(selector)]
            .filter(node => !node.parentElement?.closest(selector));
          let compacted = 0;
          for (const node of nodes) {
            if (node.dataset.codexCompacted === "true") continue;
            const rect = node.getBoundingClientRect();
            if (rect.bottom >= -3 * window.innerHeight) continue;
            const html = node.outerHTML || "";
            const urn = node.getAttribute("data-urn") ||
              node.getAttribute("data-id") || html;
            const idMatch = urn.match(/urn:li:activity:(\\d{10,})/);
            if (!idMatch) continue;
            const height = Math.max(Math.ceil(rect.height), 1);
            node.dataset.codexCompacted = "true";
            node.dataset.urn = `urn:li:activity:${idMatch[1]}`;
            node.style.height = `${height}px`;
            node.style.minHeight = `${height}px`;
            node.style.contain = "strict";
            node.replaceChildren();
            compacted += 1;
          }
          return compacted;
        }""",
    )
    return int(result) if isinstance(result, (int, float)) else 0


def build_deterministic_posts_v2(
    found: dict[str, dict[str, Any]],
    person: RegistryPerson,
    max_posts: int,
) -> list[ExtractedPost]:
    posts: list[ExtractedPost] = []
    for item in sorted(
        found.values(), key=lambda row: int(row["activity_id"]), reverse=True
    ):
        if len(posts) >= max_posts:
            break
        author_url = item.get("author_profile_url")
        author_name = item.get("author_name")
        if author_url and profile_slug(author_url) != profile_slug(person.profile_url):
            continue
        if not author_url and (
            not author_name
            or fold_identity_text(author_name.strip())
            != fold_identity_text(person.name.strip())
        ):
            continue
        if not item.get("text") and not item.get("images"):
            continue
        posts.append(
            ExtractedPost(
                activity_id=item["activity_id"],
                canonical_url=item["canonical_url"],
                content_type="post",
                text=item.get("text"),
                published_at=timestamp_from_linkedin_activity_id(item["activity_id"]),
                timestamp_source="linkedin_activity_id",
                raw_date_text=item.get("raw_date_text"),
                author_name=person.name,
                author_profile_url=person.profile_url,
                is_repost=False,
                media=ExtractedMedia(
                    images=item.get("images") or [],
                    videos=item.get("videos") or [],
                    documents=item.get("documents") or [],
                ),
                embedded_links=item.get("embedded_links") or [],
                hashtags=item.get("hashtags") or [],
                engagement=ExtractedEngagement(
                    likes=item.get("likes"),
                    comments=item.get("comments"),
                ),
            )
        )
    return posts


async def collect_person_deterministic_v2(
    person: RegistryPerson,
    *,
    user_data_dir: Path | None,
    max_posts: int,
    max_scrolls: int,
    start: date,
    end: date,
    headful: bool,
) -> tuple[LinkedInExtraction | None, list[str], CollectorError | None]:
    """Collect original authenticated posts through deterministic Browser Use CDP."""
    from browser_use import Browser

    browser_kwargs: dict[str, Any] = {
        "headless": not headful,
        "allowed_domains": list(ALLOWED_DOMAINS),
    }
    if user_data_dir:
        browser_kwargs["user_data_dir"] = str(user_data_dir)
    browser = Browser(**browser_kwargs)
    activity_url = person.profile_url.rstrip("/") + "/recent-activity/all/"
    visited = [activity_url]
    found: dict[str, dict[str, Any]] = {}
    confirmed = False
    current_url = ""
    try:
        await browser.start()
        page = await browser.must_get_current_page()
        await page.goto(activity_url)
        identity = await wait_for_linkedin_activity_v2(page)
        current_url = identity.get("url") or ""
        confirmed = profile_slug(person.profile_url) == profile_slug(current_url)
        seen_activity_ids: set[str] = set()
        stagnant_scrolls = 0
        crossed_start = False
        scrolls = 0

        while len(found) < max_posts and scrolls <= max_scrolls:
            before_seen = len(seen_activity_ids)
            for item in await extract_linkedin_cards_v2(page):
                seen_activity_ids.add(item["activity_id"])
                published = parse_iso_date(
                    timestamp_from_linkedin_activity_id(item["activity_id"])
                )
                if published and published < start:
                    if not item.get("pinned"):
                        crossed_start = True
                    continue
                if published and published > end:
                    continue
                if item.get("is_repost"):
                    continue
                existing = found.get(item["activity_id"])
                if existing is None or item.get("text") or item.get("images"):
                    found[item["activity_id"]] = item
            if len(found) >= max_posts or crossed_start or scrolls == max_scrolls:
                break
            state = await advance_linkedin_activity_v2(page)
            scrolls += 1
            if scrolls % 10 == 0:
                compacted = await compact_linkedin_activity_v2(page)
                if compacted:
                    logger.info(
                        "%s: compacted %s old activity cards",
                        person.person_id,
                        compacted,
                    )
            await asyncio.sleep(3)
            stagnant_scrolls = (
                stagnant_scrolls + 1
                if len(seen_activity_ids) == before_seen
                else 0
            )
            logger.info(
                "%s: deterministic scroll %s total_original_posts=%s position=%s",
                person.person_id,
                scrolls,
                len(found),
                state.get("after"),
            )
            if stagnant_scrolls >= 3:
                break

        posts = build_deterministic_posts_v2(found, person, max_posts)
        return (
            LinkedInExtraction(
                profile_identity_confirmed=confirmed,
                profile_name_seen=person.name if confirmed else None,
                posts=posts,
                stop_reason=(
                    "start_date_crossed"
                    if crossed_start
                    else (
                        "max_posts_reached"
                        if len(posts) >= max_posts
                        else (
                            "max_scrolls_reached"
                            if scrolls >= max_scrolls
                            else "no_new_posts"
                        )
                    )
                ),
            ),
            visited + ([current_url] if current_url else []),
            None,
        )
    except PermissionError as exc:
        return (
            LinkedInExtraction(
                access_blocked=True,
                blocked_reason=str(exc),
                stop_reason="access_blocked",
            ),
            visited,
            None,
        )
    except Exception as exc:
        logger.exception("Deterministic LinkedIn run failed for %s", person.person_id)
        partial_posts = (
            build_deterministic_posts_v2(found, person, max_posts)
            if found and confirmed
            else []
        )
        return (
            (
                LinkedInExtraction(
                    profile_identity_confirmed=True,
                    profile_name_seen=person.name,
                    posts=partial_posts,
                    stop_reason="runtime_partial",
                )
                if partial_posts
                else None
            ),
            visited + ([current_url] if current_url else []),
            CollectorError(
                person_id=person.person_id,
                category="runtime",
                message=str(exc)[:1000],
                url=activity_url,
                occurred_at=utc_now(),
            ),
        )
    finally:
        try:
            await browser.kill()
        except Exception:
            logger.warning("Browser cleanup failed for %s", person.person_id)


async def collect_person(
    person: RegistryPerson,
    *,
    llm: Any,
    use_cloud_browser: bool,
    user_data_dir: Path | None,
    max_posts: int,
    start: date,
    end: date,
    max_steps: int,
    headful: bool,
    cloud_profile_id: str | None,
    conversation_log: Path | None,
) -> tuple[LinkedInExtraction | None, list[str], CollectorError | None]:
    """Run one bounded Browser Use collection for a single verified profile."""
    from browser_use import ActionResult, Agent, Browser, Tools
    from browser_use.browser import BrowserSession

    tools = Tools()

    async def confirm_profile_identity(
        expected_name: str,
        expected_profile_slug: str,
        browser_session: BrowserSession,
    ) -> ActionResult:
        current_url = await browser_session.get_current_page_url()
        page_title = await browser_session.get_current_page_title()
        url_matches = profile_slug(current_url) == expected_profile_slug.casefold()
        content = json.dumps(
            {
                "current_url": current_url,
                "page_title": page_title,
                "expected_name": expected_name,
                "expected_profile_slug": expected_profile_slug,
                "url_matches": url_matches,
            },
            ensure_ascii=False,
        )
        return ActionResult(
            extracted_content=content,
            long_term_memory=(
                f"Identity check on {current_url}: url_matches={url_matches}"
            ),
        )

    # `from __future__ import annotations` leaves these as strings, which the
    # tools registry cannot match against its injected browser_session type;
    # restore real classes before registering the action.
    confirm_profile_identity.__annotations__.update(
        {
            "expected_name": str,
            "expected_profile_slug": str,
            "browser_session": BrowserSession,
            "return": ActionResult,
        }
    )
    tools.action(
        description=(
            "Confirm that the currently open LinkedIn page is the expected "
            "person's profile. Returns the current URL, page title, and "
            "whether the URL slug matches."
        )
    )(confirm_profile_identity)

    if headful:
        local_kwargs: dict[str, Any] = {
            "headless": False,
            "allowed_domains": list(ALLOWED_DOMAINS),
        }
        if user_data_dir:
            local_kwargs["user_data_dir"] = str(user_data_dir)
        browser = Browser(**local_kwargs)
        logger.info("Using local headful browser for %s", person.person_id)
    elif use_cloud_browser:
        browser_kwargs: dict[str, Any] = {
            "use_cloud": True,
            "allowed_domains": list(ALLOWED_DOMAINS),
        }
        if cloud_profile_id:
            browser_kwargs["cloud_profile_id"] = cloud_profile_id
        browser = Browser(**browser_kwargs)
        logger.info(
            "Using Browser Use cloud browser for %s (profile configured: %s)",
            person.person_id,
            bool(cloud_profile_id),
        )
    else:
        local_kwargs = {
            "headless": True,
            "allowed_domains": list(ALLOWED_DOMAINS),
        }
        if user_data_dir:
            # Persistent local profile (see --setup-login): reuses a session
            # the user logged into manually; never holds raw credentials.
            local_kwargs["user_data_dir"] = str(user_data_dir)
        browser = Browser(**local_kwargs)
        logger.info(
            "Using local headless browser for %s (persistent profile: %s)",
            person.person_id,
            bool(user_data_dir),
        )

    agent = Agent(
        task=build_task(person, max_posts=max_posts, start=start, end=end),
        llm=llm,
        browser=browser,
        tools=tools,
        output_model_schema=LinkedInExtraction,
        use_vision="auto",
        max_failures=3,
        step_timeout=120,
        llm_timeout=90,
        save_conversation_path=str(conversation_log) if conversation_log else None,
        calculate_cost=False,
    )

    visited: list[str] = []
    try:
        history = await agent.run(max_steps=max_steps)
        visited = [url for url in history.urls() if url]
        extraction = history.structured_output
        if extraction is None:
            final = history.final_result()
            return (
                None,
                visited,
                CollectorError(
                    person_id=person.person_id,
                    category="extraction",
                    message=(
                        "Agent finished without structured output; final result: "
                        f"{(final or '')[:500]}"
                    ),
                    url=visited[-1] if visited else person.profile_url,
                    occurred_at=utc_now(),
                ),
            )
        return extraction, visited, None
    except Exception as exc:  # noqa: BLE001 - one profile must not kill the run
        logger.exception("Browser Use run failed for %s", person.person_id)
        return (
            None,
            visited,
            CollectorError(
                person_id=person.person_id,
                category="runtime",
                message=str(exc)[:1000],
                url=visited[-1] if visited else person.profile_url,
                occurred_at=utc_now(),
            ),
        )
    finally:
        try:
            await browser.kill()
        except Exception:  # noqa: BLE001 - best-effort cleanup
            logger.debug("Browser cleanup failed", exc_info=True)


def classify_blocked(
    extraction: LinkedInExtraction, person_id: str, url: str | None
) -> CollectorError:
    reason = (extraction.blocked_reason or "").casefold()
    if "captcha" in reason or "challenge" in reason:
        category: str = "captcha"
    elif "login" in reason or "auth" in reason or "sign in" in reason:
        category = "auth_required"
    else:
        category = "blocked"
    return CollectorError(
        person_id=person_id,
        category=category,  # type: ignore[arg-type]
        message=extraction.blocked_reason or "Access blocked",
        url=url,
        occurred_at=utc_now(),
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect LinkedIn posts for verified registry people via Browser Use.",
    )
    parser.add_argument(
        "--person",
        action="append",
        default=None,
        help='Registry person ID; repeatable, or "all" for every verified profile.',
    )
    parser.add_argument(
        "--max-posts",
        type=int,
        default=None,
        help=f"Maximum posts per person (positive integer, default {DEFAULT_MAX_POSTS}).",
    )
    parser.add_argument(
        "--start-date", default=None, help="Override start date (YYYY-MM-DD)."
    )
    parser.add_argument(
        "--end-date",
        default=None,
        help="Override end date (YYYY-MM-DD, default today UTC).",
    )
    parser.add_argument(
        "--output",
        default=None,
        help=(
            "Raw-envelope destination path (gzip JSONL, e.g. "
            "satya-nadella.jsonl.gz). Required unless --setup-login is used."
        ),
    )
    parser.add_argument(
        "--headful", action="store_true", help="Local visible browser for debugging."
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=DEFAULT_MAX_STEPS,
        help=f"Bounded Browser Use agent steps per person (default {DEFAULT_MAX_STEPS}).",
    )
    parser.add_argument(
        "--max-scrolls",
        type=int,
        default=DEFAULT_MAX_SCROLLS,
        help=(
            "Maximum deterministic activity-feed scrolls per person "
            f"(default {DEFAULT_MAX_SCROLLS})."
        ),
    )
    parser.add_argument(
        "--extraction-mode",
        choices=["agent", "deterministic"],
        default="deterministic",
        help=(
            "Use deterministic authenticated activity-card extraction "
            "(default) or the slower LLM agent."
        ),
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Skip canonical URLs already present in the output file.",
    )
    parser.add_argument(
        "--conversation-log",
        default=None,
        help="Optional Browser Use conversation log path.",
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
        "--llm-model",
        default=None,
        help=f"Model id for --llm openai-compatible (default: {DEFAULT_OPEN_MODEL}).",
    )
    parser.add_argument(
        "--llm-base-url",
        default=None,
        help=(
            "OpenAI-compatible base URL for --llm openai-compatible "
            f"(default: {DEFAULT_OPEN_BASE_URL})."
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
            "Open a visible local browser on the LinkedIn login page so YOU "
            "can log in manually; the session is stored in --user-data-dir "
            f"(default: {DEFAULT_USER_DATA_DIR}) and no collection is "
            "performed."
        ),
    )
    args = parser.parse_args(argv)

    explicit_max_posts = args.max_posts is not None
    if args.max_posts is None:
        args.max_posts = DEFAULT_MAX_POSTS
    if args.max_posts < 1:
        parser.error("--max-posts must be a positive integer")
    if args.max_steps < 1:
        parser.error("--max-steps must be a positive integer")
    if args.max_scrolls < 1:
        parser.error("--max-scrolls must be a positive integer")

    if args.person is None:
        args.person = [DEFAULT_PERSON]
    if "all" in args.person:
        if args.person != ["all"]:
            parser.error("--person all cannot be combined with individual person IDs")
        if not explicit_max_posts:
            parser.error(
                "A full run requires explicit --person all and an explicit --max-posts"
            )

    for label, value in (
        ("--start-date", args.start_date),
        ("--end-date", args.end_date),
    ):
        if value is not None:
            try:
                date.fromisoformat(value)
            except ValueError:
                parser.error(f"{label} must use YYYY-MM-DD")
    return args


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
        allowed_domains=list(ALLOWED_DOMAINS),
    )
    await browser.start()
    try:
        await browser.new_page(LOGIN_URL)
        logger.info(
            "A browser window is open at %s. Log in manually there; nothing "
            "is collected and your credentials never touch this script.",
            LOGIN_URL,
        )
        await asyncio.to_thread(
            input, "When you are fully logged in, press Enter here to save... "
        )
        logger.info("Session saved to %s", user_data_dir)
    finally:
        try:
            await browser.kill()
        except Exception:  # noqa: BLE001
            logger.warning("Browser cleanup failed after login setup")


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    args = parse_args(argv)

    if args.setup_login:
        asyncio.run(interactive_login(args.user_data_dir or DEFAULT_USER_DATA_DIR))
        return 0
    if args.output is None:
        logger.error("--output is required (unless using --setup-login)")
        return 2
    if (
        args.extraction_mode == "agent"
        and args.llm == "browser-use"
        and not os.getenv(API_KEY_ENV)
    ):
        logger.error("%s is required for the default --llm browser-use", API_KEY_ENV)
        return 2
    llm = (
        build_llm(args.llm, args.llm_model, args.llm_base_url)
        if args.extraction_mode == "agent"
        else None
    )
    # Cloud browser is the production default; a local browser is used when
    # there is no Browser Use API key (possible only in openai-compatible
    # mode), in --headful debugging, or with a persistent --user-data-dir.
    use_cloud_browser = (
        not args.headful and args.user_data_dir is None and bool(os.getenv(API_KEY_ENV))
    )
    if not use_cloud_browser and not args.headful and not os.getenv(API_KEY_ENV):
        logger.warning(
            "%s is not set; using a local headless browser instead of "
            "Browser Use Cloud",
            API_KEY_ENV,
        )
    cloud_profile_id = os.getenv(CLOUD_PROFILE_ENV) or None

    registry = load_registry()
    people = resolve_people(args.person, registry)
    if not people:
        logger.error("No verified LinkedIn profiles resolved; nothing to do")
        return 2

    start = date.fromisoformat(args.start_date or registry["collection"]["start_date"])
    end = (
        date.fromisoformat(args.end_date)
        if args.end_date
        else datetime.now(timezone.utc).date()
    )
    if start > end:
        logger.error("Start date %s is after end date %s", start, end)
        return 2

    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = Path.cwd() / output_path
    conversation_log = Path(args.conversation_log) if args.conversation_log else None

    existing_envelopes: list[RawEnvelope] = []
    existing_records: list[LinkedInRecord] = []
    if args.resume:
        existing_envelopes, existing_records = load_existing_envelopes(output_path)
    if not args.resume and output_path.exists():
        logger.warning(
            "Output %s exists and --resume is not set; it will be replaced",
            output_path,
        )
    known_keys = existing_dedup_keys(existing_records)
    logger.info(
        "Run starts: people=%s max_posts=%s window=%s..%s resume=%s (%s existing records)",
        [p.person_id for p in people],
        args.max_posts,
        start,
        end,
        args.resume,
        len(existing_records),
    )

    run_id = f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:8]}"
    started_at = utc_now()
    new_envelopes: list[RawEnvelope] = []
    visited_urls: list[str] = []
    errors: list[CollectorError] = []
    record_counts: dict[str, int] = {}
    stop_reasons: dict[str, str] = {}
    person_runs: list[PersonRunSummary] = []
    duplicate_count = 0

    for person in people:
        requested_at = utc_now()
        if args.extraction_mode == "deterministic":
            extraction, visited, error = asyncio.run(
                collect_person_deterministic_v2(
                    person,
                    user_data_dir=args.user_data_dir,
                    max_posts=args.max_posts,
                    max_scrolls=args.max_scrolls,
                    start=start,
                    end=end,
                    headful=args.headful,
                )
            )
        else:
            extraction, visited, error = asyncio.run(
                collect_person(
                    person,
                    llm=llm,
                    use_cloud_browser=use_cloud_browser,
                    user_data_dir=args.user_data_dir,
                    max_posts=args.max_posts,
                    start=start,
                    end=end,
                    max_steps=args.max_steps,
                    headful=args.headful,
                    cloud_profile_id=cloud_profile_id,
                    conversation_log=conversation_log,
                )
            )
        completed_at = utc_now()
        visited_urls.extend(visited)
        new_records: list[LinkedInRecord] = []
        duplicates = 0
        stop_reason = "error"
        if error is not None:
            errors.append(error)
        if extraction is not None:
            # Fail closed: a blocked run or unconfirmed identity discards the
            # whole extraction batch. select_records is never called and the
            # deduplication state is never mutated for that person.
            if extraction.access_blocked:
                blocked = classify_blocked(
                    extraction, person.person_id, visited[-1] if visited else None
                )
                errors.append(blocked)
                stop_reason = "access_blocked"
                logger.warning(
                    "Access blocked for %s: discarding %s extracted posts (%s)",
                    person.person_id,
                    len(extraction.posts),
                    blocked.message,
                )
            elif not extraction.profile_identity_confirmed:
                errors.append(
                    CollectorError(
                        person_id=person.person_id,
                        category="identity_mismatch",
                        message=(
                            "Agent did not confirm profile identity; seen name: "
                            f"{extraction.profile_name_seen!r}; discarding "
                            f"{len(extraction.posts)} extracted posts"
                        ),
                        url=visited[-1] if visited else person.profile_url,
                        occurred_at=utc_now(),
                    )
                )
                stop_reason = "identity_mismatch"
            else:
                stop_reason = extraction.stop_reason
                extracted_at = utc_now()
                new_records, duplicates = select_records(
                    extraction,
                    person,
                    start=start,
                    end=end,
                    max_posts=args.max_posts,
                    existing_keys=known_keys,
                    extracted_at=extracted_at,
                )
                known_keys.update(
                    dedup_key(record.native_id, record.canonical_url)
                    for record in new_records
                )
        new_envelopes.extend(
            build_envelope(
                record,
                run_id=run_id,
                requested_at=requested_at,
                completed_at=completed_at,
            )
            for record in new_records
        )
        if new_records:
            checkpoint = sort_envelopes_newest_first(
                existing_envelopes + new_envelopes
            )
            checkpoint_sha = write_envelopes_gz_atomic(output_path, checkpoint)
            logger.info(
                "%s: checkpointed %s total envelopes (sha256=%s)",
                person.person_id,
                len(checkpoint),
                checkpoint_sha,
            )
        duplicate_count += duplicates
        record_counts[person.person_id] = len(new_records)
        stop_reasons[person.person_id] = stop_reason
        person_runs.append(
            PersonRunSummary(
                person_id=person.person_id,
                profile_url=person.profile_url,
                start_date=start.isoformat(),
                end_date=end.isoformat(),
                max_posts=args.max_posts,
                stop_reason=stop_reason,
                new_records=len(new_records),
                duplicates_skipped=duplicates,
            )
        )
        logger.info(
            "%s: %s new records, %s duplicates skipped, stop_reason=%s",
            person.person_id,
            len(new_records),
            duplicates,
            stop_reason,
        )

    final_envelopes = sort_envelopes_newest_first(existing_envelopes + new_envelopes)
    output_sha256 = write_envelopes_gz_atomic(output_path, final_envelopes)
    manifest = RunManifest(
        run_id=run_id,
        requested_people=[p.person_id for p in people],
        max_posts=args.max_posts,
        max_steps=args.max_steps,
        max_scrolls=args.max_scrolls,
        effective_start_date=start.isoformat(),
        effective_end_date=end.isoformat(),
        started_at=started_at,
        completed_at=utc_now(),
        browser_use_model=(
            "deterministic-cdp"
            if args.extraction_mode == "deterministic"
            else getattr(llm, "model", type(llm).__name__)
        ),
        execution_mode=(
            "local-headful"
            if args.headful
            else ("cloud" if use_cloud_browser else "local-headless")
        ),
        cloud_profile_configured=bool(cloud_profile_id),
        visited_urls=visited_urls,
        record_count_by_person=record_counts,
        duplicate_count=duplicate_count,
        stop_reason_by_person=stop_reasons,
        person_runs=person_runs,
        errors=errors,
        output_path=str(output_path),
        output_sha256=output_sha256,
        git_commit=git_commit(),
    )
    manifest_path = write_manifest(output_path, manifest)
    logger.info("Wrote %s raw envelopes to %s", len(final_envelopes), output_path)
    logger.info("Wrote manifest to %s", manifest_path)
    if errors:
        logger.warning("Run completed with %s structured errors", len(errors))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
