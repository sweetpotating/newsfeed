"""AI jobs Telegram bot.

Tracks **AI / ML job openings in Singapore** at the major AI labs (OpenAI,
Anthropic, Google DeepMind / Gemini, xAI, Mistral, Cohere, …) and other
companies that hire serious AI talent in the city-state.

It pulls live postings straight from each company's Applicant Tracking System
(Greenhouse, Lever, Ashby) or careers API — no scraping, no RSS — keeps only
the Singapore-based AI/ML roles, de-duplicates against what it already sent,
and pushes one rich Telegram message per new role on a schedule.

Runs for free on GitHub Actions; state is committed back to the repo so each
run knows what it already sent.
"""

__version__ = "1.0.0"
