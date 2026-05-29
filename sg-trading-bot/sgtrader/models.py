"""Plain data structures shared across the system.

These are deliberately simple dataclasses with no behaviour, so they serialise
cleanly to state files and are trivial to construct in tests.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Optional


class Mode(str, Enum):
    """Execution mode, in increasing order of consequence."""
    BACKTEST = "backtest"
    PAPER = "paper"
    LIVE = "live"


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


@dataclass(frozen=True)
class Instrument:
    """A tradable instrument, identified the IBKR way (symbol/exchange/currency)."""
    symbol: str
    exchange: str
    currency: str
    name: str = ""

    @property
    def key(self) -> str:
        """Stable dictionary key, e.g. 'SPY-ARCA-USD'."""
        return f"{self.symbol}-{self.exchange}-{self.currency}"

    @classmethod
    def from_dict(cls, d: dict) -> "Instrument":
        return cls(
            symbol=d["symbol"],
            exchange=d["exchange"],
            currency=d["currency"],
            name=d.get("name", ""),
        )


@dataclass
class Position:
    instrument: Instrument
    quantity: float
    avg_cost: float = 0.0
    market_price: float = 0.0

    @property
    def market_value(self) -> float:
        return self.quantity * self.market_price


@dataclass
class Account:
    """A snapshot of broker state at one moment, in base currency."""
    cash: float
    positions: dict[str, Position] = field(default_factory=dict)
    base_currency: str = "USD"

    @property
    def positions_value(self) -> float:
        return sum(p.market_value for p in self.positions.values())

    @property
    def equity(self) -> float:
        """Total liquidation value = cash + marked-to-market positions."""
        return self.cash + self.positions_value


@dataclass
class Order:
    instrument: Instrument
    side: Side
    quantity: float
    # Reference price at decision time (for value/fee estimates and logging).
    ref_price: float = 0.0
    reason: str = ""

    @property
    def value(self) -> float:
        return abs(self.quantity) * self.ref_price


@dataclass
class Fill:
    order: Order
    fill_price: float
    fill_quantity: float
    commission: float = 0.0
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class TargetWeight:
    """A strategy's desired exposure to an instrument, as a fraction of the
    *whole portfolio's* equity (after the sleeve weight has been applied)."""
    instrument: Instrument
    weight: float
    reason: str = ""


def to_jsonable(obj):
    """Best-effort conversion of our dataclasses/enums to JSON-friendly types."""
    if isinstance(obj, Enum):
        return obj.value
    if hasattr(obj, "__dataclass_fields__"):
        return {k: to_jsonable(v) for k, v in asdict(obj).items()}
    if isinstance(obj, dict):
        return {k: to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(v) for v in obj]
    if isinstance(obj, datetime):
        return obj.isoformat()
    return obj
