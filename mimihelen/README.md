# 💧 Mimi Helen Bot

A Telegram bot that nags you — in **Dr Helen's** voice — to use your **eyedrops
3–5 times a day**, take care of your eyes, and (most importantly) **stop rubbing
them**. All lowercase, heavy Singlish, fierce on the surface and caring
underneath: *"eyedrop time. just."*, *"no rubbing your eyes ah, i'm serious"*,
*"ok good, small thing but you did it 👌🏼"*. Tiny enough to run for free.

> The voice lives entirely in `mimihelen/content.py` — easy to soften or retune
> anytime. It's a friendly reminder, not a real consultation with Dr Helen.

## What it does

- ⏰ **Scheduled eyedrop reminders** at 3–5 configurable times a day, each
  tagged "dose 2 of 4" so she knows where she is.
- 🚫 **"Don't rub your eyes" nudge** on every reminder, with kinder
  alternatives (blink, cool compress).
- 💡 **200+ rotating eye-care tips** (`tips.py`) — drop technique, dry eye,
  screen habits, sleep, UV, nutrition, contacts, makeup, no-rubbing, red-flag
  symptoms, post-op care, and more — dealt in a **shuffled, no-repeat order each
  day** so the day's reminders never show the same tip twice (and won't repeat
  for weeks).
- 🧼 **Step-by-step how-to** on the first reminder of the day, so the drops go
  in correctly.
- ✅ **Dose logging, daily progress and streaks** via buttons and commands —
  with an **↩️ Undo** (button after Done, or `/undo`) for accidental taps.
- 📋 **Compliance report** — `/report` (or `/report 14`, `/report 30`) builds a
  clean, forwardable summary (per-day log + adherence %) to send to her eye
  doctor showing compliance / non-compliance.
- 💬 **Answers questions** — *"when's my next reminder?"*, *"what are my
  eyedrops for?"*, *"how do i use the drops?"*, *"can i rub my eyes?"* — in her
  voice, with general info only (always defers to your real eye doctor).
- 🕒 **Change the schedule from chat** — `/schedule 08:00, 13:00, 19:00, 22:00`
  resets the reminder times (and the daily goal) on the spot; the change is
  saved and survives restarts. Bare `/schedule` shows the current times.
- ⏰ **Snooze with a live countdown** — the "⏰ Snooze" button on a reminder
  posts a message that ticks down (5:00 → 4:00 → …) and re-sends the reminder at
  zero, without ever blocking the bot. Length is configurable: set
  `MIMIHELEN_SNOOZE_MIN` (default **5**) or send `/snooze 10` from chat.

## One worker does everything (`serve`)

`serve` is the whole deployment: it **sends the reminders**, handles **buttons /
commands / questions**, and lets you **change the schedule from chat** — all in
one always-on process. State (doses, streak, schedule, which reminders already
went out) is saved to `state/mimihelen.json`; in CI it's committed back so it
survives restarts.

The push-only `remind` cron (`mimihelen.yml`) can't receive button presses or
questions, so it's kept only as a **manual send/preview tool** and its schedule
is disabled — the `serve` worker owns the scheduling now.

## Two ways to run it

### Option A — `serve` mode (full experience: reminders + buttons + Q&A)

Run one small always-on process (your own machine, a Raspberry Pi, or a free
host like Railway / Render / Fly.io):

```bash
pip install -r requirements.txt
export TELEGRAM_BOT_TOKEN=...        # the bot token
export TELEGRAM_CHAT_ID=...          # who to remind
export MIMIHELEN_EYEDROPS="lubricating drops for dry eyes, 4x a day"  # optional
export ANTHROPIC_API_KEY=sk-ant-...  # optional, for open-ended questions
python -m mimihelen serve
```

This one process fires reminders at your scheduled times **and** handles
buttons, commands and questions.

### Option B — reminders only, zero hosting (free GitHub Actions cron)

If you just want the daily reminders and don't need buttons/Q&A:

