"""Interactive Brokers execution adapter (via ib_async / TWS / IB Gateway).

This is the only module that talks to real money, and only in LIVE mode after
the confirmation gate in config.py has passed. It is written against `ib_async`
(the maintained successor to ib_insync). `ib_async` is imported lazily so the
rest of the system installs and runs without it.

Because this environment has no IB Gateway to connect to, this adapter is
structured for correctness and clarity; validate it against your own IBKR
*paper* account (port 7497) before ever pointing it at a funded one.
"""
from __future__ import annotations

import pandas as pd

from ..logging_config import get_logger
from ..models import Account, Fill, Instrument, Order, Position, Side
from .base import Broker

log = get_logger("broker.ibkr")


class IBKRBroker(Broker):
    def __init__(self, config):
        self._cfg = config
        self._ib = None  # set on connect()

    def connect(self) -> None:
        try:
            from ib_async import IB
        except ImportError as e:
            raise ImportError(
                "ib_async is required for live IBKR trading. Install it with "
                "`pip install ib_async` and run TWS or IB Gateway with the API enabled."
            ) from e

        self._ib = IB()
        c = self._cfg.ibkr
        log.info("Connecting to IBKR at %s:%s (clientId=%s)…", c.host, c.port, c.client_id)
        self._ib.connect(c.host, c.port, clientId=c.client_id, timeout=15)
        log.info("Connected to IBKR. Server time: %s", self._ib.reqCurrentTime())

    def disconnect(self) -> None:
        if self._ib is not None and self._ib.isConnected():
            self._ib.disconnect()

    # ── contract helpers ─────────────────────────────────────────────────────
    def _contract(self, inst: Instrument):
        from ib_async import Stock

        # SMART routing with a primary exchange hint gives the best fills while
        # still disambiguating the listing.
        primary = inst.exchange
        return Stock(inst.symbol, "SMART", inst.currency, primaryExchange=primary)

    # ── account / pricing ────────────────────────────────────────────────────
    def get_account(self) -> Account:
        assert self._ib is not None
        summary = {v.tag: v for v in self._ib.accountSummary()}
        base = self._cfg.base_currency
        cash = float(summary.get("TotalCashValue").value) if "TotalCashValue" in summary else 0.0

        positions: dict[str, Position] = {}
        for p in self._ib.positions():
            con = p.contract
            inst = Instrument(con.symbol, con.primaryExchange or con.exchange, con.currency)
            price = self.get_price(inst) or float(p.avgCost)
            positions[inst.key] = Position(
                inst, float(p.position), float(p.avgCost), price
            )
        return Account(cash=cash, positions=positions, base_currency=base)

    def get_price(self, instrument: Instrument) -> float:
        assert self._ib is not None
        contract = self._contract(instrument)
        self._ib.qualifyContracts(contract)
        ticker = self._ib.reqMktData(contract, "", snapshot=True)
        self._ib.sleep(1.5)
        for px in (ticker.last, ticker.close, ticker.marketPrice()):
            if px and px == px and px > 0:  # not NaN, positive
                return float(px)
        return 0.0

    def historical_closes(self, instruments: list[Instrument], lookback_days: int) -> dict[str, pd.Series]:
        assert self._ib is not None
        out: dict[str, pd.Series] = {}
        duration = f"{max(lookback_days + 10, 30)} D"
        for inst in instruments:
            contract = self._contract(inst)
            self._ib.qualifyContracts(contract)
            bars = self._ib.reqHistoricalData(
                contract, endDateTime="", durationStr=duration,
                barSizeSetting="1 day", whatToShow="TRADES", useRTH=True,
            )
            if not bars:
                continue
            idx = pd.to_datetime([b.date for b in bars])
            out[inst.key] = pd.Series([b.close for b in bars], index=idx, name=inst.key)
        return out

    # ── execution ──────────────────────────────────────────────────────────
    def place_order(self, order: Order) -> Fill:
        assert self._ib is not None
        from ib_async import MarketOrder

        contract = self._contract(order.instrument)
        self._ib.qualifyContracts(contract)
        action = "BUY" if order.side is Side.BUY else "SELL"
        ib_order = MarketOrder(action, abs(order.quantity))
        trade = self._ib.placeOrder(contract, ib_order)
        log.info("LIVE order submitted: %s %s %s", action, abs(order.quantity), order.instrument.symbol)

        # Wait for the order to reach a terminal state.
        while not trade.isDone():
            self._ib.waitOnUpdate(timeout=5)

        fills = trade.fills
        fill_price = fills[-1].execution.price if fills else (order.ref_price or 0.0)
        filled_qty = sum(f.execution.shares for f in fills) if fills else 0.0
        commission = sum(
            f.commissionReport.commission for f in fills if f.commissionReport
        ) if fills else 0.0
        return Fill(order=order, fill_price=float(fill_price),
                    fill_quantity=float(filled_qty), commission=float(commission))
