"""Fetch and normalise feed entries into ``Article`` objects.

Feeds are fetched concurrently with a per-request timeout. Network or parse
failures for any single feed are logged and skipped — one dead feed never
blocks the digest.
"""

from __future__ import annotations

import hashlib
import logging
import re
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from html import unescape
from typing import List, Optional
from urllib.parse import urlparse, urlunparse

import feedparser
import requests
from dateutil import parser as dateparser

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


_IMG_IN_HTML_RE = re.compile(r'<img[^>]+src=["\']([^"\']+)["\']', re.IGNORECASE)


def _looks_like_image(url: str) -> bool:
    if not url or not url.lower().startswith(("http://", "https://")):
        return False
    return True


def _extract_image(entry) -> Optional[str]:
    """Pull the best representative image URL from a feed entry.

    Tries the common feed conventions in order of reliability:
    media:content, media:thumbnail, enclosures, then any <img> in the
    summary/content HTML.
    """
    # media:content (often carries the lead image with a URL + medium="image")
    for media in getattr(entry, "media_content", []) or []:
        url = media.get("url")
        medium = (media.get("medium") or "").lower()
        mtype = (media.get("type") or "").lower()
        if url and (medium == "image" or mtype.startswith("image") or _looks_like_image(url)):
            return url
    # media:thumbnail
    for thumb in getattr(entry, "media_thumbnail", []) or []:
        url = thumb.get("url")
        if url and _looks_like_image(url):
            return url
    # enclosures (RSS <enclosure> with an image type)
    for enc in getattr(entry, "enclosures", []) or []:
        url = enc.get("href") or enc.get("url")
        if url and (enc.get("type", "").lower().startswith("image") or _looks_like_image(url)):
            return url
    # links with rel=enclosure
    for lk in getattr(entry, "links", []) or []:
        if lk.get("rel") == "enclosure" and (lk.get("type", "").lower().startswith("image")):
            if lk.get("href"):
                return lk["href"]
    # Fall back to the first <img> embedded in the summary/content HTML.
    html_blobs = [getattr(entry, "summary", "") or ""]
    for c in getattr(entry, "content", []) or []:
        html_blobs.append(c.get("value", "") or "")
    for blob in html_blobs:
        m = _IMG_IN_HTML_RE.search(blob)
        if m and _looks_like_image(m.group(1)):
            return m.group(1)
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
        image_url=_extract_image(entry),
    )


_SITEMAP_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
_META_TAG_RE = re.compile(r"<meta\b[^>]*>", re.IGNORECASE)
_ATTR_RE = re.compile(r'([\w:-]+)\s*=\s*(?:"([^"]*)"|\'([^\']*)\')')
_HTML_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>",
                            re.IGNORECASE | re.DOTALL)
# beehiiv serves every post at /p/<slug>; other sitemap URLs are tag pages,
# author pages and the like.
_POST_PATH = "/p/"


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = dateparser.isoparse(value.strip())
    except (ValueError, OverflowError):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _parse_sitemap(xml: bytes):
    """Return ([(post_url, lastmod)], [child_sitemap_url]) from sitemap XML."""
    root = ET.fromstring(xml)
    posts, children = [], []
    for node in root:
        loc = (node.findtext(f"{_SITEMAP_NS}loc") or "").strip()
        if not loc:
            continue
        if node.tag == f"{_SITEMAP_NS}sitemap":
            children.append(loc)
        elif _POST_PATH in urlparse(loc).path:
            posts.append((loc, _parse_iso(node.findtext(f"{_SITEMAP_NS}lastmod"))))
    return posts, children


def _page_meta(html: str) -> dict:
    """Map og:/article:/name meta keys to their content values."""
    meta = {}
    for tag in _META_TAG_RE.findall(html):
        attrs = {k.lower(): (v1 if v1 is not None else v2)
                 for k, v1, v2 in _ATTR_RE.findall(tag)}
        key = (attrs.get("property") or attrs.get("name") or "").lower()
        if key and "content" in attrs and key not in meta:
            meta[key] = unescape(attrs["content"]).strip()
    return meta


def _get(url: str, timeout: int) -> requests.Response:
    resp = requests.get(
        url, timeout=timeout,
        headers={"User-Agent": _USER_AGENT, "Cache-Control": "no-cache"},
    )
    resp.raise_for_status()
    return resp


def fetch_sitemap_feed(feed: Feed, timeout: int,
                       max_per_feed: int) -> List[Article]:
    """Read the newest posts of a site that has a sitemap but no RSS feed."""
    try:
        posts, children = _parse_sitemap(_get(feed.url, timeout).content)
        for child in children[:5]:          # sitemap index -> child sitemaps
            posts.extend(_parse_sitemap(_get(child, timeout).content)[0])
    except (requests.RequestException, ET.ParseError) as exc:
        log.warning("Failed to read sitemap for %s: %s", feed.name, exc)
        return []

    epoch = datetime.fromtimestamp(0, tz=timezone.utc)
    posts.sort(key=lambda p: p[1] or epoch, reverse=True)

    articles: List[Article] = []
    for link, lastmod in posts[:max_per_feed]:
        try:
            html = _get(link, timeout).text
        except requests.RequestException as exc:
            log.warning("Failed to fetch %s post %s: %s", feed.name, link, exc)
            continue
        meta = _page_meta(html)
        title = meta.get("og:title") or meta.get("twitter:title")
        if not title:
            m = _HTML_TITLE_RE.search(html)
            title = unescape(m.group(1)).strip() if m else ""
        if not title:
            continue
        published = (_parse_iso(meta.get("article:published_time"))
                     or lastmod)
        articles.append(Article(
            title=_WS_RE.sub(" ", title),
            link=link,
            source=feed.name,
            region=feed.region,
            published=published,
            summary=_clean_summary(meta.get("og:description")
                                   or meta.get("description", "")),
            uid=hashlib.sha1(_normalize_link(link).encode()).hexdigest()[:16],
            image_url=meta.get("og:image") or None,
        ))
    log.info("Read %d post(s) from %s via sitemap.", len(articles), feed.name)
    return articles


def fetch_feed(feed: Feed, timeout: int, max_per_feed: int) -> List[Article]:
    if feed.kind == "sitemap":
        return fetch_sitemap_feed(feed, timeout, max_per_feed)
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
