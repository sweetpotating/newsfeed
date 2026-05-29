"""sg-trading-bot — an automated, risk-managed multi-strategy investing engine
for Interactive Brokers, designed for a Singapore-based investor.

The package is layered so each piece is testable in isolation:

    data/        market data providers (synthetic | yfinance | ibkr)
    broker/      execution adapters (PaperBroker | IBKRBroker) behind one interface
    strategies/  the four sleeves (etf_dca, dividend, momentum, mean_reversion)
    risk         portfolio-level guardrails applied before any order is sent
    portfolio    combines sleeve targets into one set of target weights
    engine       the orchestrator that ties it all together for one rebalance
    backtest     historical simulation of the same engine logic

Nothing here promises profit. It is a disciplined framework for *executing* a
plan consistently and safely; the returns depend on the market and your config.
"""

__version__ = "0.1.0"
