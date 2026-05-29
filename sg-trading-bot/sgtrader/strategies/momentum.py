"""Momentum / trend-following sleeve.

Classic dual-filter momentum:
  1. Trend filter — only consider names trading ABOVE their long SMA (200d
     default). This keeps us out of names in a downtrend.
  2. Cross-sectional rank — among those, hold the top-N by trailing return.

Capital is split equally across the chosen names. If nothing passes the trend
filter, the sleeve goes to cash (returns no weights), which is the point: don't
fight a broad downtrend.
"""
from __future__ import annotations

import pandas as pd

from .. import indicators
from ..models import Instrument, TargetWeight
from .base import Strategy


class MomentumStrategy(Strategy):
    name = "momentum"

    def compute(
        self,
        universe: list[Instrument],
        history: dict[str, pd.Series],
    ) -> list[TargetWeight]:
        lookback = int(self.params.get("lookback_days", 126))
        sma_days = int(self.params.get("sma_filter_days", 200))
        top_n = int(self.params.get("top_n", 2))

        scored: list[tuple[Instrument, float]] = []
        for inst in universe:
            s = history.get(inst.key)
            if s is None:
                continue
            s = s.dropna()
            if len(s) <= max(lookback, sma_days):
                continue
            # Trend filter.
            sma = indicators.sma(s, sma_days)
            if pd.isna(sma.iloc[-1]) or s.iloc[-1] <= sma.iloc[-1]:
                continue
            ret = indicators.total_return(s, lookback)
            if ret is None or ret <= 0:
                continue
            scored.append((inst, ret))

        if not scored:
            return []  # sleeve sits in cash

        scored.sort(key=lambda t: t[1], reverse=True)
        chosen = [inst for inst, _ in scored[:top_n]]
        w = 1.0 / len(chosen)
        return [
            TargetWeight(inst, w, reason=f"Momentum top-{top_n} (uptrend, +ret)")
            for inst in chosen
        ]
