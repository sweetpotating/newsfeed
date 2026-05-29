"""A walk-forward backtester that runs the EXACT same strategy + risk logic as
live trading, just against historical bars and the PaperBroker.

This shared-logic design is deliberate: what you backtest is what you trade.
The result is an equity curve plus summary stats (CAGR, max drawdown, Sharpe).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .broker.paper import PaperBroker
from .config import Config
from .data import get_provider
from .logging_config import get_logger
from .models import Side
from .portfolio import combine_targets
from .risk import RiskManager, RiskState
from .strategies import STRATEGY_REGISTRY

log = get_logger("backtest")


@dataclass
class BacktestResult:
    equity_curve: pd.Series
    stats: dict = field(default_factory=dict)


def run_backtest(
    config: Config,
    start: str | None = None,
    history_days: int = 750,
    rebalance_every: int = 5,
    starting_cash: float = 100_000,
) -> BacktestResult:
    """Replay history bar-by-bar, rebalancing every `rebalance_every` bars."""
    sleeve_weights = config.enabled_sleeves()
    instruments = {
        inst.key: inst
        for sleeve in sleeve_weights
        for inst in config.universes.get(sleeve, [])
    }
    inst_list = list(instruments.values())

    provider = get_provider(config.data_provider)
    full_hist = provider.history(inst_list, lookback_days=history_days)
    if not full_hist:
        raise RuntimeError("No history returned for backtest.")

    # Common date index across all series.
    common = None
    for s in full_hist.values():
        common = s.index if common is None else common.union(s.index)
    common = common.sort_values()
    if start:
        common = common[common >= pd.Timestamp(start)]

    broker = PaperBroker(starting_cash=starting_cash, base_currency=config.base_currency,
                         state_path=None)
    broker.connect()
    risk = RiskManager(config.risk)
    risk_state = RiskState()

    # Warm-up so indicators have enough lookback before the first trade.
    warmup = _max_lookback(config)
    equity_points: list[tuple[pd.Timestamp, float]] = []

    for i, date in enumerate(common):
        # Mark the simulated market to this bar's closes.
        window_prices = {}
        for key, s in full_hist.items():
            s_to_date = s[s.index <= date]
            if len(s_to_date):
                px = float(s_to_date.iloc[-1])
                broker.set_price(instruments[key], px)
                window_prices[key] = px

        account = broker.get_account()
        equity_points.append((date, account.equity))

        if i < warmup or i % rebalance_every != 0:
            continue

        # Build a trailing history window for the strategies.
        hist_window = {
            key: s[s.index <= date].tail(warmup + 5)
            for key, s in full_hist.items()
        }
        sleeve_outputs = {}
        for sleeve in sleeve_weights:
            strat = STRATEGY_REGISTRY[sleeve](config.strategy_params.get(sleeve, {}))
            sleeve_outputs[sleeve] = strat.compute(config.universes.get(sleeve, []), hist_window)

        targets = combine_targets(sleeve_weights, sleeve_outputs)
        orders, _ = risk.build_orders(account, targets, window_prices, risk_state)
        for order in orders:
            try:
                broker.place_order(order)
            except Exception as e:  # noqa: BLE001
                log.debug("Backtest order skipped: %s", e)

    curve = pd.Series(dict(equity_points)).sort_index()
    return BacktestResult(equity_curve=curve, stats=_stats(curve, starting_cash))


def _max_lookback(config: Config) -> int:
    candidates = [200]
    for params in config.strategy_params.values():
        for k in ("lookback_days", "sma_filter_days"):
            if k in params:
                candidates.append(int(params[k]))
    return max(candidates)


def _stats(curve: pd.Series, starting_cash: float) -> dict:
    curve = curve.dropna()
    if len(curve) < 2:
        return {"error": "insufficient data"}
    rets = curve.pct_change().dropna()
    total_return = curve.iloc[-1] / starting_cash - 1.0
    years = max((curve.index[-1] - curve.index[0]).days / 365.25, 1e-9)
    cagr = (curve.iloc[-1] / starting_cash) ** (1 / years) - 1.0
    running_max = curve.cummax()
    max_dd = float((curve / running_max - 1.0).min())
    sharpe = float(np.sqrt(252) * rets.mean() / rets.std()) if rets.std() > 0 else 0.0
    return {
        "start": str(curve.index[0].date()),
        "end": str(curve.index[-1].date()),
        "starting_equity": round(float(starting_cash), 2),
        "ending_equity": round(float(curve.iloc[-1]), 2),
        "total_return_pct": round(total_return * 100, 2),
        "cagr_pct": round(cagr * 100, 2),
        "max_drawdown_pct": round(max_dd * 100, 2),
        "sharpe": round(sharpe, 2),
    }
