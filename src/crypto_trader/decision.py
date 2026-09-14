from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class AIDecision(BaseModel):
    decision: Literal["LONG", "SHORT", "HOLD", "WAIT", "NO_TRADE"]
    confidence: float = Field(ge=0, le=1)
    entry_low: float | None = Field(default=None, gt=0)
    entry_high: float | None = Field(default=None, gt=0)
    stop: float | None = Field(default=None, gt=0)
    take_profit_1: float | None = Field(default=None, gt=0)
    take_profit_2: float | None = Field(default=None, gt=0)
    thesis: str = Field(min_length=1)
    invalidation: str = Field(min_length=1)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_trade_geometry(self):
        if self.entry_low is not None and self.entry_high is not None and self.entry_low > self.entry_high:
            raise ValueError("entry_low must be <= entry_high")
        if self.decision in {"LONG", "SHORT"}:
            if self.stop is None:
                raise ValueError("executable trade requires stop")
            entry = self.entry_low if self.entry_low is not None else self.entry_high
            if entry is not None:
                if self.decision == "LONG" and self.stop >= entry:
                    raise ValueError("LONG stop must be below entry")
                if self.decision == "SHORT" and self.stop <= entry:
                    raise ValueError("SHORT stop must be above entry")
                if self.take_profit_1 is not None:
                    if self.decision == "LONG" and self.take_profit_1 <= entry:
                        raise ValueError("LONG take_profit_1 must be above entry")
                    if self.decision == "SHORT" and self.take_profit_1 >= entry:
                        raise ValueError("SHORT take_profit_1 must be below entry")
                if self.take_profit_2 is not None and self.take_profit_1 is not None:
                    if self.decision == "LONG" and self.take_profit_2 < self.take_profit_1:
                        raise ValueError("LONG take_profit_2 must be >= take_profit_1")
                    if self.decision == "SHORT" and self.take_profit_2 > self.take_profit_1:
                        raise ValueError("SHORT take_profit_2 must be <= take_profit_1")
        return self
