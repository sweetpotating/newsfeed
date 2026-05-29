"""A simulated broker for backtests and paper trading.

It keeps an in-memory account, fills orders immediately at the reference price
(with a configurable commission + slippage), and persists/loads state so a
paper account survives across scheduled runs.
"""
from __future__ import annotations

import json
from pathlib import Path

from ..logging_config import get_logger
from ..models import Account, Fill, Instrument, Order, Position, Side, to_jsonable
from .base import Broker

log = get_logger("broker.paper")


class PaperBroker(Broker):
    def __init__(
        self,
        starting_cash: float = 100_000,
        base_currency: str = "USD",
        market_data=None,
        commission_per_trade: float = 1.0,
        commission_pct: float = 0.0005,
        slippage_pct: float = 0.0005,
        state_path: str | Path | None = "state/paper_account.json",
    ):
        self._account = Account(cash=starting_cash, base_currency=base_currency)
        self._market_data = market_data
        self._commission_per_trade = commission_per_trade
        self._commission_pct = commission_pct
        self._slippage_pct = slippage_pct
        self._state_path = Path(state_path) if state_path else None
        self._price_cache: dict[str, float] = {}

    # ── lifecycle ────────────────────────────────────────────────────────────
    def connect(self) -> None:
        self._load_state()
        log.info(
            "Paper broker ready. Equity=%.2f %s (cash=%.2f, %d positions)",
            self._account.equity, self._account.base_currency,
            self._account.cash, len(self._account.positions),
        )

    def disconnect(self) -> None:
        self._save_state()

    # ── data ─────────────────────────────────────────────────────────────────
    def get_account(self) -> Account:
        # Re-mark positions to the latest known price before reporting.
        for pos in self._account.positions.values():
            pos.market_price = self.get_price(pos.instrument)
        return self._account

    def get_price(self, instrument: Instrument) -> float:
        if self._market_data is not None:
            prices = self._market_data.latest_prices([instrument])
            if instrument.key in prices:
                self._price_cache[instrument.key] = prices[instrument.key]
        return self._price_cache.get(instrument.key, 0.0)

    def set_price(self, instrument: Instrument, price: float) -> None:
        """Used by the backtester to advance the simulated market."""
        self._price_cache[instrument.key] = price

    # ── execution ──────────────────────────────────────────────────────────
    def place_order(self, order: Order) -> Fill:
        ref = order.ref_price or self.get_price(order.instrument)
        if ref <= 0:
            raise ValueError(f"No price available for {order.instrument.key}")

        # Slippage works against us: buys fill a touch higher, sells a touch lower.
        if order.side is Side.BUY:
            fill_price = ref * (1 + self._slippage_pct)
        else:
            fill_price = ref * (1 - self._slippage_pct)

        qty = abs(order.quantity)
        gross = qty * fill_price
        commission = self._commission_per_trade + gross * self._commission_pct

        key = order.instrument.key
        pos = self._account.positions.get(key)

        if order.side is Side.BUY:
            self._account.cash -= gross + commission
            if pos is None:
                pos = Position(order.instrument, 0.0, 0.0, fill_price)
                self._account.positions[key] = pos
            new_qty = pos.quantity + qty
            pos.avg_cost = (pos.avg_cost * pos.quantity + gross) / new_qty if new_qty else 0.0
            pos.quantity = new_qty
            pos.market_price = fill_price
        else:  # SELL
            self._account.cash += gross - commission
            if pos is not None:
                pos.quantity -= qty
                pos.market_price = fill_price
                if abs(pos.quantity) < 1e-9:
                    del self._account.positions[key]

        log.info(
            "FILL %s %.4f %s @ %.4f (comm %.2f) — %s",
            order.side.value, qty, order.instrument.symbol, fill_price,
            commission, order.reason,
        )
        return Fill(order=order, fill_price=fill_price, fill_quantity=qty, commission=commission)

    # ── state persistence ──────────────────────────────────────────────────
    def _save_state(self) -> None:
        if not self._state_path:
            return
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "cash": self._account.cash,
            "base_currency": self._account.base_currency,
            "positions": {
                k: {
                    "instrument": to_jsonable(p.instrument),
                    "quantity": p.quantity,
                    "avg_cost": p.avg_cost,
                    "market_price": p.market_price,
                }
                for k, p in self._account.positions.items()
            },
        }
        self._state_path.write_text(json.dumps(payload, indent=2))

    def _load_state(self) -> None:
        if not self._state_path or not self._state_path.exists():
            return
        data = json.loads(self._state_path.read_text())
        self._account.cash = data["cash"]
        self._account.base_currency = data.get("base_currency", "USD")
        self._account.positions = {}
        for k, p in data.get("positions", {}).items():
            inst = Instrument.from_dict(p["instrument"])
            self._account.positions[k] = Position(
                inst, p["quantity"], p.get("avg_cost", 0.0), p.get("market_price", 0.0)
            )
            self._price_cache[k] = p.get("market_price", 0.0)
