from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Literal

Side = Literal["long","short"]
Decision = Literal["LONG","SHORT","HOLD","WAIT","NO_TRADE"]

@dataclass(frozen=True)
class TradePlan:
    symbol: str
    decision: Decision
    confidence: float
    entry_low: float | None = None
    entry_high: float | None = None
    stop: float | None = None
    take_profit_1: float | None = None
    take_profit_2: float | None = None
    thesis: str = ""
    invalidation: str = ""
    warnings: tuple[str,...] = ()
    timestamp: str = ""

    def __post_init__(self):
        if not 0 <= self.confidence <= 1: raise ValueError("confidence must be 0..1")
        if not self.timestamp: object.__setattr__(self,"timestamp",datetime.now(timezone.utc).isoformat())

    def to_dict(self): return asdict(self)

@dataclass(frozen=True)
class RiskLimits:
    starting_equity: float = 1000.0
    risk_per_trade: float = 0.01
    max_daily_loss: float = 0.03
    max_portfolio_risk: float = 0.05
    max_leverage: float = 3.0

@dataclass(frozen=True)
class Position:
    symbol: str
    side: Side
    qty: float
    entry: float
    stop: float
    take_profit_1: float | None = None
    take_profit_2: float | None = None


def position_size(equity: float, entry: float, stop: float, limits: RiskLimits, fee_rate: float=0.0005) -> float:
    distance=abs(entry-stop)
    if equity<=0 or distance<=0: return 0.0
    risk_cash=equity*limits.risk_per_trade
    qty=risk_cash/distance
    # Reserve a conservative estimate for entry+exit fees.
    qty=min(qty, (equity*limits.max_leverage)/entry)
    return max(0.0, qty*(1-fee_rate*2))
