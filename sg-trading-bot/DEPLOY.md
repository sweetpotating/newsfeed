# Deployment guide — running sg-trading-bot 24/7

This covers the two things you asked about: a **VPS** to run it always-on, and a
**Telegram bot** for alerts. Plus the safe paper→live runway.

---

## Why a VPS?

A **VPS** (Virtual Private Server) is a small always-on cloud computer you rent
(~US$5–10/month). You need one because:

- The bot trades through **IB Gateway** (Interactive Brokers' lightweight API
  app), which must stay running and connected.
- A scheduled GitHub Action **cannot** reach IB Gateway — it has no access to
  your broker session. So execution can't live in CI.
- A VPS keeps Gateway + the bot running even when your laptop is off.

You could also use your own always-on PC or a Raspberry Pi — same idea. A VPS is
just the simplest reliable option.

**Region note:** pick a VPS region IBKR allows and that's reasonably close to
you (e.g. Singapore). Providers: DigitalOcean, Linode, Hetzner, AWS Lightsail.
A 2 GB RAM instance is plenty.

---

## One-time VPS setup

```bash
# 1. SSH into your VPS, then install Python + the bot
sudo apt update && sudo apt install -y python3-venv git
git clone <your-repo-url> && cd <repo>/sg-trading-bot
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt ib_async yfinance requests

# 2. Configure
cp .env.example .env
nano .env          # fill in the values from the table below
```

`.env` for live IBKR on the VPS:

```ini
SGTRADER_MODE=paper                 # keep PAPER until you've watched it run
SGTRADER_DATA_PROVIDER=ibkr
IBKR_HOST=127.0.0.1
IBKR_PORT=7497                      # TWS paper; IB Gateway paper = 4002
IBKR_CLIENT_ID=11
TELEGRAM_BOT_TOKEN=...              # see Telegram section below
TELEGRAM_CHAT_ID=...
```

### Running IB Gateway on the VPS

1. Install **IB Gateway** (headless-friendly) on the VPS. Many people use
   [IBC](https://github.com/IbcAlpha/IBC) to auto-start/login Gateway and keep
   it alive, plus a virtual display (`xvfb`) since Gateway has a GUI.
2. In Gateway: **Configure → API → Settings** → enable *ActiveX and Socket
   Clients*, set the socket port to match `IBKR_PORT`, and add `127.0.0.1` to
   trusted IPs.
3. Confirm the bot can see the account:
   ```bash
   python -m sgtrader status
   ```

---

## Scheduling the rebalance (cron)

Run once per weekday after the US close. On the VPS:

```bash
crontab -e
```
```cron
# 22:05 UTC, Mon–Fri — run a rebalance and log it
5 22 * * 1-5  cd /home/youruser/<repo>/sg-trading-bot && /home/youruser/<repo>/sg-trading-bot/.venv/bin/python -m sgtrader rebalance >> logs/rebalance.log 2>&1
```

The engine is idempotent, so a missed run self-heals on the next one.

---

## Telegram alerts

You'll get a message after each rebalance (orders placed) and a ⚠️ alert if the
drawdown circuit breaker trips.

1. In Telegram, message **@BotFather** → `/newbot` → follow prompts → it gives
   you a **bot token** like `123456:ABC-DEF...`.
2. Message your new bot once (say "hi") so it can message you back.
3. Get your **chat id**: open
   `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` in a browser and copy
   the `"chat":{"id": ...}` number. (Or message **@userinfobot**.)
4. Put both in `.env`:
   ```ini
   TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
   TELEGRAM_CHAT_ID=987654321
   ```
5. Test:
   ```bash
   python -c "from sgtrader.notifications import notify; notify('sg-trading-bot connected ✅')"
   ```

---

## The safe paper → live runway

Do these in order. **Don't skip steps.**

1. **Backtest** — sanity-check the logic and stats:
   ```bash
   python -m sgtrader backtest
   ```
2. **Paper, dry-run** — see exactly what orders it *would* place:
   ```bash
   python -m sgtrader rebalance --dry-run
   ```
3. **Paper, live orders against your IBKR paper account** — let it run on cron
   for **at least a few weeks**. Watch `state/last_run.json` and your Telegram
   alerts. Make sure fills, sizing, and the risk limits behave as you expect.
4. **Go live** — only when you're satisfied. On the VPS `.env`:
   ```ini
   SGTRADER_MODE=live
   SGTRADER_LIVE_CONFIRM=I UNDERSTAND THIS TRADES REAL MONEY
   IBKR_PORT=7496      # TWS live; IB Gateway live = 4001
   ```
   The bot **refuses** live orders unless both of those are set exactly. Start
   with a small balance you can afford to lose.

> **Reminder:** this automates discipline, not profit. Markets can fall; an
> "aggressive" profile can draw down hard. You are responsible for funding,
> monitoring, taxes (IRAS), and your IBKR agreement. Not financial advice.
