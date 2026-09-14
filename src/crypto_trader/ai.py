from __future__ import annotations
import json, os, time
from typing import Any
import httpx
from .decision import AIDecision

class AIError(RuntimeError): pass

class AIGateway:
    """OpenAI-compatible gateway with bounded retries and strict schema validation."""
    def __init__(self, base_url: str|None=None, api_key: str|None=None, model: str|None=None):
        # KiosAPI can be configured with KIOS_API_KEY alone; generic AI_* remains supported.
        kios_key = os.getenv("KIOS_API_KEY") or os.getenv("KIOSAPI_API_KEY", "")
        self.base=(base_url or os.getenv("AI_BASE_URL") or os.getenv("KIOSAPI_BASE_URL") or ("https://router.kiosapi.com/v1" if kios_key else "")).rstrip("/")
        self.key=api_key or os.getenv("AI_API_KEY") or kios_key
        self.model=model or os.getenv("AI_MODEL", "")
        self.timeout=float(os.getenv("AI_TIMEOUT", "45"))
        self.retries=max(0,int(os.getenv("AI_RETRIES", "2")))
    def enabled(self): return bool(self.base and self.key and self.model)
    def chat(self, system: str, user: str, tools: list[dict[str,Any]]|None=None) -> dict[str,Any]:
        if not self.enabled(): raise AIError("AI gateway is not configured")
        body={"model":self.model,"messages":[{"role":"system","content":system},{"role":"user","content":user}],"temperature":0.1}
        if tools: body["tools"]=tools
        last=None
        for attempt in range(self.retries+1):
            try:
                r=httpx.post(self.base+"/chat/completions",headers={"Authorization":f"Bearer {self.key}","Content-Type":"application/json"},json=body,timeout=self.timeout)
                r.raise_for_status(); return r.json()
            except Exception as exc:
                last=exc
                if attempt < self.retries: time.sleep(1.5*(attempt+1))
        raise AIError(f"AI request failed after retries: {last}") from last

    @staticmethod
    def extract_plan(response: dict[str,Any]) -> dict[str,Any]:
        try: content=response["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc: raise AIError("AI response has no message content") from exc
        if isinstance(content, list):
            content="".join(part.get("text","") for part in content if isinstance(part,dict))
        text=str(content).strip()
        if text.startswith("```"):
            text=text.strip("`").replace("json\n", "", 1).strip()
        try: obj=json.loads(text)
        except json.JSONDecodeError as exc: raise AIError("AI returned invalid JSON") from exc
        try:
            return AIDecision.model_validate(obj).model_dump()
        except Exception as exc:
            raise AIError(f"AI plan failed schema validation: {exc}") from exc

TRADER_SYSTEM = """You are a disciplined professional crypto market trader. You are one trader, not a strategy generator. Analyze only evidence supplied by tools. Never invent prices, indicators, funding, open interest, liquidations, order-book data, on-chain metrics or news. Think top-down: higher-timeframe regime and structure first, then price action, momentum, volume, volatility, liquidity/SMC hypotheses, derivatives and catalysts when available. A single indicator never triggers a trade. Build explicit scenarios, entry, invalidation and targets. LONG/SHORT/HOLD/WAIT/NO_TRADE are all valid; no trade is often correct. Never force a position. Deterministic risk controls are authoritative and cannot be overridden. Confidence is not probability of profit. Do not generate, mutate or multiply strategies."""

def decision_prompt(snapshot: dict[str,Any]) -> str:
    return "Return JSON only. Required keys: decision, confidence, entry_low, entry_high, stop, take_profit_1, take_profit_2, thesis, invalidation, warnings. Use null for unavailable numeric fields.\nMARKET SNAPSHOT:\n"+json.dumps(snapshot,default=str)
