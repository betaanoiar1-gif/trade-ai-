from __future__ import annotations
import os, json, httpx
from typing import Any

class AIError(RuntimeError): pass

class AIGateway:
    """OpenAI-compatible gateway. No provider is hard-coded into trading logic."""
    def __init__(self, base_url: str|None=None, api_key: str|None=None, model: str|None=None):
        self.base=(base_url or os.getenv("AI_BASE_URL","")).rstrip("/")
        self.key=api_key or os.getenv("AI_API_KEY",""); self.model=model or os.getenv("AI_MODEL","")
    def enabled(self): return bool(self.base and self.key and self.model)
    def chat(self, system: str, user: str, tools: list[dict[str,Any]]|None=None) -> dict[str,Any]:
        if not self.enabled(): raise AIError("AI gateway is not configured")
        body={"model":self.model,"messages":[{"role":"system","content":system},{"role":"user","content":user}],"temperature":0.1}
        if tools: body["tools"]=tools
        r=httpx.post(self.base+"/chat/completions",headers={"Authorization":f"Bearer {self.key}"},json=body,timeout=60)
        r.raise_for_status(); return r.json()

TRADER_SYSTEM = """You are a disciplined professional crypto market trader. Analyze only evidence supplied by tools. Never invent prices, indicators, funding, open interest, liquidations, order-book data or news. Use top-down multi-timeframe context, market structure, price action, momentum, volume, volatility, liquidity/SMC hypotheses, derivatives and macro/crypto catalysts when available. A single indicator never triggers a trade. Always define invalidation. You may choose LONG, SHORT, HOLD, WAIT or NO_TRADE. Waiting is a valid decision. Do not generate or evolve strategies. Do not override deterministic risk controls. Confidence is not probability of profit."""

def decision_prompt(snapshot: dict[str,Any]) -> str:
    return "Return a JSON trade plan only. Required keys: decision, confidence, entry_low, entry_high, stop, take_profit_1, take_profit_2, thesis, invalidation, warnings.\nMARKET SNAPSHOT:\n"+json.dumps(snapshot,default=str)
