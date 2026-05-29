"""The rebalance engine — one run of the full automated flow.

    load config ─▶ build strategies ─▶ fetch history ─▶ compute sleeve targets
    ─▶ combine ─▶ snapshot account ─▶ apply risk ─▶ generate orders
    ─▶ execute (unless dry-run) ─▶ persist + report + notify

The engine is idempotent: running it again when nothing has drifted produces no
orders. That makes it safe to schedule frequently.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .broker import get_broker
from .config import Config
from .data import get_provider
from .logging_config import get_logger
from .models import Instrument, Mode, to_jsonable
from .notifications import notify
from .portfolio import combine_targets
from .risk import RiskManager, RiskState
from .strategies import STRATEGY_REGISTRY

log = get_logger("engine")

_RISK_STATE_PATH = Path("state/risk_state.json")


class Engine:
    def __init__(self, config: Config, broker=None, market_data=None):
        self.cfg = config
        self.risk = RiskManager(config.risk)
        # The data provider may need the broker (for the 'ibkr' provider), so
        # build the broker first, then the provider, then hand data to broker.
        self.broker = broker
        self.market_data = market_data

    # ── lifecycle helpers ────────────────────────────────────────────────────
    def _ensure_wiring(self):
        if self.broker is None:
            # For the ibkr data provider we must connect the broker first.
            if self.cfg.data_provider == "ibkr" and self.cfg.mode is Mode.LIVE:
                self.broker = get_broker(self.cfg)
                self.broker.connect()
                self.market_data = get_provider("ibkr", broker=self.broker)
            else:
                self.market_data = self.market_data or get_provider(self.cfg.data_provider)
                self.broker = get_broker(self.cfg, market_data=self.market_data)
                self.broker.connect()
        elif self.market_data is None:
            self.market_data = get_provider(self.cfg.data_provider)

    def _all_instruments(self) -> list[Instrument]:
        seen: dict[str, Instrument] = {}
        for sleeve in self.cfg.enabled_sleeves():
            for inst in self.cfg.universes.get(sleeve, []):
                seen[inst.key] = inst
        return list(seen.values())

    # ── the run ──────────────────────────────────────────────────────────────
    def run(self, dry_run: bool = False) -> dict:
        self._ensure_wiring()
        sleeve_weights = self.cfg.enabled_sleeves()
        if not sleeve_weights:
            raise RuntimeError("No sleeves enabled in config; nothing to do.")

        # 1. History for the whole universe (deep enough for the slowest filter).
        instruments = self._all_instruments()
        max_lookback = self._max_lookback()
        history = self.market_data.history(instruments, lookback_days=max_lookback)

        # 2. Run each enabled sleeve.
        sleeve_outputs: dict[str, list] = {}
        for sleeve in sleeve_weights:
            strat_cls = STRATEGY_REGISTRY[sleeve]
            strat = strat_cls(self.cfg.strategy_params.get(sleeve, {}))
            universe = self.cfg.universes.get(sleeve, [])
            sleeve_outputs[sleeve] = strat.compute(universe, history)
            log.info("Sleeve %-15s -> %d target(s)", sleeve, len(sleeve_outputs[sleeve]))

        # 3. Combine into one portfolio target.
        targets = combine_targets(sleeve_weights, sleeve_outputs)

        # 4. Snapshot account + prices.
        account = self.broker.get_account()
        prices: dict[str, float] = {}
        for key in set(list(targets) + list(account.positions)):
            inst = targets[key].instrument if key in targets else account.positions[key].instrument
            prices[key] = self.broker.get_price(inst)

        # 5. Risk -> orders.
        risk_state = self._load_risk_state()
        orders, diag = self.risk.build_orders(account, targets, prices, risk_state)

        # 6. Execute (unless dry-run or backtest-without-broker).
        fills = []
        if not dry_run and self.cfg.mode is not Mode.BACKTEST:
            for order in orders:
                try:
                    fills.append(self.broker.place_order(order))
                except Exception as e:  # noqa: BLE001
                    log.error("Order failed for %s: %s", order.instrument.symbol, e)
        else:
            log.info("DRY-RUN: %d order(s) computed but not sent.", len(orders))

        self._save_risk_state(risk_state)

        report = self._build_report(account, targets, orders, fills, diag, dry_run)
        self._persist_report(report)
        self._notify(report)
        return report

    # ── helpers ────────────────────────────────────────────────────────────
    def _max_lookback(self) -> int:
        candidates = [260]
        for params in self.cfg.strategy_params.values():
            for k in ("lookback_days", "sma_filter_days", "rsi_period"):
                if k in params:
                    candidates.append(int(params[k]) + 30)
        return max(candidates)

    def _load_risk_state(self) -> RiskState:
        if _RISK_STATE_PATH.exists():
            try:
                d = json.loads(_RISK_STATE_PATH.read_text())
                return RiskState(peak_equity=float(d.get("peak_equity", 0.0)))
            except Exception:  # noqa: BLE001
                pass
        return RiskState()

    def _save_risk_state(self, state: RiskState) -> None:
        _RISK_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _RISK_STATE_PATH.write_text(json.dumps({"peak_equity": state.peak_equity}, indent=2))

    def _build_report(self, account, targets, orders, fills, diag, dry_run) -> dict:
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "mode": self.cfg.mode.value,
            "dry_run": dry_run,
            "equity": round(account.equity, 2),
            "cash": round(account.cash, 2),
            "positions": {
                k: {"symbol": p.instrument.symbol, "qty": round(p.quantity, 4),
                    "value": round(p.market_value, 2)}
                for k, p in account.positions.items()
            },
            "targets": {k: {"symbol": t.instrument.symbol, "weight": round(t.weight, 4)}
                        for k, t in targets.items()},
            "orders": [to_jsonable(o) for o in orders],
            "fills": [to_jsonable(f) for f in fills],
            "risk": diag,
        }

    def _persist_report(self, report: dict) -> None:
        path = Path("state/last_run.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2, default=str))

    def _notify(self, report: dict) -> None:
        n_orders = len(report["orders"])
        if n_orders == 0 and not report["risk"].get("halted"):
            return
        lines = [
            f"*sg-trading-bot* ({report['mode']}{' / DRY' if report['dry_run'] else ''})",
            f"Equity: {report['equity']:.2f}  Cash: {report['cash']:.2f}",
            f"Orders: {n_orders}",
        ]
        for o in report["orders"][:10]:
            lines.append(f"  {o['side']} {o['quantity']:.2f} {o['instrument']['symbol']}")
        if report["risk"].get("halted"):
            lines.append("⚠️ Drawdown circuit breaker active (de-risk only).")
        notify("\n".join(lines))

    def close(self):
        if self.broker is not None:
            self.broker.disconnect()
