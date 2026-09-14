from __future__ import annotations
from dataclasses import dataclass
from .models import RiskLimits, TradePlan

@dataclass(frozen=True)
class RiskDecision:
    allowed: bool
    reason: str
    qty: float = 0.0
    risk_cash: float = 0.0
    notional: float = 0.0


def validate_plan(plan: TradePlan, equity: float, limits: RiskLimits, daily_pnl: float = 0.0, current_exposure: float = 0.0, price: float | None = None) -> RiskDecision:
    if plan.decision not in {"LONG", "SHORT"}: return RiskDecision(False, "no executable trade decision")
    if equity <= 0: return RiskDecision(False, "non-positive equity")
    if daily_pnl <= -equity * limits.max_daily_loss: return RiskDecision(False, "daily loss limit reached")
    if plan.stop is None or price is None: return RiskDecision(False, "entry price and stop are required")
    entry = price if plan.entry_low is None or plan.entry_high is None else (plan.entry_low + plan.entry_high) / 2
    if entry <= 0 or plan.stop <= 0: return RiskDecision(False, "invalid entry or stop")
    if plan.decision == "LONG" and plan.stop >= entry: return RiskDecision(False, "long stop must be below entry")
    if plan.decision == "SHORT" and plan.stop <= entry: return RiskDecision(False, "short stop must be above entry")
    distance = abs(entry - plan.stop)
    risk_cash = equity * limits.risk_per_trade
    qty = risk_cash / distance
    notional = qty * entry
    max_notional = equity * limits.max_leverage
    if notional > max_notional:
        qty = max_notional / entry
        notional = qty * entry
    if current_exposure + notional > equity * limits.max_portfolio_risk * limits.max_leverage:
        return RiskDecision(False, "portfolio exposure limit reached")
    if plan.take_profit_1 is not None:
        reward = (plan.take_profit_1-entry) if plan.decision == "LONG" else (entry-plan.take_profit_1)
        if reward <= 0 or reward / distance < 1.0: return RiskDecision(False, "take profit has inadequate reward/risk")
    return RiskDecision(True, "risk checks passed", qty, risk_cash, notional)
