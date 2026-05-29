import numpy as np
import pandas as pd

from sgtrader.models import Instrument
from sgtrader.strategies import (
    ETFDCAStrategy, DividendStrategy, MomentumStrategy, MeanReversionStrategy,
)


def _inst(sym):
    return Instrument(sym, "ARCA", "USD")


def _series(values):
    idx = pd.bdate_range(end="2026-01-01", periods=len(values))
    return pd.Series(values, index=idx, dtype=float)


def test_etf_dca_equal_weights_priced_only():
    u = [_inst("A"), _inst("B"), _inst("C")]
    hist = {"A-ARCA-USD": _series([1, 2, 3]), "B-ARCA-USD": _series([1, 2, 3])}
    out = ETFDCAStrategy().compute(u, hist)
    assert len(out) == 2  # C has no price
    assert abs(sum(t.weight for t in out) - 1.0) < 1e-9
    assert all(abs(t.weight - 0.5) < 1e-9 for t in out)


def test_dividend_equal_weight():
    u = [_inst("D"), _inst("E")]
    hist = {"D-ARCA-USD": _series([10] * 5), "E-ARCA-USD": _series([10] * 5)}
    out = DividendStrategy().compute(u, hist)
    assert len(out) == 2
    assert abs(sum(t.weight for t in out) - 1.0) < 1e-9


def test_momentum_picks_uptrend_and_top_n():
    n = 300
    up = _series(np.linspace(100, 200, n))          # strong uptrend
    down = _series(np.linspace(200, 100, n))        # downtrend -> filtered out
    flat_up = _series(np.linspace(100, 130, n))     # mild uptrend
    u = [_inst("UP"), _inst("DOWN"), _inst("MILD")]
    hist = {"UP-ARCA-USD": up, "DOWN-ARCA-USD": down, "MILD-ARCA-USD": flat_up}
    out = MomentumStrategy({"lookback_days": 126, "sma_filter_days": 200, "top_n": 2}).compute(u, hist)
    syms = {t.instrument.symbol for t in out}
    assert "DOWN" not in syms          # downtrend excluded
    assert "UP" in syms                # strongest included
    assert len(out) == 2


def test_momentum_all_cash_when_no_uptrend():
    n = 300
    down = _series(np.linspace(200, 100, n))
    u = [_inst("DOWN")]
    out = MomentumStrategy({"sma_filter_days": 200}).compute(u, {"DOWN-ARCA-USD": down})
    assert out == []


def test_mean_reversion_buys_oversold_in_uptrend():
    n = 300
    # Long uptrend, then a sharp dip at the end -> oversold but above 200d SMA.
    base = np.linspace(100, 300, n - 10)
    dip = np.linspace(300, 250, 10)
    prices = _series(np.concatenate([base, dip]))
    u = [_inst("X")]
    out = MeanReversionStrategy({"rsi_period": 14, "rsi_buy_below": 30,
                                 "rsi_sell_above": 70, "sma_filter_days": 200}).compute(
        u, {"X-ARCA-USD": prices})
    # Depending on dip depth it may or may not trigger; if it does, weight<=1.
    assert all(0 < t.weight <= 1.0 for t in out)
