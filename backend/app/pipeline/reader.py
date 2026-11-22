"""Page reading with a TinyFish circuit breaker and a direct httpx fallback."""

from __future__ import annotations

import asyncio
import html as html_module
import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx
import trafilatura
from tinyfish import TinyFish

from ..config import settings
from .discovery import is_blocked_url, normalise_url

logger = logging.getLogger(__name__)

USER_AGENT = "UnclaimedBot/1.0 (student hackathon project)"
HTTP_TIMEOUT_SECONDS = 8.0
MAX_HTTP_BYTES = 1_500_000
HTTP_CONCURRENCY = 16
HTTP_PER_HOST = 3
MIN_READABLE_CHARS = 500
LIMIT_ERROR_THRESHOLD = 2
DAILY_LIMIT_MEMO_SECONDS = 30 * 60.0
DAILY_LIMIT_MARKERS = ("daily free fetch limit", "allowance resets", "daily free")


@dataclass(frozen=True)
class Page:
    url: str
    final_url: str
    title: str
    text: str
    links: tuple[str, ...] = field(default_factory=tuple)
    depth: int = 0
    score: int = 0
    angle: str = ""
    based_on: str = ""
    round: int = 0


@dataclass(frozen=True)
class FetchBatchResult:
    pages: list[Page]
    error_count: int
    unreadable_count: int = 0
    tinyfish_pages: int = 0
    http_pages: int = 0


@dataclass(frozen=True)
class _TinyFishBatch:
    pages: list[Page]
    errors: list[str]


_client: TinyFish | None = None
_daily_limit_until = 0.0


def _memo_daily_limit() -> None:
    """Remember a daily Fetch exhaustion so later hunts skip TinyFish at once."""

    global _daily_limit_until
    _daily_limit_until = time.monotonic() + DAILY_LIMIT_MEMO_SECONDS


def _daily_limit_remembered() -> bool:
    return time.monotonic() < _daily_limit_until


def _is_daily_limit_error(message: str) -> bool:
    lowered = message.lower()
    return any(marker in lowered for marker in DAILY_LIMIT_MARKERS)


def _client_instance() -> TinyFish:
    global _client
    if _client is None:
        _client = TinyFish()
    return _client


def reading_label(url: str) -> str:
    parts = urlsplit(url)
    path = parts.path if len(parts.path) <= 90 else parts.path[:87] + "..."
    return f"Reading {(parts.hostname or 'page').removeprefix('www.')}{path or '/'}"


def _is_limit_error(message: str) -> bool:
    lowered = message.lower()
    return any(
        marker in lowered
        for marker in (
            "daily free fetch limit",
            "rate limit",
            "maximum 150 urls",
            "too many requests",
            "429",
            "allowance resets",
        )
    )


def _tinyfish_batch(urls: list[str]) -> _TinyFishBatch:
    try:
        response = _client_instance().fetch.get_contents(
            urls,
            format="markdown",
            links=True,
            ttl=0,
            per_url_timeout_ms=settings.per_url_timeout_ms,
        )
    except Exception as exc:  # noqa: BLE001 - fetch failures are counted, never fatal
        logger.warning("TinyFish fetch batch failed: %s", exc)
        return _TinyFishBatch(pages=[], errors=[str(exc).strip() or exc.__class__.__name__])

    pages: list[Page] = []
    for result in getattr(response, "results", []):
        final_url = str(getattr(result, "final_url", "") or getattr(result, "url", "") or "").strip()
        if not final_url or is_blocked_url(final_url):
            continue
        text = str(getattr(result, "text", "") or "")
        if not text:
            continue
        raw_links = getattr(result, "links", []) or []
        links = tuple(str(link).strip() for link in raw_links if str(link).strip())
        pages.append(
            Page(
                url=normalise_url(final_url),
                final_url=final_url,
                title=str(getattr(result, "title", "") or "").strip(),
                text=text,
                links=links,
            )
        )
    errors: list[str] = []
    for error in getattr(response, "errors", []) or []:
        message = str(getattr(error, "error", "") or error).strip()
        errors.append(message)
        logger.info("TinyFish fetch failed url=%s error=%s", getattr(error, "url", "?"), message)
    return _TinyFishBatch(pages=pages, errors=errors)


