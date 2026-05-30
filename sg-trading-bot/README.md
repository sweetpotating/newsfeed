# 📈 sg-trading-bot

A fully automated, **risk-managed, multi-strategy investing engine** for
**Interactive Brokers**, designed for a Singapore-based investor. It runs the
same logic in backtest, paper, and live modes; deploys capital across four
complementary strategy "sleeves"; enforces portfolio-level risk limits before
every order; and refuses to touch real money until you explicitly arm it.

> ### ⚠️ Read this first — honest expectations
> No software can *guarantee* or *maximise* investment returns — markets are
> uncertain and this bot is **not** financial advice. What it gives you is
> **discipline and automation**: a consistent, rules-based process with hard
> risk guardrails, so emotion and forgetfulness don't erode your plan. You can
> still lose money. **Start in paper mode, review the behaviour, and only go
> live with capital you can afford to risk.** You are responsible for tax
> (IRAS), regulatory, and brokerage-agreement compliance.

---

## Why four sleeves?

A "core-satellite" design that balances long-term compounding against tactical
opportunity. Capital is split by configurable weights (defaults in `config.yaml`):

| Sleeve | Default | Horizon | What it does |
|---|---|---|---|
| **ETF DCA** | 55% | Long | Equal-weight, low-cost broad-market ETFs — the compounding core. Defaults to Irish-domiciled **UCITS** ETFs (VWRA/CSPX/AGGG), which are generally tax-efficient for SG investors. |
| **Dividend** | 20% | Medium | Income/ballast basket (SGX blue chips D05/O39/U11 + US VYM). |
| **Momentum** | 15% | Short–Medium | Holds the strongest names *above their 200-day trend*; sits in cash in downtrends. |
| **Mean-reversion** | 10% | Short | Buys oversold (low-RSI) dips, but only inside a long-term uptrend. Smallest sleeve because it trades most. |

Each sleeve outputs target weights; the portfolio layer combines them, then the
**risk layer** clamps the result before any order is generated.

## Risk guardrails (applied to the *combined* portfolio)

All configurable under `risk:` in `config.yaml`:

