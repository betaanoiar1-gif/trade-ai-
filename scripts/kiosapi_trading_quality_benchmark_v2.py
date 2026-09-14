from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any

import httpx

BASE = (os.getenv("KIOSAPI_BASE_URL") or "https://router.kiosapi.com/v1/").rstrip("/")
KEY = os.getenv("KIOS_API_KEY") or os.getenv("KIOSAPI_API_KEY") or os.getenv("AI_API_KEY", "")
DEFAULT_MODELS = "qwen3.8-27b,deepseek-v4-flash,deepseek-v4-flash-0731,glm-5.3-flash,qwen3.8-flash,nemotron-3-super-120b-a12b,gpt-oss-20b,oc/mimo-v2.5"
MODELS = [x.strip() for x in os.getenv("KIOSAPI_TRADING_BENCHMARK_MODELS", DEFAULT_MODELS).split(",") if x.strip()]
REQUEST_INTERVAL_S = float(os.getenv("KIOSAPI_BENCHMARK_REQUEST_INTERVAL_S", "10"))
MAX_TOKENS = int(os.getenv("KIOSAPI_TRADING_BENCHMARK_MAX_TOKENS", "2048"))

@dataclass(frozen=True)
class Case:
    name: str
    expected: str
    snapshot: str
    evidence: tuple[str, ...]

CASES = [
    Case("bullish_breakout", "LONG", "BTCUSDT perpetual. Current 104200. 1D bullish HH/HL. 4H closed above 103500 after three failed attempts; volume 2.1x average. 1H EMA20>EMA50>EMA200, RSI 64, ADX 29. 15M retest holds 103500-103800. Funding +0.008%, OI +7%. No liquidation data or news. Invalidation: confirmed 1H close below 103500.", ("103500", "volume", "EMA", "RSI", "funding", "OI")),
    Case("bearish_breakdown", "SHORT", "ETHUSDT perpetual. Current 3520. 1D bearish lower highs. 4H closed below 3600 and retest failed at 3590. 1H EMA20<EMA50<EMA200, RSI 34, ADX 31. 15M lower high with selling volume 1.8x average. Funding -0.012%, OI +5%. No liquidation data or news. Invalidation: confirmed 1H close above 3600.", ("3600", "volume", "EMA", "RSI", "funding", "OI")),
    Case("range_no_trade", "NO_TRADE", "SOLUSDT perpetual. Current 148.2. 4H inside 142-154 range with failed breaks both sides. 1H EMA20/50 flat, ADX 14, RSI 51. Volume 0.8x average. Funding +0.001%, OI flat. No clean sweep or BOS. No liquidation data or news. No validated entry, stop, or directional edge; breakout plus retest required.", ("range", "ADX", "RSI", "volume", "OI")),
    Case("fake_breakout", "NO_TRADE", "BTCUSDT perpetual. Current 101900. 4H briefly moved above 103000 but closed back below. Breakout volume 0.9x average. 1H RSI 57, ADX 17, EMA20 only slightly above EMA50. OI fell 3%. No confirmed retest above resistance. No liquidation data or news. Directional edge is unconfirmed.", ("failed", "volume", "ADX", "OI")),
    Case("mtf_conflict", "WAIT", "ETHUSDT perpetual. Current 3650. 1D remains bearish below major resistance, but 4H just made a higher high. 1H EMA20>EMA50 while 15M rejects resistance and RSI is 72. Volume normal, OI flat, funding mildly positive. No confirmed breakout/retest. No liquidation data. Wait for higher-timeframe alignment or clean invalidation.", ("1D", "4H", "15M", "RSI", "OI")),
    Case("missing_derivatives", "NO_TRADE", "SOLUSDT perpetual. Current 150. 4H mildly bullish and 1H EMA20>EMA50, but funding, open interest, and liquidation data are unavailable. Volume 1.1x average and RSI 58. Resistance has not broken. Do not invent unavailable derivative data and do not force a trade.", ("funding", "open interest", "liquidation", "volume", "RSI")),
    Case("stale_data", "NO_TRADE", "BTCUSDT perpetual. Current 98000. Latest OHLCV candle is 47 minutes old for a 5-minute strategy. Order book snapshot is stale. Indicators cannot be trusted for current execution. No fresh funding or OI snapshot is supplied. Do not trade on stale market data.", ("stale", "5-minute", "order book", "funding", "OI")),
    Case("high_volatility", "WAIT", "BTCUSDT perpetual. Current 105000. 1H ATR is 4.8% of price, largest in 90 days. Price oscillates violently around 104800 support. RSI 52 and ADX 19 give no directional confirmation. Volume 2.5x average but split both ways. Funding +0.02%, OI +9%. Normal stop sizing is too tight. Wait for volatility contraction and structure confirmation.", ("ATR", "volatility", "volume", "funding", "OI")),
    Case("bad_risk_reward", "NO_TRADE", "ETHUSDT perpetual. Current 3500. Possible long at 3480 support, but valid stop is 3460 and nearest realistic target is 3515. Reward/risk is below 1:1. Trend and volume neutral. Funding and OI provide no strong edge. Do not trade with inadequate reward/risk.", ("stop", "target", "reward", "risk", "1:1")),
    Case("clean_long", "LONG", "BTCUSDT perpetual. Current 99000. 1D and 4H bullish HH/HL. Resistance 98200 broke and held on retest. 1H EMA20>EMA50>EMA200, RSI 61, ADX 27. Breakout volume 1.9x. Funding +0.004%, OI +4%. No liquidation data. Invalidation: confirmed 1H close below 98200. Conservative stop below retest and target near 101500 give positive reward/risk.", ("98200", "EMA", "RSI", "volume", "funding", "OI")),
    Case("clean_short", "SHORT", "SOLUSDT perpetual. Current 142.5. 1D and 4H bearish lower highs/lows. Support 145 broke and retest failed at 144.8. 1H EMA20<EMA50<EMA200, RSI 38, ADX 28. Selling volume 2.0x. Funding -0.006%, OI +6%. No liquidation data. Invalidation: confirmed 1H close above 145. Stop above failed retest and target near 137 give positive reward/risk.", ("145", "EMA", "RSI", "volume", "funding", "OI")),
    Case("contradictory_signals", "NO_TRADE", "BTCUSDT perpetual. Current 100000. 4H bullish but price is below major resistance 101000. 1H RSI 78 and volume 2.2x suggest exhaustion, while OI rises 10% and funding is +0.03%. 15M bearish divergence has no confirmed breakdown. No clean entry/invalidation without chasing. No liquidation data or news.", ("resistance", "RSI", "volume", "OI", "funding")),
]