class _LinkParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        for name, value in attrs:
            if name.lower() != "href" or not value:
                continue
            resolved = urljoin(self.base_url, value.strip())
            parsed = urlsplit(resolved)
            if parsed.scheme in {"http", "https"} and parsed.netloc:
                self.links.append(resolved)
            break


_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)


def _html_title(body: str) -> str:
    match = _TITLE_RE.search(body)
    if match is None:
        return ""
    return " ".join(html_module.unescape(match.group(1)).split())


def _extract_markdown(body: str, final_url: str) -> str:
    try:
        extracted = trafilatura.extract(
            body,
            url=final_url,
            output_format="markdown",
            include_links=True,
            include_formatting=True,
            favor_recall=True,
        )
    except Exception as exc:  # noqa: BLE001 - malformed HTML is not fatal
        logger.info("Trafilatura failed url=%s: %s", final_url, exc)
        return ""
    return (extracted or "").strip()


class PageReader:
    """TinyFish first, then direct HTTP after two provider limit errors."""

    def __init__(self, on_limit: Callable[[], None] | None = None) -> None:
        self._on_limit = on_limit
        self._limit_notified = _daily_limit_remembered()
        self._tinyfish_disabled = _daily_limit_remembered()
        self.tinyfish_limit_errors = 0
        self.tinyfish_pages = 0
        self.http_pages = 0
        self.unreadable_pages = 0
        self._http = httpx.AsyncClient(
            follow_redirects=True,
            timeout=httpx.Timeout(HTTP_TIMEOUT_SECONDS),
            headers={
                "User-Agent": USER_AGENT,
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
            },
        )
        self._overall = asyncio.Semaphore(HTTP_CONCURRENCY)
        self._host_semaphores: dict[str, asyncio.Semaphore] = {}
        self._robots: dict[str, RobotFileParser] = {}
        self._robots_locks: dict[str, asyncio.Lock] = {}

    async def aclose(self) -> None:
        await self._http.aclose()

    def _record_limit_errors(self, messages: list[str]) -> None:
        for message in messages:
            if _is_daily_limit_error(message):
                _memo_daily_limit()
            if not _is_limit_error(message):
                continue
            self.tinyfish_limit_errors += 1
            if self.tinyfish_limit_errors >= LIMIT_ERROR_THRESHOLD and not self._tinyfish_disabled:
                self._tinyfish_disabled = True
                if not self._limit_notified:
                    self._limit_notified = True
                    if self._on_limit is not None:
                        self._on_limit()

    def _host_semaphore(self, url: str) -> asyncio.Semaphore:
        host = urlsplit(url).netloc.lower()
        semaphore = self._host_semaphores.get(host)
        if semaphore is None:
            semaphore = asyncio.Semaphore(HTTP_PER_HOST)
            self._host_semaphores[host] = semaphore
        return semaphore

    async def _robots_allowed(self, url: str) -> bool:
        parts = urlsplit(url)
        host = parts.netloc.lower()
        cached = self._robots.get(host)
        if cached is not None:
            return cached.can_fetch(USER_AGENT, url)

        lock = self._robots_locks.get(host)
        if lock is None:
            lock = asyncio.Lock()
            self._robots_locks[host] = lock
        async with lock:
            cached = self._robots.get(host)
            if cached is not None:
                return cached.can_fetch(USER_AGENT, url)
            parser = RobotFileParser()
            robots_url = f"{parts.scheme}://{host}/robots.txt"
            parser.set_url(robots_url)
            try:
                response = await self._http.get(
                    robots_url,
                    headers={
                        "User-Agent": USER_AGENT,
                        "Cache-Control": "no-cache",
                        "Pragma": "no-cache",
                    },
                )
                if response.status_code in {401, 403}:
                    parser.parse(["User-agent: *", "Disallow: /"])
                elif response.status_code >= 400:
                    parser.parse(["User-agent: *", "Allow: /"])
                else:
                    parser.parse(response.text.splitlines())
            except Exception as exc:  # noqa: BLE001 - unavailable robots.txt means allow
                logger.info("robots.txt unavailable host=%s: %s", host, exc)
                parser.parse(["User-agent: *", "Allow: /"])
            self._robots[host] = parser
            return parser.can_fetch(USER_AGENT, url)

    async def _direct_fetch(self, url: str) -> tuple[Page | None, bool]:
        """Return a page and whether the fetched body was technically unreadable."""

        if is_blocked_url(url):
            return None, False
        if not await self._robots_allowed(url):
            logger.info("robots.txt disallowed url=%s", url)
            return None, False
        async with self._overall, self._host_semaphore(url):
            try:
                async with self._http.stream(
                    "GET",
                    url,
                    headers={
                        "User-Agent": USER_AGENT,
                        "Cache-Control": "no-cache",
                        "Pragma": "no-cache",
                    },
                    timeout=httpx.Timeout(HTTP_TIMEOUT_SECONDS),
                ) as response:
                    final_url = str(response.url)
                    if response.status_code < 200 or response.status_code >= 400:
                        return None, False
                    if is_blocked_url(final_url):
                        return None, False
                    content_type = response.headers.get("content-type", "").lower()
                    if "html" not in content_type and "xhtml" not in content_type:
                        return None, True

                    chunks: list[bytes] = []
                    size = 0
                    async for chunk in response.aiter_bytes():
                        remaining = MAX_HTTP_BYTES - size
                        if remaining <= 0:
                            break
                        chunks.append(chunk[:remaining])
                        size += min(len(chunk), remaining)
                        if size >= MAX_HTTP_BYTES:
                            break
                    body = b"".join(chunks).decode(response.encoding or "utf-8", errors="replace")
                    markdown = _extract_markdown(body, final_url)
                    if len(markdown) < MIN_READABLE_CHARS:
                        return None, True
                    link_parser = _LinkParser(final_url)
                    try:
                        link_parser.feed(body)
                    except Exception as exc:  # noqa: BLE001 - links are optional
                        logger.info("Link parsing failed url=%s: %s", final_url, exc)
                    return (
                        Page(
                            url=normalise_url(final_url),
                            final_url=final_url,
                            title=_html_title(body),
                            text=markdown,
                            links=tuple(dict.fromkeys(link_parser.links)),
                        ),
                        False,
                    )
            except Exception as exc:  # noqa: BLE001 - one URL must not stop a batch
                logger.info("Direct read failed url=%s: %s", url, exc)
                return None, False

    async def fetch_urls(self, urls: list[str]) -> FetchBatchResult:
        """Read a batch with TinyFish until the breaker trips, then direct HTTP."""

        unique: list[str] = []
        seen: set[str] = set()
        for url in urls:
            normalized = normalise_url(url)
            if normalized in seen or is_blocked_url(normalized):
                continue
            seen.add(normalized)
            unique.append(normalized)
        if not unique:
            return FetchBatchResult(pages=[], error_count=0)

        pages: list[Page] = []
        by_url: set[str] = set()
        tinyfish_count = 0
        if not self._tinyfish_disabled:
            batch = await asyncio.to_thread(_tinyfish_batch, unique)
            self._record_limit_errors(batch.errors)
            for tiny_page in batch.pages:
                if tiny_page.url in by_url:
                    continue
                pages.append(tiny_page)
                by_url.add(tiny_page.url)
                tinyfish_count += 1
            self.tinyfish_pages += tinyfish_count

        missing = [url for url in unique if url not in by_url]
        unreadable = 0
        http_count = 0
        if missing:
            results = await asyncio.gather(*(self._direct_fetch(url) for url in missing))
            for direct_page, was_unreadable in results:
                if was_unreadable:
                    unreadable += 1
                if direct_page is None or direct_page.url in by_url:
                    continue
                pages.append(direct_page)
                by_url.add(direct_page.url)
                http_count += 1
            self.http_pages += http_count
            self.unreadable_pages += unreadable

        return FetchBatchResult(
            pages=pages,
            error_count=max(0, len(unique) - len(pages)),
            unreadable_count=unreadable,
            tinyfish_pages=tinyfish_count,
            http_pages=http_count,
        )