- **Per-position cap** — no single holding exceeds 25% of equity.
- **Gross exposure cap + cash buffer** — no leverage; always keep ≥2% cash.
- **Minimum trade size** — skips trades below `$200` to avoid fee drag (also
  acts as a no-trade/drift band so the bot doesn't churn).
- **Turnover cap** — at most 35% of equity traded per run, so rebalances are
  gradual rather than all-at-once.
- **Drawdown circuit breaker** — if equity falls ≥20% below its trailing peak,
  the bot stops *adding* risk and only allows de-risking until it recovers.

---

## Architecture

```
config.yaml + .env
        │
        ▼
   ┌─────────┐   history   ┌──────────────┐  weights  ┌───────────┐
   │  data   │────────────▶│  strategies  │──────────▶│ portfolio │
   │provider │             │  (4 sleeves) │           │  combine  │
   └─────────┘             └──────────────┘           └─────┬─────┘
   synthetic|yfinance|ibkr                                  │ targets
                                                            ▼
   ┌──────────┐  fills   ┌────────────┐  orders   ┌───────────────┐
   │  broker  │◀─────────│   engine   │◀──────────│ risk manager  │
   │paper|IBKR│          │ (rebalance)│           │  (guardrails) │
   └──────────┘          └────────────┘           └───────────────┘
```

Everything upstream of the broker is **pure and offline-testable**. The broker
interface (`Broker`) has two implementations — `PaperBroker` (simulated fills)
and `IBKRBroker` (live via `ib_async`) — so the engine code is identical in all
modes. **What you backtest is exactly what you trade.**

```
sgtrader/
├── config.py          # loads config.yaml + .env; enforces the LIVE gate
├── models.py          # Instrument, Order, Position, Account, ...
├── indicators.py      # SMA, RSI, trailing return (no TA-Lib dependency)
├── data/              # market-data providers (synthetic | yfinance | ibkr)
├── broker/            # PaperBroker | IBKRBroker behind one interface
├── strategies/        # etf_dca, dividend, momentum, mean_reversion
├── portfolio.py       # combine sleeve targets
├── risk.py            # guardrails + order generation
├── engine.py          # one rebalance, end to end
├── backtest.py        # walk-forward sim using the same logic
└── cli.py             # `python -m sgtrader ...`
```

---

## Quick start (offline, zero setup)

```bash
cd sg-trading-bot
pip install -r requirements.txt        # core deps only
python -m pytest -q                    # 16 tests, fully offline

# These run with the built-in simulator + deterministic synthetic data —
# no account, no network, no secrets needed:
python -m sgtrader status
python -m sgtrader backtest --history-days 600 --rebalance-every 10
python -m sgtrader rebalance --dry-run   # prints the JSON of what it WOULD do
```

`rebalance` prints a machine-readable JSON report to **stdout** (logs go to
stderr), and writes the latest snapshot to `state/last_run.json`.

## Modes & the data provider

Set in `.env` (copy from `.env.example`):

- `SGTRADER_MODE`: `backtest` | `paper` | `live`
- `SGTRADER_DATA_PROVIDER`: `synthetic` (offline) | `yfinance` (free real data) | `ibkr`

```bash
pip install yfinance        # then set SGTRADER_DATA_PROVIDER=yfinance
```

## Connecting Interactive Brokers

1. `pip install ib_async`
2. Install and run **TWS** or **IB Gateway**, and enable the API
   (Settings → API → *Enable ActiveX and Socket Clients*).
3. Point `.env` at it — **paper** account first:
   ```
   IBKR_HOST=127.0.0.1
   IBKR_PORT=7497          # TWS paper (IB Gateway paper = 4002)
   IBKR_CLIENT_ID=11
   SGTRADER_DATA_PROVIDER=ibkr
   ```
   By default `paper` mode uses the **built-in simulator**. To instead route
   paper orders through your *IBKR paper* account, use the `IBKRBroker` (see
   `broker/__init__.py`) — handy for validating the real order path safely.

> **Note on cloud/CI:** a scheduled GitHub Actions run **cannot** reach a
> TWS/IB Gateway on your laptop. Run live/paper-IBKR on a machine where Gateway
> is running (your PC, a VPS, or a small always-on box). The included workflow
> defaults to the offline simulator so CI stays green without secrets.

## Going live (the deliberate, two-key gate)

Live orders are refused unless **both** are true:

1. `SGTRADER_MODE=live`, **and**
2. `SGTRADER_LIVE_CONFIRM="I UNDERSTAND THIS TRADES REAL MONEY"` (exact phrase).

This is intentional friction so live trading can never be enabled by accident.

```bash
# Recommended runway before real money:
python -m sgtrader backtest                 # 1. sanity-check the logic
python -m sgtrader rebalance --dry-run      # 2. paper sim: inspect orders
#   ... run paper for a while, review state/last_run.json ...
# 3. only then, on the machine running IB Gateway, set the two keys above.
```

## Scheduling

`.github/workflows/trade.yml` runs the test suite on every push and a **paper**
rebalance on a weekday schedule (offline/synthetic by default). For real
execution, schedule `python -m sgtrader rebalance` with `cron`/Task Scheduler on
the host running IB Gateway. The engine is **idempotent** — extra runs just
re-check drift, so frequent scheduling is safe.

👉 **Full always-on setup (VPS + IB Gateway + Telegram + the safe paper→live
runway) is in [`DEPLOY.md`](DEPLOY.md).**

## Notifications (optional)

Set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in `.env` to get a summary of
each rebalance and a ⚠️ alert when the drawdown breaker trips.

---

## Extracting into its own repository

This project is self-contained. To move it into a standalone repo:

```bash
# Option A — just copy the folder:
cp -r sg-trading-bot /path/to/new-repo && cd /path/to/new-repo && git init

# Option B — keep its git history with subtree split:
git subtree split --prefix=sg-trading-bot -b sg-trading-bot-standalone
```

## Configuration cheat-sheet

| File | Holds | Commit? |
|---|---|---|
| `config.yaml` | sleeve weights, universes, strategy params, risk limits | ✅ yes (no secrets) |
| `.env` | mode, IBKR connection, API keys, live confirmation | ❌ **never** |

Edit `config.yaml` to change what's traded and how much risk is taken — no code
changes required.

---

*Not investment advice. Use at your own risk. Test in paper mode first.*