SYSTEM = """You are the deterministic decision engine of a crypto paper-trading research system. Use only supplied facts. Never invent missing data. Return exactly one compact JSON object and nothing else. Do not execute a trade. Confidence is not probability of profit. Keep reasoning internal."""
PROMPT = """Return exactly one JSON object with ONLY these keys: decision, confidence, entry_low, entry_high, stop, take_profit_1, take_profit_2, thesis, invalidation, warnings.
Allowed decisions: LONG, SHORT, HOLD, WAIT, NO_TRADE. Numeric price fields or null. Confidence 0..1. LONG/SHORT requires logically placed stop and TP1 with reward/risk >=1:1. NO_TRADE should have all five price fields null. WAIT should normally use null prices. warnings is an array. Keep thesis/invalidation short. Use no facts absent from the case.
CASE:\n{snapshot}"""


def candidates(message: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for key in ("content", "text", "output_text"):
        value = message.get(key)
        if isinstance(value, str) and value.strip(): out.append(value)
        elif isinstance(value, list):
            parts = []
            for item in value:
                if isinstance(item, str): parts.append(item)
                elif isinstance(item, dict):
                    part = item.get("text") or item.get("content") or item.get("output_text")
                    if isinstance(part, str): parts.append(part)
            if parts: out.append("".join(parts))
    for field in ("tool_calls", "function_call"):
        value = message.get(field)
        items = value if isinstance(value, list) else [value]
        for item in items:
            if not isinstance(item, dict): continue
            fn = item.get("function") if isinstance(item.get("function"), dict) else item
            args = fn.get("arguments") if isinstance(fn, dict) else None
            if isinstance(args, str) and args.strip(): out.append(args)
    return out


def extract_json(text: str) -> dict[str, Any] | None:
    depth = 0; start = None; quoted = False; escaped = False
    for i, ch in enumerate(text):
        if quoted:
            if escaped: escaped = False
            elif ch == "\\": escaped = True
            elif ch == '"': quoted = False
            continue
        if ch == '"': quoted = True
        elif ch == "{":
            if depth == 0: start = i
            depth += 1
        elif ch == "}" and depth:
            depth -= 1
            if depth == 0 and start is not None:
                try:
                    obj = json.loads(text[start:i+1])
                    if isinstance(obj, dict): return obj
                except json.JSONDecodeError: pass
                start = None
    return None


def parse_response(data: dict[str, Any]) -> dict[str, Any]:
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict): raise ValueError("missing choices")
    choice = choices[0]
    if choice.get("finish_reason") == "length": raise ValueError("finish_reason=length")
    message = choice.get("message")
    if not isinstance(message, dict): raise ValueError("missing message")
    for text in candidates(message):
        obj = extract_json(text)
        if obj is not None: return obj
    raise ValueError("no JSON object in final response")


def num(v: Any) -> float | None:
    if isinstance(v, bool): return None
    try: return float(v)
    except (TypeError, ValueError): return None


