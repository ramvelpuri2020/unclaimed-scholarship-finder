"""Search-driven candidate discovery without scholarship keyword ranking."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from tinyfish import APIError, TinyFish

from ..config import settings
from ..models import Profile
from ..threads import run_daemon
from .planner import PlannedQuery

logger = logging.getLogger(__name__)

GOVERNMENT_DOMAINS = ("canada.ca", "gc.ca", "ontario.ca", "gov.on.ca")
SOCIAL_DOMAINS = (
    "facebook.com",
    "instagram.com",
    "reddit.com",
    "youtube.com",
    "tiktok.com",
    "linkedin.com",
    "pinterest.com",
    "quora.com",
)
AGGREGATOR_DOMAINS = ("scholarshipscanada.com", "studentawards.com")
LOGIN_SEGMENTS = frozenset({"secure", "login", "log-in", "signin", "sign-in", "sso", "auth"})
TRACKING_PARAMS = frozenset({"fbclid", "gclid", "mc_cid", "mc_eid", "ref", "source"})


@dataclass(frozen=True)
class Candidate:
    url: str
    title: str
    snippet: str
    site_name: str
    query: str = ""
    angle: str = ""
    based_on: str = ""
    score: int = 0


_client: TinyFish | None = None


def _client_instance() -> TinyFish:
    global _client
    if _client is None:
        _client = TinyFish()
    return _client


def normalise_url(url: str) -> str:
    """Canonical URL used for dedupe, without tracking parameters."""

    parts = urlsplit(url.strip())
    host = (parts.hostname or "").lower().removeprefix("www.")
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in TRACKING_PARAMS
    ]
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower() or "https", host, path, urlencode(query), ""))


def _host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def is_government_url(url: str) -> bool:
    """Return true for any Canadian government page or host."""

    host = _host(url)
    if not host:
        return True
    if any(host == domain or host.endswith("." + domain) for domain in GOVERNMENT_DOMAINS):
        return True
    return host.startswith("gov.") or ".gov." in host or host.endswith(".gov")


def is_blocked_url(url: str) -> bool:
    """Return true for government, social, aggregator, PDF and login pages."""

    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or not host:
        return True
    if parsed.path.lower().endswith(".pdf"):
        return True
    if is_government_url(url):
        return True
    if any(host == domain or host.endswith("." + domain) for domain in SOCIAL_DOMAINS + AGGREGATOR_DOMAINS):
        return True
    segments = {segment.lower() for segment in parsed.path.split("/") if segment}
    if segments & LOGIN_SEGMENTS:
        return True
    lowered = parsed.path.lower()
    return "secure" in lowered or "login" in lowered or "sign-in" in lowered or "signin" in lowered


def _result_candidate(result: object, planned: PlannedQuery) -> Candidate | None:
    url = str(getattr(result, "url", "") or "").strip()
    if not url or is_blocked_url(url):
        return None
    return Candidate(
        url=normalise_url(url),
        title=str(getattr(result, "title", "") or "").strip(),
        snippet=str(getattr(result, "snippet", "") or "").strip(),
        site_name=str(getattr(result, "site_name", "") or "").strip(),
        query=planned.query,
        angle=planned.angle,
        based_on=planned.based_on,
    )


async def discover(
    queries: list[PlannedQuery],
    seen_urls: set[str],
    profile: Profile,
    limit: int | None = None,
) -> list[Candidate]:
    """Run searches concurrently and return unique candidates in result order."""

    del profile  # discovery is deliberately not profile-ranked; Gemini selects pages
    if not queries:
        return []

    semaphore = asyncio.Semaphore(settings.search_concurrency)
    client = _client_instance()

    async def run_query(planned: PlannedQuery) -> list[Candidate]:
        async with semaphore:
            try:
                response = await run_daemon(
                    client.search.query,
                    planned.query,
                    location="CA",
                )
            except APIError as exc:
                logger.warning("Search failed for %r: %s", planned.query, exc)
                return []
            except Exception as exc:  # noqa: BLE001 - one query must not stop the round
                logger.warning("Search crashed for %r: %s", planned.query, exc)
                return []
        candidates: list[Candidate] = []
        for result in getattr(response, "results", []):
            candidate = _result_candidate(result, planned)
            if candidate is not None:
                candidates.append(candidate)
        return candidates

    batches = await asyncio.gather(*(run_query(query) for query in queries), return_exceptions=True)
    merged: list[Candidate] = []
    local_seen = set(seen_urls)
    for batch in batches:
        if isinstance(batch, BaseException):
            logger.warning("Query batch failed: %s", batch)
            continue
        for candidate in batch:
            if candidate.url in local_seen:
                continue
            local_seen.add(candidate.url)
            merged.append(candidate)

    if limit is not None:
        return merged[: max(0, limit)]
    return merged
