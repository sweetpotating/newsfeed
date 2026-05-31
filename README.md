# 🗞️ AI News Telegram Digest  +  💼 AI Jobs in Singapore

This repo ships **two** zero-server Telegram bots that run for free on GitHub
Actions:

| Bot | Module | What it pushes | Docs |
|-----|--------|----------------|------|
| 🗞️ **AI News Digest** | `python -m ainews` | Curated AI news, one rich post per article | this page |
| 💼 **AI Jobs (Singapore)** | `python -m aijobs` | **AI/ML job openings in Singapore** at OpenAI, Anthropic, Google DeepMind/Gemini & more | [jump ↓](#-ai-jobs-in-singapore) |

Both share the same Telegram client, scheduling model and committed-state
pattern. The jobs bot is documented in full [at the bottom](#-ai-jobs-in-singapore).

---

A zero-server Telegram bot that pushes you a curated feed of the latest **AI
news** on a schedule. It pulls from a wide set of **global**, **Asia-focused**
and **official lab** RSS/Atom feeds, classifies and ranks each item, writes
**3 AI-generated takeaways** per story, de-duplicates against what it already
sent, and posts **one rich message per article** (with the article image
attached) to your Telegram chat or channel.

Each post shows:
- a clear, linked **headline**
- **source · platform badge · region · time** (e.g. *Anthropic News · 🟧 Claude · 📣 Official · 1h ago*)
- **3 concise takeaways** summarising the article
- the article **image** and a **Read more →** link

Coverage is organised around what you asked for:

1. **AI platforms** (priority order) — 🟧 Claude · 🟢 ChatGPT · 🔵 Gemini ·
   🟣 Qwen · 🐳 DeepSeek · ⚡ Grok — plus other major labs (Meta AI, Mistral,
   Microsoft, Hugging Face, …).
2. **AI industry news** — international press + Asia outlets.
3. **Agentic payments & agentic commerce** — payments/fintech feeds, surfaced
   by keyword (AP2, Agentic Commerce Protocol, x402, Visa Intelligent
   Commerce, Mastercard Agent Pay, Stripe agent toolkit, …).

It runs **for free on GitHub Actions** — no server to maintain. State is
committed back to the repo so each run knows what it already sent.

---

## How it works

```
feeds ─▶ fetch (concurrent, timeouts, +image) ─▶ normalise ─▶ drop already-seen
     ─▶ drop too-old ─▶ classify (platform / agentic / industry)
     ─▶ rank (relevance) ─▶ keep top N ─▶ AI takeaways (1 batched call)
     ─▶ render one post per article ─▶ Telegram (sendPhoto/sendMessage)
     ─▶ save state
```

- **Sources** live in [`ainews/sources.py`](ainews/sources.py) — add or remove
  feeds freely; dead feeds are skipped gracefully.
- **Classification** lives in [`ainews/classifier.py`](ainews/classifier.py) —
  keyword maps for platforms and agentic-commerce. Even when a lab has no
  reliable feed (e.g. DeepSeek), its news is still tagged from the industry
  feeds.
- **Ranking** ([`ainews/ranker.py`](ainews/ranker.py)) scores items so the top
  ~10 are sent: AI platforms (in priority order) and agentic-commerce first,
  then recency, with a nudge for official lab sources. This keeps a
  one-post-per-article feed readable instead of flooding the chat.
- **Takeaways** ([`ainews/summarizer.py`](ainews/summarizer.py)) are written by
  Claude in a **single batched API call** per run (prompt-cached system prompt
  to keep cost low). Summaries are drawn from the headline + feed blurb. If no
  `ANTHROPIC_API_KEY` is set, the bot still runs and falls back to the feed
  blurb — no bullets, no crash.
- **De-dup state** is a small JSON file at `state/seen.json`. Only articles
  that were actually sent are marked, so a failed send retries next run.

---

## Setup (5 minutes)

### 1. Create your bot
1. In Telegram, message [@BotFather](https://t.me/BotFather) → `/newbot` →
   follow prompts. Copy the **bot token** it gives you.

### 2. Choose where the digest goes (`TELEGRAM_CHAT_ID`)
Pick one:
- **Personal chat:** message [@userinfobot](https://t.me/userinfobot); it
  replies with your numeric id. (Also send your new bot any message first so it
  is allowed to DM you.)
- **Channel:** create a channel, add your bot as an **admin**, and use the
  channel handle, e.g. `@my_ai_news`.
- **Group:** add the bot to the group; the id is usually a negative number like
  `-1001234567890`.

### 3. Add GitHub secrets
In the repo: **Settings → Secrets and variables → Actions → New repository
secret**, add:
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `ANTHROPIC_API_KEY` *(optional)* — enables the 3-bullet AI takeaways. Get one
  at [console.anthropic.com](https://console.anthropic.com). Without it the bot
  still works and shows the feed's own blurb instead of takeaways.

### 4. Enable the workflow
The workflow [`/.github/workflows/digest.yml`](.github/workflows/digest.yml)
runs **every 3 hours**. To test it now: **Actions → AI News Digest → Run
workflow** (tick *dry run* first if you just want to preview in the logs).

> The workflow needs to push the updated `state/seen.json` back. That requires
> **Settings → Actions → General → Workflow permissions → Read and write
> permissions**.

That's it — you'll start receiving digests. 🎉

---

## Run it locally

```bash
pip install -r requirements.txt

# Preview without sending (no token needed):
python -m ainews --dry-run

# Actually send:
export TELEGRAM_BOT_TOKEN="123:abc"
export TELEGRAM_CHAT_ID="123456789"
python -m ainews

# Widen the window for a one-off catch-up run:
python -m ainews --lookback 72 --max-items 20

# Takeaways need an Anthropic key (skip it and you get feed blurbs instead):
export ANTHROPIC_API_KEY="sk-ant-..."
```

Copy [`.env.example`](.env.example) to `.env` for local config (it is
git-ignored). Then `set -a; . ./.env; set +a` before running.

### CLI flags
| Flag | Meaning |
|------|---------|
| `--dry-run` | Print the digest to stdout; send nothing, save no state. |
| `--lookback N` | Only include items from the last `N` hours (default 24). |
| `--max-items N` | Cap how many articles are sent per run (default 10). |
| `--no-state` | Ignore the dedup file (always treat everything as new). |
| `-v` / `--verbose` | Debug logging. |

---

## Configuration

All optional, via environment variables (see [`.env.example`](.env.example)):

| Variable | Default | Purpose |
|----------|---------|---------|
| `TELEGRAM_BOT_TOKEN` | – | **Required** to send. |
| `TELEGRAM_CHAT_ID` | – | **Required** to send. |
| `ANTHROPIC_API_KEY` | – | Enables AI takeaways. Optional — falls back to feed blurb. |
| `AINEWS_SUMMARY_MODEL` | `claude-haiku-4-5` | Model for takeaways. Bump to `claude-sonnet-4-6` / `claude-opus-4-8` for richer bullets. |
| `AINEWS_SUMMARIZE` | `1` | Set `0` to disable AI takeaways. |
| `AINEWS_PHOTOS` | `1` | `1` = attach the article image to each post; `0` = text only. |
| `AINEWS_SEND_DELAY_MS` | `1000` | Pause between per-article posts (rate-limit safety). |
| `AINEWS_LOOKBACK_HOURS` | `24` | Time window for "new". |
| `AINEWS_MAX_ITEMS` | `10` | Max articles sent per run (one post each). |
| `AINEWS_MAX_PER_FEED` | `8` | Items taken per feed per run. |
| `AINEWS_TIMEOUT` | `20` | Per-feed network timeout (s). |
| `AINEWS_STATE_FILE` | `state/seen.json` | Dedup state path. |
| `AINEWS_STATE_TTL_DAYS` | `45` | Prune seen entries older than this. |

### Cost of AI takeaways
One batched call per run on **Haiku 4.5** (the default) for ~10 articles is a
fraction of a US cent. Running every 3 hours that's roughly a few cents a month.
Switching `AINEWS_SUMMARY_MODEL` to Sonnet or Opus improves bullet quality at
proportionally higher cost. No key set → no cost, blurb fallback.

### Change the schedule
Edit the `cron` in the workflow. Examples:
- Twice daily (08:00 & 18:00 UTC): `0 8,18 * * *`
- Hourly: `0 * * * *`

### Tune sources / keywords
Edit [`ainews/sources.py`](ainews/sources.py) (feeds) and
[`ainews/classifier.py`](ainews/classifier.py) (platform & agentic keywords).

---

## Customising what counts as a "platform"
`PLATFORM_ORDER` and `PLATFORM_LABELS` in `classifier.py` define the priority
order and the badges shown. Add a new key + keyword list to track another
platform.

---

## Tests

```bash
pip install pytest
python -m pytest -q
```

Tests cover classification (priority order, word-boundary matching,
agentic-vs-platform precedence), ranking (platform/agentic priority, caps),
post rendering (title/meta/takeaways, blurb fallback, HTML escaping, caption
limit), feed image extraction, and summarizer graceful degradation — all
offline, no network or API key needed.

---

## Notes & limitations
- Some AI labs don't publish a stable public feed; their news is still captured
  via keyword tagging on the industry feeds. If a lab adds an official feed,
  drop it into `sources.py`.
- Feeds occasionally rate-limit or go down — those runs simply skip them.
- **Takeaways are built from the headline + the feed's summary blurb**, not the
  full article text. Some feeds give a rich blurb, others only a sentence, so
  bullet depth varies by source. (Full-page fetching could be added later.)
- **Images** come from the feed (`media:content`, enclosures, or the first
  `<img>` in the summary). If a feed exposes none, that article posts as text.
- This is a **push-only feed**. Interactive commands (`/latest`, etc.) would
  need an always-on bot process; the design intentionally favours the free,
  serverless cron model.

---
---

# 💼 AI Jobs in Singapore

A companion zero-server Telegram bot that pushes you **AI / ML job openings in
Singapore** on a schedule — focused on the big AI labs you care about
(**OpenAI, Anthropic, Google DeepMind / Gemini, xAI, Mistral, Cohere,
Perplexity, Hugging Face, …**) plus the other companies that staff real AI
teams in the city-state.

It reads postings **straight from each company's hiring system** — Greenhouse,
Lever, Ashby and the Google Careers API — so there's no scraping and no
fragile HTML parsing. Each run keeps only the **Singapore-based AI roles**,
de-duplicates against what it already sent, ranks them (frontier labs and
research/ML roles first), and posts **one message per new opening**:

```
⭐ Priority AI Lab
OpenAI — Member of Technical Staff, Research
OpenAI · Singapore · 🔬 Research · 2d ago

A research role on OpenAI's Singapore team working on frontier models.
Apply →
```

## How it works

```
companies ─▶ fetch each ATS/careers API (concurrent, timeouts)
          ─▶ normalise to Job ─▶ keep Singapore locations
          ─▶ keep AI/ML/research roles (drop recruiters, ops, etc.)
          ─▶ drop already-seen ─▶ drop too-old ─▶ rank ─▶ keep top N
          ─▶ optional 1-line AI note ─▶ Telegram ─▶ save state
```

- **Roster** lives in [`aijobs/sources.py`](aijobs/sources.py). Each company
  declares its ATS provider (`greenhouse` / `lever` / `ashby` / `google`) and
  board slug. Priority labs are flagged so they rank to the top with a ⭐.
- **Filtering** lives in [`aijobs/filters.py`](aijobs/filters.py): a generous
  Singapore **location** match (handles "Singapore", "Remote – Singapore",
  multi-location postings, etc.) and a precise AI **role** match on the title
  (research / ML / data / AI-product / safety / infra), with hard exclusions
  for non-AI roles that happen to share a keyword.
- **Ranking** ([`aijobs/ranker.py`](aijobs/ranker.py)) floats the marquee labs
  and research/ML roles up, then recency, and caps the run so the chat stays
  readable.
- **AI note** ([`aijobs/summarizer.py`](aijobs/summarizer.py)) writes one
  concise line per role in a single batched, prompt-cached Claude call.
  Optional — without `ANTHROPIC_API_KEY` the bot uses the posting's own blurb.
- **De-dup state** is a small JSON file at `state/jobs_seen.json`, separate
  from the news bot's state. Only roles actually sent are marked.

## Setup

The jobs feed posts to its **own Telegram channel**, separate from the news
digest:

1. **Create a channel** in Telegram (e.g. *AI Jobs SG*), then **add your bot as
   an admin** so it can post there.
2. **Get the channel id.** Use its public handle (e.g. `@my_ai_jobs_sg`), or
   for a private channel forward one of its messages to
   [@userinfobot](https://t.me/userinfobot) to read the numeric id (looks like
   `-1001234567890`).
3. **Add a GitHub secret** `AIJOBS_CHAT_ID` set to that channel
   (**Settings → Secrets and variables → Actions → New repository secret**).

The bot **reuses the news bot's** `TELEGRAM_BOT_TOKEN` and (optional)
`ANTHROPIC_API_KEY` — the same bot can post to multiple channels, so you only
add `AIJOBS_CHAT_ID`. (Want a fully separate bot? Add an `AIJOBS_BOT_TOKEN`
secret too.) If `AIJOBS_CHAT_ID` is left unset, the feed falls back to
`TELEGRAM_CHAT_ID` and shares the news digest's chat.

The workflow [`.github/workflows/jobs.yml`](.github/workflows/jobs.yml) runs
**twice daily** (09:00 & 18:00 SGT). Trigger it now from **Actions → AI Jobs
(Singapore) → Run workflow** (tick *dry run* to preview in the logs first).

## Run it locally

```bash
pip install -r requirements.txt

# Preview without sending (no token needed). Widen the window for a first look:
python -m aijobs --dry-run --lookback 720 --max-items 25

# Actually send (to the jobs channel):
export TELEGRAM_BOT_TOKEN="123:abc"     # shared with the news bot
export AIJOBS_CHAT_ID="@my_ai_jobs_sg"  # the dedicated jobs channel
python -m aijobs
```

> **Note:** the ATS APIs (greenhouse / ashby / lever / Google) must be
> reachable from wherever you run this. GitHub Actions can reach them; some
> locked-down networks return `403`, in which case run it on Actions instead.

### CLI flags
| Flag | Meaning |
|------|---------|
| `--dry-run` | Print the feed to stdout; send nothing, save no state. |
| `--lookback N` | Only include roles posted in the last `N` hours (default 168). |
| `--max-items N` | Cap how many roles are sent per run (default 15). |
| `--no-state` | Ignore the dedup file (treat everything as new). |
| `-v` / `--verbose` | Debug logging (shows per-board fetch counts). |

## Configuration

All optional, via environment variables (see [`.env.example`](.env.example)):

| Variable | Default | Purpose |
|----------|---------|---------|
| `AIJOBS_CHAT_ID` | falls back to `TELEGRAM_CHAT_ID` | The dedicated jobs channel. |
| `AIJOBS_BOT_TOKEN` | falls back to `TELEGRAM_BOT_TOKEN` | Use a separate bot (optional). |
| `AIJOBS_LOOKBACK_HOURS` | `168` | Time window for "new" (one week). |
| `AIJOBS_MAX_ITEMS` | `15` | Max roles sent per run. |
| `AIJOBS_TIMEOUT` | `20` | Per-board network timeout (s). |
| `AIJOBS_STATE_FILE` | `state/jobs_seen.json` | Dedup state path. |
| `AIJOBS_STATE_TTL_DAYS` | `90` | Prune seen entries older than this. |
| `AIJOBS_SUMMARIZE` | `1` | Set `0` to disable the AI note. |
| `AIJOBS_SUMMARY_MODEL` | `claude-haiku-4-5` | Model for the note. |
| `AIJOBS_SEND_DELAY_MS` | `1000` | Pause between per-role posts. |
| `AIJOBS_EXTRA_LOCATIONS` | – | Extra location keywords to accept (e.g. `remote, apac`). |

## Tuning the company roster

Open [`aijobs/sources.py`](aijobs/sources.py) and add a `Company(...)` line.
The `token` is the slug from the company's careers URL. To verify a slug works,
open its API URL in a browser — a JSON document means it's good:

| Provider | API URL to check | Example slug source |
|----------|------------------|---------------------|
| `greenhouse` | `https://boards-api.greenhouse.io/v1/boards/<slug>/jobs` | `boards.greenhouse.io/<slug>` |
| `lever` | `https://api.lever.co/v0/postings/<slug>?mode=json` | `jobs.lever.co/<slug>` |
| `ashby` | `https://api.ashbyhq.com/posting-api/job-board/<slug>` | `jobs.ashbyhq.com/<slug>` |
| `google` | `https://careers.google.com/api/v3/search/?location=Singapore&q=<query>` | (covers DeepMind / Gemini) |

Dead, renamed or rate-limited boards are **skipped gracefully**, so it's safe
to keep optimistic entries. Slugs drift over time — if a company stops
appearing, re-check its slug with the table above.

## Notes & limitations
- **Frontier labs often have 0 Singapore roles at a given moment.** That's why
  the roster also includes other AI-heavy employers — so the feed isn't empty
  between marquee openings. Priority labs still rank first when they do hire.
- **Meta and Apple** use bespoke, login-walled careers systems with no stable
  public feed, so they aren't polled. Add them if they expose a standard board.
- The role filter is **title-driven** and tuned for precision; a genuinely
  AI-focused role with an unusual title may be missed. Widen the keyword lists
  in `filters.py` if you want more recall.
- This is a **push-only feed**, same serverless design as the news bot.

## Tests

```bash
python -m pytest tests/aijobs -q
```

Offline tests (no network, no API key) cover Singapore location matching,
AI-role classification & exclusions, every ATS adapter's JSON normalisation,
ranking priority, post rendering / HTML-escaping / truncation, and the
end-to-end selection pipeline (filtering, dedup, seen-skipping, lookback).
