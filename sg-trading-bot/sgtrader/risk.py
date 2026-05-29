"""Portfolio-level risk guardrails and order generation.

This is the last gate before orders are formed. It turns target *weights* into
concrete target *dollar values*, clamps them to the configured limits, then
diffs against current holdings to produce orders — while honouring a cash
buffer, minimum trade size, turnover cap and a drawdown circuit breaker.
"""
from __future__ import annotations

from dataclasses import dataclass

from .logging_config import get_logger
from .models import Account, Instrument, Order, Side
from .portfolio import CombinedTarget

log = get_logger("risk")


@dataclass
class RiskState:
    peak_equity: float = 0.0


class RiskManager:
    def __init__(self, risk_cfg: dict):
        self.max_position_pct = float(risk_cfg.get("max_position_pct", 0.25))
        self.max_gross_exposure = float(risk_cfg.get("max_gross_exposure", 1.0))
        self.min_cash_pct = float(risk_cfg.get("min_cash_pct", 0.02))
        self.min_trade_value = float(risk_cfg.get("min_trade_value", 200))
        self.max_daily_turnover = float(risk_cfg.get("max_daily_turnover", 0.35))
        self.max_drawdown_halt = float(risk_cfg.get("max_drawdown_halt", 0.20))

    def build_orders(
        self,
        account: Account,
        targets: dict[str, CombinedTarget],
        prices: dict[str, float],
        risk_state: RiskState,
    ) -> tuple[list[Order], dict]:
        """Return (orders, diagnostics)."""
        equity = account.equity
        diag: dict = {"equity": equity, "halted": False, "notes": []}
        if equity <= 0:
            diag["notes"].append("Non-positive equity; no orders.")
            return [], diag

        # ── drawdown circuit breaker ─────────────────────────────────────────
        risk_state.peak_equity = max(risk_state.peak_equity, equity)
        drawdown = 1.0 - equity / risk_state.peak_equity if risk_state.peak_equity else 0.0
        de_risk_only = drawdown >= self.max_drawdown_halt
        if de_risk_only:
            diag["halted"] = True
            diag["notes"].append(
                f"Drawdown {drawdown:.1%} >= halt {self.max_drawdown_halt:.0%}: "
                "only reducing positions allowed."
            )

        # ── 1. cap each target weight, and the gross total ──────────────────
        capped: dict[str, float] = {}
        for key, t in targets.items():
            capped[key] = min(t.weight, self.max_position_pct)
        gross = sum(capped.values())
        invest_budget = min(self.max_gross_exposure, 1.0 - self.min_cash_pct)
        if gross > invest_budget and gross > 0:
            scale = invest_budget / gross
            capped = {k: w * scale for k, w in capped.items()}
            diag["notes"].append(f"Scaled targets by {scale:.3f} to respect cash buffer / gross cap.")

        # ── 2. target $ -> desired share qty, then diff vs current ──────────
        instruments: dict[str, Instrument] = {k: t.instrument for k, t in targets.items()}
        for key, pos in account.positions.items():
            instruments.setdefault(key, pos.instrument)

        proposed: list[Order] = []
        for key, inst in instruments.items():
            price = prices.get(key) or 0.0
            if price <= 0:
                continue
            target_value = capped.get(key, 0.0) * equity
            current_qty = account.positions[key].quantity if key in account.positions else 0.0
            current_value = current_qty * price
            delta_value = target_value - current_value

            if abs(delta_value) < self.min_trade_value:
                continue

            side = Side.BUY if delta_value > 0 else Side.SELL
            # Under the circuit breaker, skip anything that adds risk.
            if de_risk_only and side is Side.BUY:
                continue

            qty = abs(delta_value) / price
            reason = "; ".join(targets[key].reasons) if key in targets else "exit (not in target)"
            proposed.append(Order(inst, side, qty, ref_price=price, reason=reason))

        # ── 3. turnover cap — prioritise sells (free cash), then biggest buys
        orders = self._apply_turnover_cap(proposed, equity, diag)
        return orders, diag

    def _apply_turnover_cap(self, orders: list[Order], equity: float, diag: dict) -> list[Order]:
        budget = self.max_daily_turnover * equity
        # Sells first (they de-risk / raise cash and shouldn't be starved),
        # then buys by descending size.
        sells = [o for o in orders if o.side is Side.SELL]
        buys = sorted((o for o in orders if o.side is Side.BUY), key=lambda o: o.value, reverse=True)

        kept: list[Order] = []
        used = 0.0
        for o in sells + buys:
            if used + o.value > budget:
                # Trim a buy to fit; drop if it would fall below min trade size.
                if o.side is Side.BUY:
                    remaining = budget - used
                    if remaining >= self.min_trade_value and o.ref_price > 0:
                        o.quantity = remaining / o.ref_price
                        kept.append(o)
                        used += remaining
                    continue
                kept.append(o)  # never starve a sell
                used += o.value
                continue
            kept.append(o)
            used += o.value
        if used >= budget:
            diag["notes"].append(f"Turnover capped at {self.max_daily_turnover:.0%} of equity.")
        return kept
