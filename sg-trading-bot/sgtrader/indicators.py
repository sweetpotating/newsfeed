"""Small, dependency-light technical indicators used by the strategies.

Each takes a pandas Series of closing prices and returns a Series aligned to it.
Kept here (rather than pulling in TA-Lib) so the core install stays minimal.
"""
from __future__ import annotations

import pandas as pd


def sma(close: pd.Series, window: int) -> pd.Series:
    """Simple moving average."""
    return close.rolling(window=window, min_periods=window).mean()


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Wilder's Relative Strength Index, 0..100."""
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    # Wilder's smoothing == EMA with alpha = 1/period.
    avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0.0, pd.NA)
    out = 100.0 - (100.0 / (1.0 + rs))
    # When there are no losses at all, RSI is defined as 100.
    out = out.where(avg_loss != 0, 100.0)
    return out


def total_return(close: pd.Series, lookback: int) -> float | None:
    """Trailing total return over `lookback` bars, or None if insufficient data."""
    if len(close.dropna()) <= lookback:
        return None
    end = close.iloc[-1]
    start = close.iloc[-1 - lookback]
    if start == 0 or pd.isna(start) or pd.isna(end):
        return None
    return float(end / start - 1.0)
