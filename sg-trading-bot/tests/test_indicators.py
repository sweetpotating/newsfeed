import numpy as np
import pandas as pd

from sgtrader import indicators


def test_sma_basic():
    s = pd.Series([1, 2, 3, 4, 5], dtype=float)
    out = indicators.sma(s, 2)
    assert np.isnan(out.iloc[0])
    assert out.iloc[1] == 1.5
    assert out.iloc[-1] == 4.5


def test_rsi_all_gains_is_100():
    s = pd.Series(np.arange(1, 40), dtype=float)  # monotonically rising
    r = indicators.rsi(s, 14).iloc[-1]
    assert r == 100.0


def test_rsi_bounds():
    rng = np.random.default_rng(0)
    s = pd.Series(100 + np.cumsum(rng.normal(0, 1, 200)))
    r = indicators.rsi(s, 14).dropna()
    assert (r >= 0).all() and (r <= 100).all()


def test_total_return_none_when_insufficient():
    s = pd.Series([1.0, 2.0, 3.0])
    assert indicators.total_return(s, 10) is None
    assert indicators.total_return(s, 2) == 2.0  # 3/1 - 1
