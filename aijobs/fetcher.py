"""Fetch postings from each company's ATS and normalise into ``Job`` objects.

One adapter per provider (Greenhouse / Lever / Ashby / Google Careers). Boards
are fetched concurrently with a per-request timeout; a network or parse
failure for any single board is logged and skipped — one dead board never
blocks the run.

Each adapter pulls the board, then the caller filters down to the Singapore AI
roles. The boards are small JSON documents, so fetching and filtering locally
is simpler and more reliable than per-provider query params (whose location
semantics differ and are often unsupported).
"""

from __future__ import annotations

import hashlib
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import List, Optional
from urllib.parse import quote_plus

import requests

from .models import Job
from .sources import Company

log = logging.getLogger("aijobs.fetcher")

_USER_AGENT = "Mozilla/5.0 (compatible; AIJobsBot/1.0; +https://github.com/)"

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _clean(text: str, limit: int = 400) -> str:
    text = _TAG_RE.sub(" ", text or "")
    for a, b in (("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
                 ("&#39;", "'"), ("&quot;", '"'), ("&nbsp;", " ")):
        text = text.replace(a, b)
    text = _WS_RE.sub(" ", text).strip()
    if len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return text


def _uid(company: str, external_id: str, url: str) -> str:
    basis = f"{company}:{external_id or url}"
    return hashlib.sha1(basis.encode("utf-8", "ignore")).hexdigest()[:16]


def _ts_to_dt(ms_or_s) -> Optional[datetime]:
    if ms_or_s is None:
        return None
    try:
        val = float(ms_or_s)
    except (TypeError, ValueError):
        return None
    # Lever/Ashby use epoch milliseconds; anything that large is ms.
    if val > 1e12:
        val /= 1000.0
    try:
        return datetime.fromtimestamp(val, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def _iso_to_dt(s) -> Optional[datetime]:
    if not s or not isinstance(s, str):
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


# --- Provider adapters -----------------------------------------------------
def _fetch_greenhouse(company: Company, session: requests.Session,
                      timeout: int) -> List[Job]:
    url = (f"https://boards-api.greenhouse.io/v1/boards/"
           f"{company.token}/jobs?content=false")
    data = session.get(url, timeout=timeout).json()
    jobs: List[Job] = []
    for j in data.get("jobs", []):
        loc = (j.get("location") or {}).get("name", "") or ""
        link = j.get("absolute_url") or ""
        title = (j.get("title") or "").strip()
        if not title or not link:
            continue
        jobs.append(Job(
            title=_WS_RE.sub(" ", title),
            company=company.name,
            location=loc,
            url=link,
            uid=_uid(company.name, str(j.get("id", "")), link),
            is_priority_lab=company.is_priority_lab,
            department=", ".join(
                d.get("name", "") for d in (j.get("departments") or [])
            ),
            posted=_iso_to_dt(j.get("updated_at") or j.get("first_published")),
        ))
    return jobs


def _fetch_lever(company: Company, session: requests.Session,
                 timeout: int) -> List[Job]:
    url = f"https://api.lever.co/v0/postings/{company.token}?mode=json"
    data = session.get(url, timeout=timeout).json()
    jobs: List[Job] = []
    for j in data if isinstance(data, list) else []:
        cats = j.get("categories") or {}
        loc = cats.get("location", "") or ""
        all_locs = cats.get("allLocations") or []
        if all_locs:
            loc = " | ".join([loc] + [x for x in all_locs if x]) if loc \
                else " | ".join([x for x in all_locs if x])
        link = j.get("hostedUrl") or j.get("applyUrl") or ""
        title = (j.get("text") or "").strip()
        if not title or not link:
            continue
        jobs.append(Job(
            title=_WS_RE.sub(" ", title),
            company=company.name,
            location=loc,
            url=link,
            uid=_uid(company.name, str(j.get("id", "")), link),
            is_priority_lab=company.is_priority_lab,
            department=cats.get("team", "") or cats.get("department", "") or "",
            posted=_ts_to_dt(j.get("createdAt")),
            summary=_clean(j.get("descriptionPlain") or j.get("additional") or ""),
        ))
    return jobs


def _fetch_ashby(company: Company, session: requests.Session,
                 timeout: int) -> List[Job]:
    url = f"https://api.ashbyhq.com/posting-api/job-board/{company.token}"
    data = session.get(url, timeout=timeout).json()
    jobs: List[Job] = []
    for j in data.get("jobs", []):
        if j.get("isListed") is False:
            continue
        loc = j.get("location", "") or ""
        secs = j.get("secondaryLocations") or []
        sec_strs = [
            s.get("location", "") if isinstance(s, dict) else str(s) for s in secs
        ]
        if sec_strs:
            loc = " | ".join([loc] + [s for s in sec_strs if s])
        link = j.get("jobUrl") or j.get("applyUrl") or ""
        title = (j.get("title") or "").strip()
        if not title or not link:
            continue
        jobs.append(Job(
            title=_WS_RE.sub(" ", title),
            company=company.name,
            location=loc,
            url=link,
            uid=_uid(company.name, str(j.get("id", "")), link),
            is_priority_lab=company.is_priority_lab,
            department=j.get("department", "") or j.get("team", "") or "",
            posted=_iso_to_dt(j.get("publishedAt")),
        ))
    return jobs


def _fetch_google(company: Company, session: requests.Session,
                  timeout: int) -> List[Job]:
    """Google Careers search API, scoped to Singapore.

    Covers Google DeepMind / Gemini roles, which post on Google Careers rather
    than a standard ATS. The ``token`` is the free-text query.
    """
    q = quote_plus(company.token or "artificial intelligence")
    url = (
        "https://careers.google.com/api/v3/search/"
        f"?location=Singapore&q={q}&page_size=100"
    )
    data = session.get(url, timeout=timeout).json()
    jobs: List[Job] = []
    for j in data.get("jobs", []):
        title = (j.get("title") or "").strip()
        # Google nests locations under display_name / locations.
        locs = j.get("locations") or []
        loc = ", ".join(
            l.get("display") or l.get("display_name") or ""
            for l in locs if isinstance(l, dict)
        ) or j.get("location", "")
        # Build a stable apply URL from the job id.
        jid = str(j.get("id", "") or j.get("job_id", ""))
        link = j.get("apply_url") or ""
        if not link and jid:
            slug = jid.split("/")[-1]
            link = f"https://www.google.com/about/careers/applications/jobs/results/{slug}"
        if not title or not link:
            continue
        jobs.append(Job(
            title=_WS_RE.sub(" ", title),
            company=j.get("company_name") or company.name,
            location=loc,
            url=link,
            uid=_uid(company.name, jid, link),
            is_priority_lab=company.is_priority_lab,
            department=", ".join(j.get("categories") or []) if isinstance(
                j.get("categories"), list) else "",
            posted=_iso_to_dt(j.get("publish_date") or j.get("created")),
            summary=_clean(j.get("summary") or j.get("description") or ""),
        ))
    return jobs


_ADAPTERS = {
    "greenhouse": _fetch_greenhouse,
    "lever": _fetch_lever,
    "ashby": _fetch_ashby,
    "google": _fetch_google,
}


def fetch_company(company: Company, timeout: int) -> List[Job]:
    adapter = _ADAPTERS.get(company.provider)
    if adapter is None:
        log.warning("Unknown provider %r for %s", company.provider, company.name)
        return []
    session = requests.Session()
    session.headers.update({"User-Agent": _USER_AGENT,
                            "Accept": "application/json"})
    try:
        jobs = adapter(company, session, timeout)
        log.debug("%s: %d posting(s)", company.name, len(jobs))
        return jobs
    except requests.RequestException as exc:
        log.warning("Failed to fetch %s (%s): %s", company.name,
                    company.provider, exc)
        return []
    except (ValueError, KeyError, TypeError) as exc:
        log.warning("Failed to parse %s (%s): %s", company.name,
                    company.provider, exc)
        return []


def fetch_all(companies: List[Company], timeout: int,
              workers: int = 12) -> List[Job]:
    results: List[Job] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fetch_company, c, timeout): c for c in companies}
        for fut in as_completed(futures):
            company = futures[fut]
            try:
                results.extend(fut.result())
            except Exception as exc:  # adapters are defensive; last-resort guard
                log.warning("Worker failed for %s: %s", company.name, exc)
    log.info("Fetched %d posting(s) from %d board(s)", len(results), len(companies))
    return results
