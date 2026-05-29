"""Strategy sleeves. Each maps a universe + price history to target weights
*within its own sleeve* (the weights it returns sum to <= 1.0). The portfolio
layer scales those by the sleeve's share of total capital."""
from .base import Strategy
from .etf_dca import ETFDCAStrategy
from .dividend import DividendStrategy
from .momentum import MomentumStrategy
from .mean_reversion import MeanReversionStrategy

# Maps the sleeve names in config.yaml to their implementations.
STRATEGY_REGISTRY: dict[str, type[Strategy]] = {
    "etf_dca": ETFDCAStrategy,
    "dividend": DividendStrategy,
    "momentum": MomentumStrategy,
    "mean_reversion": MeanReversionStrategy,
}

__all__ = [
    "Strategy",
    "ETFDCAStrategy",
    "DividendStrategy",
    "MomentumStrategy",
    "MeanReversionStrategy",
    "STRATEGY_REGISTRY",
]
