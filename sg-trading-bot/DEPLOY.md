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

### What to buy

The bot itself is tiny; the spec is driven by **IB Gateway** (a Java GUI app
that must stay running 24/7). Memory is the thing that matters — an
under-provisioned box gets its Gateway OOM-killed and silently disconnects.

| Resource | Minimum | Recommended | Why |
|---|---|---|---|
| RAM | 2 GB | **4 GB** | Gateway + Java + xvfb use ~1.5–2 GB idle |
| vCPU | 1 | 2 | Gateway idles; rebalance is a daily burst |
| Disk | 25 GB SSD | 40 GB | OS + Java + logs |
| OS | Ubuntu 22.04/24.04 LTS | same | best-documented for IBC/Gateway |
| Region | — | **Singapore** | close for management; daily trading isn't latency-sensitive |

**Recommended pick: 2 vCPU / 4 GB RAM, Ubuntu 24.04 LTS, Singapore region** —
~US$20–24/mo on **DigitalOcean** (SGP1) or **Vultr**. AWS Lightsail and
Linode/Akamai also have SG regions at similar prices.

**Free option:** Oracle Cloud's *Always Free* ARM (4 vCPU / 24 GB, SG region) is
capable, but it's ARM and Oracle can reclaim idle free instances — fine for
paper testing, not ideal for a live trading connection. Move to a paid box
before going live.

**Don't:** use a 1 GB box (Gateway will OOM), or try to run on serverless /
GitHub Actions (Gateway needs a persistent process).

---

## One-time VPS setup

A bootstrap script does the heavy lifting (Python + bot + Java + xvfb + IBC):

```bash
# SSH into your VPS, then:
sudo apt update && sudo apt install -y git
git clone <your-repo-url> && cd <repo>/sg-trading-bot
bash scripts/bootstrap.sh        # installs everything; creates .env from template
nano .env                        # fill in the values from the table below
```

The script prints the remaining steps that need *your* credentials (installing
IB Gateway, IBC login, ports).

`.env` for IBKR paper-then-live on the VPS:

```ini
SGTRADER_MODE=paper                 # keep PAPER until you've watched it run
SGTRADER_PAPER_BROKER=ibkr          # route paper orders to your IBKR paper acct
SGTRADER_DATA_PROVIDER=ibkr
IBKR_HOST=127.0.0.1
IBKR_PORT=4002                      # IB Gateway paper; TWS paper = 7497
IBKR_CLIENT_ID=11
TELEGRAM_BOT_TOKEN=...              # see Telegram section below
TELEGRAM_CHAT_ID=...
```

> Setting `SGTRADER_PAPER_BROKER=ibkr` makes paper mode use the **exact same
> live order path** as real trading, against your IBKR *paper* account — the
> best possible dress rehearsal, with zero money at risk.

### Running IB Gateway on the VPS

1. Install **IB Gateway** (headless-friendly) on the VPS. Many people use
   [IBC](https://github.com/IbcAlpha/IBC) to auto-start/login Gateway and keep
   it alive, plus a virtual display (`xvfb`) since Gateway has a GUI.
2. In Gateway: **Configure → API → Settings** → enable *ActiveX and Socket
   Clients*, set the socket port to match `IBKR_PORT`, and add `127.0.0.1` to
   trusted IPs.
3. Confirm the bot can see the account and everything is wired:
   ```bash
   source .venv/bin/activate
   python -m sgtrader doctor      # ✅/❌ checklist: config, data, broker, alerts
   python -m sgtrader status      # shows your live account snapshot
   ```

---

## Scheduling the rebalance (systemd)

Use the provided units (more robust than cron — handles missed runs and logs to
the journal). Edit the `User`/paths in `scripts/sgtrader.service` first, then:

```bash
sudo cp scripts/sgtrader.service /etc/systemd/system/
sudo cp scripts/sgtrader.timer   /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now sgtrader.timer

systemctl list-timers sgtrader.timer    # confirm the next run time
journalctl -u sgtrader.service -f        # watch run logs
```

Default schedule is **weekdays 22:05 UTC** (just after the US close). The engine
is idempotent, so a missed run self-heals on the next one.

Prefer cron? This one-liner is equivalent:
```cron
5 22 * * 1-5  cd /path/sg-trading-bot && .venv/bin/python -m sgtrader rebalance >> logs/rebalance.log 2>&1
```

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
