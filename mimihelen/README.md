# 💧 Mimi Helen Bot

A gentle Telegram bot that helps a friend remember to use her **eyedrops 3–5
times a day**, take good care of her eyes, and — importantly — **not rub
them**. Warm, encouraging, and tiny enough to run for free.

## What it does

- ⏰ **Scheduled eyedrop reminders** at 3–5 configurable times a day, each
  tagged "dose 2 of 4" so she knows where she is.
- 🚫 **"Don't rub your eyes" nudge** on every reminder, with kinder
  alternatives (blink, cool compress).
- 💡 **Rotating eye-care tips** (20-20-20 rule, hydration, blink breaks,
  sunglasses, sleep, spacing multiple drops, and more).
- 🧼 **Step-by-step how-to** on the first reminder of the day, so the drops go
  in correctly.
- ✅ **Dose logging, daily progress and streaks** (in interactive mode) via
  buttons and commands.

## Two ways to run it

### 1. Scheduled reminders — zero hosting (recommended to start)

Runs on a free **GitHub Actions** cron (`.github/workflows/mimihelen.yml`).
No server needed.

1. Create a bot with [@BotFather](https://t.me/BotFather) → copy the token.
2. Get the friend's chat id (message [@userinfobot](https://t.me/userinfobot)).
3. In the repo: **Settings → Secrets and variables → Actions**
   - Secrets: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
   - Optional Variables: `MIMIHELEN_FRIEND_NAME`, `MIMIHELEN_TIMES`,
     `MIMIHELEN_TZ`, `MIMIHELEN_DAILY_GOAL`
4. The schedule fires automatically. To test now: **Actions → Mimi Helen Bot →
   Run workflow** (leave *force* on).

> The cron lines are in **UTC**; the defaults map to Singapore time. If you
> change `MIMIHELEN_TIMES`, update the cron lines in the workflow to match.

### 2. Interactive bot — `serve` mode

For the full experience (buttons, `/done` logging, `/streak`), run a small
long-lived process anywhere (a tiny VPS, a Raspberry Pi, a free dyno):

```bash
pip install -r requirements.txt
export TELEGRAM_BOT_TOKEN=... TELEGRAM_CHAT_ID=...
python -m mimihelen serve
```

Commands: `/done` `/today` `/streak` `/tip` `/schedule` `/help`.

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
