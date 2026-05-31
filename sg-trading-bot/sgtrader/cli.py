"""Command-line entrypoint.

    python -m sgtrader status                 # show account + config, no trading
    python -m sgtrader rebalance [--dry-run]  # run one rebalance (mode from .env)
    python -m sgtrader backtest [--start ...] # historical simulation
"""
from __future__ import annotations

import argparse
import json
import sys

from .config import load_config
from .engine import Engine
from .logging_config import setup_logging
from .models import Mode


def _cmd_status(args) -> int:
    log = setup_logging()
    cfg = load_config(args.config, args.env)
    engine = Engine(cfg)
    engine._ensure_wiring()
    account = engine.broker.get_account()
    print(f"\nMode:            {cfg.mode.value}")
    print(f"Data provider:   {cfg.data_provider}")
    print(f"Base currency:   {cfg.base_currency}")
    print(f"Enabled sleeves: {cfg.enabled_sleeves()}")
    print(f"\nEquity:          {account.equity:,.2f} {cfg.base_currency}")
    print(f"Cash:            {account.cash:,.2f}")
    print(f"Positions:       {len(account.positions)}")
    for p in account.positions.values():
        print(f"  {p.instrument.symbol:8s} qty={p.quantity:>10.4f}  value={p.market_value:>12.2f}")
    engine.close()
    return 0


def _cmd_doctor(args) -> int:
    """Preflight checks: config, data provider, broker, notifications.

    Run this on the VPS before trusting the bot. Exit code is non-zero if any
    critical check fails.
    """
    import os

    setup_logging()
    checks: list[tuple[str, bool, str]] = []  # (label, ok, detail)

    # 1. Config + live gate.
    try:
        cfg = load_config(args.config, args.env)
        checks.append(("Config loads", True, f"mode={cfg.mode.value}, sleeves={list(cfg.enabled_sleeves())}"))
    except Exception as e:  # noqa: BLE001
        checks.append(("Config loads", False, str(e)))
        _print_checks(checks)
        return 1

    # 2. Optional deps relevant to the chosen providers.
    paper_via_ibkr = os.getenv("SGTRADER_PAPER_BROKER", "simulator").lower() == "ibkr"
    needs_ibkr = cfg.mode is Mode.LIVE or paper_via_ibkr or cfg.data_provider == "ibkr"
    if needs_ibkr:
        try:
            import ib_async  # noqa: F401
            checks.append(("ib_async installed", True, "ok"))
        except ImportError:
            checks.append(("ib_async installed", False, "pip install ib_async"))
    if cfg.data_provider == "yfinance":
        try:
            import yfinance  # noqa: F401
            checks.append(("yfinance installed", True, "ok"))
        except ImportError:
            checks.append(("yfinance installed", False, "pip install yfinance"))

    # 3. Market data reachable.
    try:
        engine = Engine(cfg)
        engine.market_data = None
        from .data import get_provider
        provider = get_provider(cfg.data_provider) if cfg.data_provider != "ibkr" else None
        if provider is not None:
            sample = cfg.universes[next(iter(cfg.enabled_sleeves()))][:1]
            hist = provider.history(sample, lookback_days=30)
            ok = bool(hist) and all(len(s.dropna()) > 0 for s in hist.values())
            checks.append((f"Data provider '{cfg.data_provider}'", ok,
                           f"{len(hist)} series" if ok else "no data returned"))
        else:
            checks.append(("Data provider 'ibkr'", True, "validated via broker connect below"))
    except Exception as e:  # noqa: BLE001
        checks.append((f"Data provider '{cfg.data_provider}'", False, str(e)))

    # 4. Broker connectivity (real connect only if IBKR is involved).
    if needs_ibkr and (cfg.mode is Mode.LIVE or paper_via_ibkr):
        try:
            from .broker import get_broker
            broker = get_broker(cfg)
            broker.connect()
            acct = broker.get_account()
            broker.disconnect()
            checks.append(("IBKR connection", True,
                           f"equity={acct.equity:.2f} {cfg.base_currency}, {len(acct.positions)} positions"))
        except Exception as e:  # noqa: BLE001
            checks.append(("IBKR connection", False, str(e)))
    else:
        checks.append(("Broker", True, "simulator (no external connection needed)"))

    # 5. Notifications.
    tg = bool(os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_ID"))
    checks.append(("Telegram configured", tg, "ok" if tg else "optional — set TOKEN + CHAT_ID to enable"))

    all_ok = _print_checks(checks)
    # Telegram is optional, so don't fail the whole preflight just for it.
    critical_ok = all(ok for label, ok, _ in checks if label != "Telegram configured")
    return 0 if critical_ok else 1


def _print_checks(checks) -> bool:
    print("\nsg-trading-bot preflight")
    print("─" * 60)
    all_ok = True
    for label, ok, detail in checks:
        mark = "✅" if ok else "❌"
        all_ok = all_ok and ok
        print(f"  {mark}  {label:28s} {detail}")
    print("─" * 60)
    return all_ok


def _cmd_rebalance(args) -> int:
    log = setup_logging()
    cfg = load_config(args.config, args.env)
    if cfg.mode is Mode.LIVE and not args.dry_run:
        log.warning("⚠️  LIVE mode — this will place REAL orders on a funded account.")
    engine = Engine(cfg)
    try:
        report = engine.run(dry_run=args.dry_run)
    finally:
        engine.close()
    print(json.dumps(report, indent=2, default=str))
    return 0


def _cmd_backtest(args) -> int:
    setup_logging()
    from .backtest import run_backtest

    cfg = load_config(args.config, args.env)
    result = run_backtest(
        cfg, start=args.start, history_days=args.history_days,
        rebalance_every=args.rebalance_every, starting_cash=args.cash,
    )
    print("\n=== Backtest summary ===")
    print(json.dumps(result.stats, indent=2))
    if args.out:
        result.equity_curve.to_csv(args.out, header=["equity"])
        print(f"\nEquity curve written to {args.out}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="sgtrader", description="Automated multi-strategy investing for IBKR.")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--env", default=".env")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="Show account + config (no trading).").set_defaults(func=_cmd_status)
    sub.add_parser("doctor", help="Preflight checks (config, data, broker, alerts).").set_defaults(func=_cmd_doctor)

    p_reb = sub.add_parser("rebalance", help="Run one rebalance.")
    p_reb.add_argument("--dry-run", action="store_true", help="Compute orders but do not send them.")
    p_reb.set_defaults(func=_cmd_rebalance)

    p_bt = sub.add_parser("backtest", help="Historical simulation.")
    p_bt.add_argument("--start", default=None, help="Start date YYYY-MM-DD.")
    p_bt.add_argument("--history-days", type=int, default=750)
    p_bt.add_argument("--rebalance-every", type=int, default=5, help="Rebalance every N bars.")
    p_bt.add_argument("--cash", type=float, default=100_000.0)
    p_bt.add_argument("--out", default=None, help="Write equity curve CSV here.")
    p_bt.set_defaults(func=_cmd_backtest)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
