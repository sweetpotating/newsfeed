"""Decide which postings are Singapore-based AI/ML roles.

A job must pass two independent gates:

  1. **Location** is in (or includes) Singapore. ATS location strings are
     messy — "Singapore", "Singapore, Singapore", "APAC (Singapore)",
     "Remote - Singapore", "Multiple Locations" with SG in a secondary list.
     We match the word "singapore" (or the bare token "sg") anywhere in the
     combined location text. Extra accepted keywords (e.g. remote/apac) are
     configurable.

  2. **Role** is genuinely about AI / ML / data science / research, matched by
     keyword on the job title (with a light assist from the department).
     Recruiters, office managers and unrelated roles in a SG office are
     filtered out.

The location gate is deliberately generous (so we don't miss a SG role hidden
in a multi-location posting) while the role gate leans on precise, mostly
multi-word keywords so the feed stays on-topic.
"""

from __future__ import annotations

import re
from typing import List

# --- Location -------------------------------------------------------------
# Whole-word "singapore"; also a bare "sg" token (e.g. "SG", "Remote-SG").
_SG_PATS = [
    re.compile(r"(?<![a-z])singapore(?![a-z])", re.IGNORECASE),
    re.compile(r"(?<![a-z])sg(?![a-z])", re.IGNORECASE),
]


def is_singapore(location_text: str, extra_keywords: List[str] | None = None) -> bool:
    text = location_text or ""
    if any(p.search(text) for p in _SG_PATS):
        return True
    for kw in extra_keywords or []:
        kw = kw.strip().lower()
        if kw and kw in text.lower():
            return True
    return False


# --- Role -----------------------------------------------------------------
# Keyword -> coarse role tag, used both to gate and to badge the post.
# Keep keywords specific (mostly multi-word) to avoid false positives like a
# generic "Engineer" or "Analyst" in a Singapore office.
_ROLE_KEYWORDS = {
    "research": [
        "research scientist", "research engineer", "research resident",
        "member of technical staff", "ai researcher", "ml researcher",
        "research lead", "research manager",
    ],
    "ml": [
        "machine learning", "ml engineer", "mle", "deep learning",
        "applied scientist", "applied ai", "ai engineer", "ai/ml",
        "ml scientist", "ai scientist", "genai", "generative ai",
        "llm", "large language model", "nlp engineer",
        "computer vision", "speech recognition", "reinforcement learning",
        "foundation model",
    ],
    "data": [
        "data scientist", "data science", "mlops", "ml ops",
        "machine learning operations",
    ],
    "ai-product": [
        "ai product", "product manager, ai", "ai solutions", "ai architect",
        "ai consultant", "ai specialist", "forward deployed", "ai lead",
        "head of ai", "ai strategy", "prompt engineer", "agent engineer",
        "ai program", "ai developer advocate", "ai sales",
    ],
    "ai-safety": [
        "alignment", "ai safety", "responsible ai", "ai policy",
        "ai governance", "model safety", "ai red team", "red teamer",
    ],
    "infra": [
        "ai infrastructure", "ml infrastructure", "ml platform",
        "ai platform", "inference engineer", "training infrastructure",
        "gpu", "cuda", "ml systems",
    ],
}


def _compile(words: List[str]) -> List[re.Pattern]:
    pats = []
    for w in words:
        esc = re.escape(w.strip()).replace(r"\ ", r"\s+")
        # Bound by non-word chars so "llm" doesn't match inside "skillment".
        pats.append(re.compile(rf"(?<![\w]){esc}(?![\w])", re.IGNORECASE))
    return pats


_ROLE_PATS = {tag: _compile(words) for tag, words in _ROLE_KEYWORDS.items()}

# Hard exclusions: titles that might brush a keyword but are not AI roles
# (e.g. "Data Center Technician" near "data"). Checked on the title only.
_EXCLUDE = _compile([
    "data center", "data centre", "datacenter", "recruiter", "recruiting",
    "sourcer", "office manager", "executive assistant", "receptionist",
    "facilities", "accountant", "payroll", "paralegal", "data entry",
])


def role_tags(title: str, department: str = "") -> List[str]:
    """Return the coarse AI role tags a posting matches (priority-ordered)."""
    title = title or ""
    if any(p.search(title) for p in _EXCLUDE):
        return []
    haystack = f"{title}\n{department or ''}"
    return [tag for tag, pats in _ROLE_PATS.items()
            if any(p.search(haystack) for p in pats)]


def is_ai_role(title: str, department: str = "") -> bool:
    return bool(role_tags(title, department))