1. Create a bot with [@BotFather](https://t.me/BotFather) → copy the token.
2. Get the chat id (message [@userinfobot](https://t.me/userinfobot)).
3. **Settings → Secrets and variables → Actions**
   - Secrets: `MIMIHELEN_BOT_TOKEN`, `MIMIHELEN_CHAT_ID`
   - Optional Variables: `MIMIHELEN_FRIEND_NAME`, `MIMIHELEN_TIMES`,
     `MIMIHELEN_TZ`, `MIMIHELEN_DAILY_GOAL`
4. The schedule fires automatically. Test now: **Actions → Mimi Helen Bot →
   Run workflow** (leave *force* on).

> Reminders in this mode still show the buttons, but they only respond if a
> `serve` process is also running. The cron lines are in **UTC**; defaults map
> to Singapore time — if you change `MIMIHELEN_TIMES`, update the cron to match.

Commands: `/done` `/today` `/streak` `/tip` `/schedule` `/ask` `/help` — or
just type a question.

### Option C — everything on free GitHub Actions (no laptop, no account)

The `.github/workflows/mimihelen-serve.yml` worker runs the **full `serve`** bot
near-continuously: reminders, buttons, Q&A and chat schedule-changes. State is
committed back to the repo (`MIMIHELEN_GIT_PERSIST`), so doses, streaks and your
chat-set schedule survive restarts. Public repos get unlimited Actions minutes,
so it's $0.

1. Set the secrets `MIMIHELEN_BOT_TOKEN` / `MIMIHELEN_CHAT_ID`.
2. Optional repo **Variables** (Settings → Secrets and variables → Actions →
   Variables): `MIMIHELEN_TIMES`, `MIMIHELEN_TZ`, `MIMIHELEN_DAILY_GOAL`,
   `MIMIHELEN_FRIEND_NAME`, `MIMIHELEN_EYEDROPS`. Optional secret
   `ANTHROPIC_API_KEY` for open-ended questions.
3. It auto-starts on push and restarts itself every ~6h. To kick it off now:
   **Actions → "Mimi Helen Bot — Interactive" → Run workflow**.

How it stays up: a job runs ~6h max, so the worker runs ~5h50m then exits and is
restarted. During the short handoff Telegram queues taps/messages (held ~24h)
and the worker handles them when it returns; a reminder due in that gap still
fires on restart (within the slot tolerance) and is de-duplicated so it's never
sent twice.

> ⚠️ Only **one** `serve` may run at a time per bot — don't also run it locally,
> or Telegram returns 409. The push-only reminder cron stays disabled while this
> worker runs.

## Local preview

```bash
# Print the reminder due now (or use --force) without sending anything:
python -m mimihelen remind --force --dry-run
```

## Configuration

All optional — sensible defaults are built in. See `.env.example`.

| Variable | Default | Meaning |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | — | From @BotFather (required to send) |
| `TELEGRAM_CHAT_ID` | — | Where reminders go (required to send) |
| `MIMIHELEN_FRIEND_NAME` | `Helen` | Name used in greetings |
| `MIMIHELEN_TIMES` | `07:00,12:00,18:00,22:00` | Reminder times (24h) |
| `MIMIHELEN_TZ` | `Asia/Singapore` | Timezone for the times |
| `MIMIHELEN_DAILY_GOAL` | `4` | Doses/day for progress & streaks |
| `MIMIHELEN_SLOT_TOLERANCE_MIN` | `30` | How late a cron run still counts |
| `MIMIHELEN_STATE_FILE` | `state/mimihelen.json` | Dose/streak tracker file |
| `MIMIHELEN_EYEDROPS` | — | Her actual drops, so Q&A can answer accurately |
| `ANTHROPIC_API_KEY` | — | Optional — open-ended Q&A (serve mode) |
| `MIMIHELEN_QA_MODEL` | `claude-haiku-4-5` | Model for open-ended answers |

## Ideas for more functions (roadmap)

These are easy, friendly extensions if you want to grow the bot:

- 🗓️ **Refill / prescription reminders** — "you started this bottle ~28 days
  ago, time to reorder?"
- 💊 **Multiple drop types** — track separate medications with their own
  spacing (e.g. wait 5 min between drops).
- 📈 **Weekly summary** — "you hit your goal 6/7 days this week 🎉".
- 🩺 **Appointment reminders** — next eye-doctor / optometrist visit.
- 🤝 **Caregiver copy** — optionally CC a family member if a day is missed, for
  accountability.
- 🌡️ **Symptom check-in** — quick "how do your eyes feel today?" with a
  gentle prompt to see a doctor if redness/pain persists.
- 🌅 **Smart quiet hours** — pause reminders overnight automatically.
- 🌐 **Localization** — reminders in her preferred language.

> ⚕️ *Mimi Helen Bot is a friendly reminder tool, not medical advice. Always
> follow the dosing and instructions from her eye doctor or pharmacist.*
