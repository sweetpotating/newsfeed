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
- 💡 **~30 rotating eye-care tips** (20-20-20 rule, hydration, blink breaks,
  sunglasses, sleep, one-drop-is-enough, warm compress, annual checks, red-flag
  symptoms, and more) — dealt in a **shuffled, no-repeat order each day** so the
  day's reminders never show the same tip twice.
- 🧼 **Step-by-step how-to** on the first reminder of the day, so the drops go
  in correctly.
- ✅ **Dose logging, daily progress and streaks** via buttons and commands —
  with an **↩️ Undo** (button after Done, or `/undo`) for accidental taps.
- 💬 **Answers questions** — *"when's my next reminder?"*, *"what are my
  eyedrops for?"*, *"how do i use the drops?"*, *"can i rub my eyes?"* — in her
  voice, with general info only (always defers to your real eye doctor).

## ⚠️ Buttons & questions need `serve` mode

Telegram can't deliver a button press or a typed question to a workflow that
only *sends* messages. So:

| Feature | GitHub Actions cron (push-only) | `serve` (always-on process) |
|---|---|---|
| Scheduled reminders | ✅ | ✅ |
| ✅ Done / ⏰ Snooze / 📊 / 💡 buttons | ❌ (nothing listening) | ✅ |
| `/done` `/streak`, typed questions | ❌ | ✅ |

**If you want the buttons and Q&A to work, run `serve`** — it now *also* sends
the scheduled reminders itself, so it's a complete, single-process deployment.
(When running `serve`, disable the Actions cron so you don't get double
reminders — Actions tab → the workflow → ⋯ → Disable workflow.)

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

### Option C — buttons + Q&A on free GitHub Actions (no laptop, no account)

Keeps your existing reminder cron **and** makes the buttons + questions work,
using a second workflow (`.github/workflows/mimihelen-serve.yml`) that runs
`serve --no-schedule` near-continuously. Public repos get unlimited Actions
minutes, so it's $0.

1. Make sure the secrets `MIMIHELEN_BOT_TOKEN` / `MIMIHELEN_CHAT_ID` are set
   (same ones the reminder workflow uses).
2. Optional repo **Variables** (Settings → Secrets and variables → Actions →
   Variables) so answers are accurate: `MIMIHELEN_TIMES`, `MIMIHELEN_TZ`,
   `MIMIHELEN_DAILY_GOAL`, `MIMIHELEN_FRIEND_NAME`, `MIMIHELEN_EYEDROPS`.
   Optional secret `ANTHROPIC_API_KEY` for open-ended questions.
3. **Actions → "Mimi Helen Bot — Interactive" → Run workflow** to start it now;
   after that the schedule keeps it alive (it restarts itself every ~6h).

How it stays up: a single Actions job can run ~6h max, so the worker runs
~5h50m then exits and the schedule restarts it. During the short handoff,
Telegram queues taps/messages (it holds them ~24h) and the worker answers them
when it comes back — nothing lost, just an occasional short delay.

> ⚠️ Limitations of the free worker: (1) only **one** `serve` may run at a time
> per bot — don't also run it locally, or Telegram returns 409. (2) Dose logs
> live in memory for the worker's session, so `/today` is accurate within a
> session but `/streak` won't accumulate across the ~6h restarts. For
> persistent streaks, use Option A on an always-on host with a disk.

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
