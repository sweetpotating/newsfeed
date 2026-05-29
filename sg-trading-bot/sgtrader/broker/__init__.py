"""Execution adapters behind one interface."""
from .base import Broker
from .paper import PaperBroker

__all__ = ["Broker", "PaperBroker", "get_broker"]


def get_broker(config, market_data=None):
    """Factory: build the right broker for the configured mode.

    backtest/paper -> PaperBroker (simulated fills, no real money)
    live           -> IBKRBroker  (real account; only reachable past the gate)
    """
    from ..models import Mode

    if config.mode in (Mode.BACKTEST, Mode.PAPER):
        # In PAPER mode you can EITHER use the built-in simulator (default, no
        # account needed) or point the IBKR adapter at your IBKR *paper* account.
        # We default to the simulator so it works out of the box.
        return PaperBroker(
            starting_cash=float(config.raw.get("paper_starting_cash", 100_000)),
            base_currency=config.base_currency,
            market_data=market_data,
        )
    # Mode.LIVE — import lazily so ib_async is only required when actually trading.
    from .ibkr import IBKRBroker

    return IBKRBroker(config)
