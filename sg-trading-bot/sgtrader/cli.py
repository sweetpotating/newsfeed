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
