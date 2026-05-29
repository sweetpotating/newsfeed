from sgtrader.models import Account, Instrument, Position, Side
from sgtrader.portfolio import CombinedTarget
from sgtrader.risk import RiskManager, RiskState


def _inst(sym):
    return Instrument(sym, "ARCA", "USD")


def _rm(**over):
    base = {
        "max_position_pct": 0.25, "max_gross_exposure": 1.0, "min_cash_pct": 0.02,
        "min_trade_value": 200, "max_daily_turnover": 1.0, "max_drawdown_halt": 0.20,
    }
    base.update(over)
    return RiskManager(base)


def test_position_cap_enforced():
    rm = _rm()
    acct = Account(cash=10_000)
    targets = {"A-ARCA-USD": CombinedTarget(_inst("A"), 0.90, ["x"])}  # asks for 90%
    prices = {"A-ARCA-USD": 100.0}
    orders, diag = rm.build_orders(acct, targets, prices, RiskState())
    assert len(orders) == 1
    # capped to 25% of 10k = 2500 -> 25 shares
    assert orders[0].side is Side.BUY
    assert abs(orders[0].value - 2500) < 1.0


def test_min_trade_value_skips_tiny_trades():
    rm = _rm(min_trade_value=500)
    acct = Account(cash=10_000)
    targets = {"A-ARCA-USD": CombinedTarget(_inst("A"), 0.01, ["x"])}  # 1% = $100 < 500
    orders, _ = rm.build_orders(acct, targets, {"A-ARCA-USD": 100.0}, RiskState())
    assert orders == []


def test_drawdown_circuit_breaker_blocks_buys():
    rm = _rm(max_drawdown_halt=0.10)
    state = RiskState(peak_equity=20_000)  # we are 50% below peak
    acct = Account(cash=10_000)
    targets = {"A-ARCA-USD": CombinedTarget(_inst("A"), 0.20, ["x"])}
    orders, diag = rm.build_orders(acct, targets, {"A-ARCA-USD": 100.0}, state)
    assert diag["halted"] is True
    assert all(o.side is not Side.BUY for o in orders)


def test_drawdown_breaker_still_allows_sells():
    rm = _rm(max_drawdown_halt=0.10)
    state = RiskState(peak_equity=100_000)
    pos = Position(_inst("A"), quantity=100, avg_cost=100, market_price=100)
    acct = Account(cash=0, positions={"A-ARCA-USD": pos})  # equity 10k, deep DD
    targets = {}  # target zero -> should sell
    orders, diag = rm.build_orders(acct, targets, {"A-ARCA-USD": 100.0}, state)
    assert diag["halted"] is True
    assert any(o.side is Side.SELL for o in orders)


def test_cash_buffer_scales_down():
    rm = _rm(max_position_pct=1.0, min_cash_pct=0.10)
    acct = Account(cash=10_000)
    targets = {
        "A-ARCA-USD": CombinedTarget(_inst("A"), 0.6, ["x"]),
        "B-ARCA-USD": CombinedTarget(_inst("B"), 0.6, ["x"]),
    }
    prices = {"A-ARCA-USD": 100.0, "B-ARCA-USD": 100.0}
    orders, diag = rm.build_orders(acct, targets, prices, RiskState())
    invested = sum(o.value for o in orders)
    # must respect the 90% invest budget
    assert invested <= 9_000 + 1.0
