"""Execution adapters behind one interface."""
import os

from .base import Broker
from .paper import PaperBroker

__all__ = ["Broker", "PaperBroker", "get_broker"]


def get_broker(config, market_data=None):
    """Factory: build the right broker for the configured mode.

    backtest         -> PaperBroker (simulated fills, no real money)
    paper            -> PaperBroker simulator by default, OR the IBKR adapter
                        pointed at your IBKR *paper* account if
                        SGTRADER_PAPER_BROKER=ibkr (still no real money).
    live             -> IBKRBroker  (real account; only reachable past the gate)
    """
    from ..models import Mode

    if config.mode is Mode.BACKTEST:
        return PaperBroker(
            starting_cash=float(config.raw.get("paper_starting_cash", 100_000)),
            base_currency=config.base_currency,
            market_data=market_data,
        )

    if config.mode is Mode.PAPER:
        # Route paper orders through the real IBKR *paper* account when asked.
        # This exercises the exact live order path with zero financial risk —
        # the recommended final check before going live.
        if os.getenv("SGTRADER_PAPER_BROKER", "simulator").lower() == "ibkr":
            from .ibkr import IBKRBroker

            return IBKRBroker(config)
        # Default: built-in simulator, works offline with no account.
        return PaperBroker(
            starting_cash=float(config.raw.get("paper_starting_cash", 100_000)),
            base_currency=config.base_currency,
            market_data=market_data,
        )

    # Mode.LIVE — import lazily so ib_async is only required when actually trading.
    from .ibkr import IBKRBroker

    return IBKRBroker(config)

