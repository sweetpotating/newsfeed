"""Fetch and normalise feed entries into ``Article`` objects.

Feeds are fetched concurrently with a per-request timeout. Network or parse
failures for any single feed are logged and skipped — one dead feed never
blocks the digest.
"""

from __future__ import annotations

import hashlib
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import List, Optional
from urllib.parse import urlparse, urlunparse

import feedparser
import requests

from .models import Article
from .sources import Feed

log = logging.getLogger("ainews.fetcher")

_USER_AGENT = (
    "Mozilla/5.0 (compatible; AINewsDigestBot/1.0; +https://github.com/)"
)

# Query params that are pure tracking noise; stripped before hashing so the
# same article from two URLs de-dupes correctly.
_TRACKING_PREFIXES = ("utm_", "ref", "fbclid", "gclid", "mc_", "cmp")

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _clean_summary(raw: str, limit: int = 280) -> str:
    text = _TAG_RE.sub(" ", raw or "")
    text = _WS_RE.sub(" ", text).strip()
    if len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return text


def _normalize_link(link: str) -> str:
    try:
        parts = urlparse(link)
    except ValueError:
        return link.strip()
    query = "&".join(
        kv for kv in parts.query.split("&")
        if kv and not kv.lower().startswith(_TRACKING_PREFIXES)
    )
    path = parts.path.rstrip("/") or "/"
    return urlunparse((parts.scheme.lower(), parts.netloc.lower(), path,
                       "", query, ""))


def _make_uid(entry, link: str) -> str:
    basis = getattr(entry, "id", None) or _normalize_link(link)
    return hashlib.sha1(basis.encode("utf-8", "ignore")).hexdigest()[:16]


def _parse_date(entry) -> Optional[datetime]:
    for attr in ("published_parsed", "updated_parsed"):
        tm = getattr(entry, attr, None)
        if tm:
            try:
                return datetime(*tm[:6], tzinfo=timezone.utc)
            except (TypeError, ValueError):
                continue
    return None


def _entry_to_article(entry, feed: Feed) -> Optional[Article]:
    link = (getattr(entry, "link", "") or "").strip()
    title = (getattr(entry, "title", "") or "").strip()
    if not link or not title:
        return None
    summary = getattr(entry, "summary", "") or getattr(entry, "description", "")
    return Article(
        title=_WS_RE.sub(" ", title),
        link=link,
        source=feed.name,
        region=feed.region,
        published=_parse_date(entry),
        summary=_clean_summary(summary),
        uid=_make_uid(entry, link),
    )


def fetch_feed(feed: Feed, timeout: int, max_per_feed: int) -> List[Article]:
    # Fetch with requests so the timeout is actually enforced (feedparser's
    # built-in fetch has no reliable timeout), then parse the bytes.
    try:
        resp = requests.get(
            feed.url,
            timeout=timeout,
            headers={"User-Agent": _USER_AGENT, "Cache-Control": "no-cache"},
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        log.warning("Failed to fetch %s: %s", feed.name, exc)
        return []

    try:
        parsed = feedparser.parse(resp.content)
    except Exception as exc:  # feedparser is broad; never let it bubble up
        log.warning("Failed to parse %s: %s", feed.name, exc)
        return []

    if getattr(parsed, "bozo", False) and not parsed.entries:
        log.warning("No entries from %s (%s)", feed.name,
                    getattr(parsed, "bozo_exception", "unknown error"))
        return []

    articles: List[Article] = []
    for entry in parsed.entries[: max_per_feed * 3]:
        art = _entry_to_article(entry, feed)
        if art:
            articles.append(art)
    # Newest first, then cap.
    articles.sort(key=lambda a: a.sort_key, reverse=True)
    return articles[:max_per_feed]


def fetch_all(feeds: List[Feed], timeout: int, max_per_feed: int,
              workers: int = 12) -> List[Article]:
    results: List[Article] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(fetch_feed, f, timeout, max_per_feed): f for f in feeds
        }
        for fut in as_completed(futures):
            feed = futures[fut]
            try:
                results.extend(fut.result())
            except Exception as exc:
                log.warning("Worker failed for %s: %s", feed.name, exc)
    log.info("Fetched %d entries from %d feeds", len(results), len(feeds))
    return results
