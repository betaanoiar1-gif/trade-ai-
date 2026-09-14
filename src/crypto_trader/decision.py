from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Literal

class AIDecision(BaseModel):
    decision: Literal["LONG","SHORT","HOLD","WAIT","NO_TRADE"]
    confidence: float = Field(ge=0,le=1)
    entry_low: float|None=None
    entry_high: float|None=None
    stop: float|None=None
    take_profit_1: float|None=None
    take_profit_2: float|None=None
    thesis: str
    invalidation: str
    warnings: list[str]=[]