def score(obj: dict[str, Any], case: Case) -> tuple[int, list[str]]:
    required = {"decision","confidence","entry_low","entry_high","stop","take_profit_1","take_profit_2","thesis","invalidation","warnings"}
    missing = required - set(obj)
    if missing: return 0, [f"missing={sorted(missing)}"]
    p = 20; notes = []
    if obj.get("decision") == case.expected: p += 35; notes.append("decision_match")
    else: notes.append(f"decision_mismatch={obj.get('decision')}")
    conf = num(obj.get("confidence"))
    if conf is not None and 0 <= conf <= 1: p += 10
    else: notes.append("confidence_invalid")
    if isinstance(obj.get("thesis"), str) and obj["thesis"].strip(): p += 5
    else: notes.append("thesis_empty")
    if isinstance(obj.get("invalidation"), str) and obj["invalidation"].strip(): p += 5
    else: notes.append("invalidation_empty")
    text = f"{obj.get('thesis','')} {obj.get('invalidation','')}".lower()
    hits = sum(term.lower() in text for term in case.evidence)
    p += min(15, hits * 3)
    if hits < max(1, len(case.evidence)//2): notes.append(f"evidence={hits}/{len(case.evidence)}")
    if case.expected == "NO_TRADE":
        if all(obj.get(k) is None for k in ("entry_low","entry_high","stop","take_profit_1","take_profit_2")): p += 10
        else: notes.append("prices_present_on_no_trade")
    elif case.expected in {"LONG","SHORT"}:
        values = [num(obj.get(k)) for k in ("entry_low","entry_high","stop","take_profit_1")]
        if all(v is not None and v > 0 for v in values):
            lo, hi, stop, tp = values; entry = (lo+hi)/2; risk = abs(entry-stop)
            reward = tp-entry if case.expected == "LONG" else entry-tp
            valid_side = stop < entry < tp if case.expected == "LONG" else tp < entry < stop
            if lo <= hi and risk > 0 and reward >= risk and valid_side: p += 15
            else: notes.append("trade_geometry_or_rr_invalid")
        else: notes.append("trade_prices_invalid")
    return min(p, 100), notes


def run_model(client: httpx.Client, model: str) -> list[dict[str, Any]]:
    results = []
    for case in CASES:
        started = time.perf_counter()
        try:
            r = client.post(f"{BASE}/chat/completions", headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}, json={
                "model": model,
                "messages": [{"role":"system","content":SYSTEM},{"role":"user","content":PROMPT.format(snapshot=case.snapshot)}],
                "temperature": 0.0, "max_tokens": MAX_TOKENS, "response_format": {"type":"json_object"}
            })
            latency = time.perf_counter()-started
            if r.status_code >= 400: raise ValueError(f"HTTP {r.status_code}")
            obj = parse_response(r.json())
            points, notes = score(obj, case)
            results.append({"case":case.name,"ok":points >= 70,"score":points,"detail":notes,"latency_s":round(latency,3)})
        except Exception as exc:
            results.append({"case":case.name,"ok":False,"score":0,"detail":type(exc).__name__+":"+str(exc)[:180],"latency_s":round(time.perf_counter()-started,3)})
        time.sleep(REQUEST_INTERVAL_S)
    return results


def main() -> int:
    if not KEY: raise SystemExit("KIOS_API_KEY is not configured")
    if REQUEST_INTERVAL_S < 8: raise SystemExit("benchmark interval must be >= 8 seconds")
    print(f"KIOSAPI_BASE_URL={BASE}")
    print(f"MODELS={json.dumps(MODELS)}")
    print(f"CASES={len(CASES)}")
    print(f"REQUEST_INTERVAL_S={REQUEST_INTERVAL_S}")
    print(f"MAX_TOKENS={MAX_TOKENS}")
    print("RESPONSE_FORMAT=json_object")
    summaries=[]
    with httpx.Client(timeout=75.0) as client:
        for model in MODELS:
            results=run_model(client,model)
            summary={"model":model,"avg_score":round(sum(x["score"] for x in results)/len(results),2),"avg_latency_s":round(sum(x["latency_s"] for x in results)/len(results),3),"valid_cases":sum(x["ok"] for x in results),"all_cases_valid":all(x["ok"] for x in results),"results":results}
            summaries.append(summary); print("MODEL_RESULT="+json.dumps(summary,ensure_ascii=False))
    ranked=sorted(summaries,key=lambda x:(not x["all_cases_valid"],-x["avg_score"],-x["valid_cases"],x["avg_latency_s"]))
    print("TRADING_QUALITY_RANKING="+json.dumps(ranked,ensure_ascii=False))
    qualified=[x for x in ranked if x["all_cases_valid"]]
    print("BEST_TRADING_MODEL="+(qualified[0]["model"] if qualified else "INCONCLUSIVE"))
    if not qualified: print("NOTE=No model passed every deterministic case; do not select production model")
    print("NOTE=This measures decision/schema discipline, not profitability or future returns")
    return 0

if __name__ == "__main__": raise SystemExit(main())
