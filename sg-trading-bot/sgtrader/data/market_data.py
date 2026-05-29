"""Market-data providers behind one interface.

A provider's job is to return daily closing-price history for a set of
instruments. Strategies consume that history; they don't care where it came
from. Three implementations:

  * SyntheticDataProvider — deterministic geometric-Brownian-motion prices.
    Needs no network/account, so the whole engine runs offline and tests are
    reproducible.
  * YFinanceProvider — free daily bars via the optional `yfinance` package.
  * IBKRDataProvider — historical bars from a connected IB Gateway/TWS.
"""
from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from ..logging_config import get_logger
from ..models import Instrument

log = get_logger("data")


class MarketDataProvider(ABC):
    @abstractmethod
    def history(self, instruments: list[Instrument], lookback_days: int) -> dict[str, pd.Series]:
        """Return {instrument.key: Series of daily closes indexed by date}."""

    def latest_prices(self, instruments: list[Instrument]) -> dict[str, float]:
        """Most recent close per instrument. Default: derived from history()."""
        hist = self.history(instruments, lookback_days=5)
        out: dict[str, float] = {}
        for inst in instruments:
            s = hist.get(inst.key)
            if s is not None and len(s.dropna()) > 0:
                out[inst.key] = float(s.dropna().iloc[-1])
        return out


class SyntheticDataProvider(MarketDataProvider):
    """Deterministic synthetic prices — same symbol always yields the same path,
    so behaviour is reproducible across runs and in CI."""

    def __init__(self, annual_drift: float = 0.07, annual_vol: float = 0.18):
        self.drift = annual_drift
        self.vol = annual_vol

    def _seed(self, key: str) -> int:
        return int(hashlib.sha256(key.encode()).hexdigest(), 16) % (2**32)

    def history(self, instruments: list[Instrument], lookback_days: int) -> dict[str, pd.Series]:
        n = max(lookback_days, 250) + 5
        end = datetime.utcnow().date()
        # Business-day index ending today.
        idx = pd.bdate_range(end=end, periods=n)
        dt = 1.0 / 252.0
        out: dict[str, pd.Series] = {}
        for inst in instruments:
            rng = np.random.default_rng(self._seed(inst.key))
            start_price = 50.0 + (self._seed(inst.key) % 200)
            shocks = rng.normal(
                (self.drift - 0.5 * self.vol**2) * dt,
                self.vol * np.sqrt(dt),
                size=len(idx),
            )
            path = start_price * np.exp(np.cumsum(shocks))
            out[inst.key] = pd.Series(path, index=idx, name=inst.key)
        return out


class YFinanceProvider(MarketDataProvider):
    """Daily bars via yfinance. Maps IBKR-style instruments to Yahoo tickers."""

    # Yahoo suffixes for the exchanges we use.
    _SUFFIX = {"SGX": ".SI", "LSEETF": ".L", "LSE": ".L"}

    def __init__(self):
        try:
            import yfinance  # noqa: F401
        except ImportError as e:
            raise ImportError(
                "yfinance is required for the yfinance data provider. "
                "Install it with `pip install yfinance`, or set "
                "SGTRADER_DATA_PROVIDER=synthetic for offline use."
            ) from e

    def _yahoo_symbol(self, inst: Instrument) -> str:
        return inst.symbol + self._SUFFIX.get(inst.exchange, "")

    def history(self, instruments: list[Instrument], lookback_days: int) -> dict[str, pd.Series]:
        import yfinance as yf

        # Pad calendar days to cover non-trading days within the lookback window.
        period_days = int(lookback_days * 1.6) + 10
        start = (datetime.utcnow() - timedelta(days=period_days)).strftime("%Y-%m-%d")
        out: dict[str, pd.Series] = {}
        for inst in instruments:
            ysym = self._yahoo_symbol(inst)
            try:
                df = yf.download(ysym, start=start, progress=False, auto_adjust=True)
                if df is None or df.empty:
                    log.warning("No yfinance data for %s (%s)", inst.key, ysym)
                    continue
                close = df["Close"]
                if isinstance(close, pd.DataFrame):  # multiindex edge case
                    close = close.iloc[:, 0]
                out[inst.key] = close.rename(inst.key)
            except Exception as e:  # noqa: BLE001
                log.warning("yfinance fetch failed for %s: %s", inst.key, e)
        return out


class IBKRDataProvider(MarketDataProvider):
    """Historical daily bars from a connected IB Gateway / TWS via ib_async."""

    def __init__(self, broker):
        # Reuses an already-connected IBKRBroker so we share one IB session.
        self._broker = broker

    def history(self, instruments: list[Instrument], lookback_days: int) -> dict[str, pd.Series]:
        return self._broker.historical_closes(instruments, lookback_days)


def get_provider(name: str, broker=None) -> MarketDataProvider:
    name = (name or "synthetic").lower()
    if name == "synthetic":
        return SyntheticDataProvider()
    if name == "yfinance":
        return YFinanceProvider()
    if name == "ibkr":
        if broker is None:
            raise ValueError("IBKR data provider needs a connected broker.")
        return IBKRDataProvider(broker)
    raise ValueError(f"Unknown data provider: {name!r}")
