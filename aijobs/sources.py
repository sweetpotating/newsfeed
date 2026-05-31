"""Curated roster of companies to watch for AI roles in Singapore.

Each company is fetched directly from its Applicant Tracking System (ATS) or
careers API. Four providers cover the vast majority of tech employers:

  * ``greenhouse`` -> https://boards-api.greenhouse.io/v1/boards/<token>/jobs
  * ``lever``      -> https://api.lever.co/v0/postings/<token>?mode=json
  * ``ashby``      -> https://api.ashbyhq.com/posting-api/job-board/<token>
  * ``google``     -> Google Careers search API (covers Gemini / DeepMind);
                      the ``token`` is the Google careers query string.

For the ATS providers the ``token`` is the company's board slug — the bit in
their careers URL, e.g. ``boards.greenhouse.io/<token>`` or
``jobs.ashbyhq.com/<token>``.

Why a roster and not just "the big 3"?
--------------------------------------
OpenAI / Anthropic / Google each have only a handful of Singapore openings at
any moment — often zero. To make the feed genuinely useful, we also watch the
other labs and the AI-heavy employers that staff real ML / research / AI-eng
teams in Singapore. ``is_priority_lab=True`` marks the marquee AI companies
the user called out so they always rank to the top and get a ⭐ badge.

Dead, renamed or rate-limited boards are skipped gracefully by the fetcher, so
it is safe to keep optimistic entries here. Tune freely: to add a company,
find its careers page, note which ATS it uses and its slug, and drop a
``Company(...)`` line in the right list. To verify a slug, open the
corresponding API URL above in a browser — a JSON document means it works.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Company:
    name: str
    provider: str            # greenhouse | lever | ashby | google
    token: str               # board slug, or (for google) a careers query
    is_priority_lab: bool = False


# --- Priority AI labs (the user's headline asks) --------------------------
# Frontier labs. They may have 0 SG roles on any given day; when one opens it
# ranks to the very top with a ⭐ badge. Google DeepMind / Gemini roles come
# through the Google Careers API below.
PRIORITY_LABS = [
    Company("OpenAI", "ashby", "openai", is_priority_lab=True),
    Company("Anthropic", "greenhouse", "anthropic", is_priority_lab=True),
    Company("Google DeepMind / Gemini", "google",
            "artificial intelligence", is_priority_lab=True),
    Company("xAI", "greenhouse", "xai", is_priority_lab=True),
    Company("Mistral AI", "ashby", "mistralai", is_priority_lab=True),
    Company("Cohere", "greenhouse", "cohere", is_priority_lab=True),
    Company("Perplexity", "ashby", "perplexity-ai", is_priority_lab=True),
    Company("Hugging Face", "greenhouse", "huggingface", is_priority_lab=True),
    Company("ElevenLabs", "ashby", "elevenlabs", is_priority_lab=True),
    Company("Scale AI", "greenhouse", "scaleai", is_priority_lab=True),
    Company("Stability AI", "greenhouse", "stabilityai", is_priority_lab=True),
    Company("Runway", "ashby", "runway", is_priority_lab=True),
    Company("Together AI", "ashby", "together-ai", is_priority_lab=True),
    Company("Sierra", "ashby", "sierra", is_priority_lab=True),
]

# --- AI-heavy employers with real Singapore ML / AI teams -----------------
# Strong, frequently-hiring AI / ML / data-science presence in Singapore.
AI_EMPLOYERS = [
    Company("Databricks", "greenhouse", "databricks"),
    Company("Snowflake", "ashby", "snowflake"),
    Company("Stripe", "greenhouse", "stripe"),
    Company("Canva", "lever", "canva"),
    Company("Grab", "lever", "grab"),
    Company("Sea / Shopee", "lever", "sea"),
    Company("GitLab", "greenhouse", "gitlab"),
    Company("Datadog", "greenhouse", "datadog"),
    Company("Confluent", "greenhouse", "confluent"),
    Company("MongoDB", "greenhouse", "mongodb"),
    Company("Airwallex", "lever", "airwallex"),
    Company("Nansen", "ashby", "nansen"),
    Company("Algolia", "greenhouse", "algolia"),
    Company("Rippling", "greenhouse", "rippling"),
    Company("Twilio", "greenhouse", "twilio"),
    Company("GitHub", "greenhouse", "github"),
    Company("HashiCorp", "greenhouse", "hashicorp"),
]

# Meta and Apple run bespoke, login-walled careers systems with no stable
# public job feed, so they cannot be polled the same way. Their Singapore AI
# openings are linked from the README instead. If they expose a standard
# board, add it above.


def all_companies() -> list[Company]:
    return [*PRIORITY_LABS, *AI_EMPLOYERS]
