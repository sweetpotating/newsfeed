# 🗞️ AI News Telegram Digest

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
