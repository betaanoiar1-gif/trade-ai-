from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any

import httpx

BASE = (os.getenv("KIOSAPI_BASE_URL") or "https://router.kiosapi.com/v1/").rstrip("/")
KEY = os.getenv("KIOS_API_KEY") or os.getenv("KIOSAPI_API_KEY") or os.getenv("AI_API_KEY", "")
MODELS = [
    x.strip()
    for x in os.getenv(
        "KIOSAPI_TRADING_BENCHMARK_MODELS",
        "qwen3.8-27b,deepseek-v4-flash-0731,deepseek-v4-flash,glm-5.3-flash,qwen3.8-flash,nemotron-3-super-120b-a12b",
    ).split(",")
    if x.strip()
]
INTERVAL = float(os.getenv("KIOSAPI_BENCHMARK_REQUEST_INTERVAL_S", "10"))
TIMEOUT = float(os.getenv("KIOSAPI_BENCHMARK_TIMEOUT_S", "12"))
TOKENS = int(os.getenv("KIOSAPI_TRADING_BENCHMARK_MAX_TOKENS", "1200"))


@dataclass(frozen=True)
class Case:
    name: str
    expected: str
    snapshot: str
    evidence: tuple[str, ...]


SCREEN = Case(
    "breakout",
    "LONG",
    "BTCUSDT perpetual. Current 104200. 1D bullish HH/HL. 4H closed above 103500; volume 2.1x average. 1H EMA20>EMA50>EMA200, RSI 64, ADX 29. 15M retest holds 103500-103800. Funding +0.008%, OI +7%. No liquidation data. Invalidation: confirmed 1H close below 103500.",
    ("103500", "volume", "EMA", "RSI", "funding", "OI"),
)
DEEP = [
    Case(
        "bearish",
        "SHORT",
        "ETHUSDT perpetual. Current 3520. 1D bearish. 4H closed below 3600 and retest failed. 1H EMA20<EMA50<EMA200, RSI 34, ADX 31. Selling volume 1.8x. Funding -0.012%, OI +5%. Invalidation: 1H close above 3600.",
        ("3600", "volume", "EMA", "RSI", "funding", "OI"),
    ),
    Case(
        "range",
        "NO_TRADE",
        "SOLUSDT perpetual. Current 148.2. 4H inside 142-154 range with failed breaks. 1H EMA20/50 flat, ADX 14, RSI 51. Volume 0.8x. Funding +0.001%, OI flat. No clean sweep or BOS. No validated directional edge.",
        ("range", "ADX", "RSI", "volume", "OI"),
    ),
    Case(
        "missing_data",
        "NO_TRADE",
        "SOLUSDT perpetual. Current 150. 4H mildly bullish, but funding, open interest and liquidation data are unavailable. Volume 1.1x and RSI 58. Resistance has not broken. Do not invent unavailable data.",
        ("funding", "open interest", "liquidation", "volume", "RSI"),
    ),
]
SYSTEM = "You are a deterministic crypto paper-trading decision engine. Use only supplied facts. Never invent data. Return exactly one compact JSON object and nothing else."
PROMPT = "Return ONLY JSON with keys decision,confidence,entry_low,entry_high,stop,take_profit_1,take_profit_2,thesis,invalidation,warnings. Decisions: LONG, SHORT, HOLD, WAIT, NO_TRADE. Numeric prices or null. Confidence 0..1. LONG/SHORT needs valid stop and TP1 with >=1:1 reward/risk. NO_TRADE uses null prices. CASE:\n{snapshot}"


def extract(s: str) -> dict[str, Any] | None:
    depth = 0
    start = None
    quoted = False
    escaped = False
    for i, c in enumerate(s):
        if quoted:
            if escaped:
                escaped = False
            elif c == "\\":
                escaped = True
            elif c == '"':
                quoted = False
        elif c == '"':
            quoted = True
        elif c == "{":
            if depth == 0:
                start = i
            depth += 1
        elif c == "}" and depth:
            depth -= 1
            if depth == 0 and start is not None:
                try:
                    obj = json.loads(s[start : i + 1])
                    return obj if isinstance(obj, dict) else None
                except json.JSONDecodeError:
                    start = None
    return None


def parse(data: dict[str, Any]) -> dict[str, Any]:
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("missing_choices")
    choice = choices[0]
    if not isinstance(choice, dict):
        raise ValueError("invalid_choice")
    finish = choice.get("finish_reason")
    if finish == "length":
        raise ValueError("finish_reason_length")
    message = choice.get("message")
    if not isinstance(message, dict):
        raise ValueError("missing_message")
    for key in ("content", "text", "output_text"):
        value = message.get(key)
        if isinstance(value, str) and value.strip():
            obj = extract(value)
            if obj is not None:
                return obj
    raise ValueError("no_final_json")


def num(value: Any) -> float | None:
    try:
        return None if isinstance(value, bool) else float(value)
    except (TypeError, ValueError):
        return None


def score(obj: dict[str, Any], case: Case) -> int:
    required = {
        "decision",
        "confidence",
        "entry_low",
        "entry_high",
        "stop",
        "take_profit_1",
        "take_profit_2",
        "thesis",
        "invalidation",
        "warnings",
    }
    if required - set(obj):
        return 0
    points = 20 + (35 if obj.get("decision") == case.expected else 0)
    confidence = num(obj.get("confidence"))
    points += 10 if confidence is not None and 0 <= confidence <= 1 else 0
    points += 5 if isinstance(obj.get("thesis"), str) and obj["thesis"].strip() else 0
    points += 5 if isinstance(obj.get("invalidation"), str) and obj["invalidation"].strip() else 0
    text = f"{obj.get('thesis', '')} {obj.get('invalidation', '')}".lower()
    points += min(15, sum(term.lower() in text for term in case.evidence) * 3)
    if case.expected == "NO_TRADE":
        points += 10 if all(obj.get(k) is None for k in ("entry_low", "entry_high", "stop", "take_profit_1", "take_profit_2")) else 0
    else:
        values = [num(obj.get(k)) for k in ("entry_low", "entry_high", "stop", "take_profit_1")]
        if all(x is not None and x > 0 for x in values):
            low, high, stop, tp = values
            entry = (low + high) / 2
            risk = abs(entry - stop)
            reward = tp - entry if case.expected == "LONG" else entry - tp
            valid_geometry = (
                low <= high
                and risk > 0
                and reward >= risk
                and ((case.expected == "LONG" and stop < entry < tp) or (case.expected == "SHORT" and tp < entry < stop))
            )
            points += 15 if valid_geometry else 0
    return min(points, 100)


def call(client: httpx.Client, model: str, case: Case) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        response = client.post(
            f"{BASE}/chat/completions",
            headers={"Authorization": f"Bearer {KEY}"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": SYSTEM},
                    {"role": "user", "content": PROMPT.format(snapshot=case.snapshot)},
                ],
                "temperature": 0,
                "max_tokens": TOKENS,
                "response_format": {"type": "json_object"},
            },
        )
        latency = round(time.perf_counter() - started, 2)
        if response.status_code >= 400:
            return {"ok": False, "score": 0, "latency_s": latency, "error": f"HTTP_{response.status_code}"}
        try:
            payload = response.json()
        except ValueError:
            return {"ok": False, "score": 0, "latency_s": latency, "error": "invalid_http_json"}
        try:
            obj = parse(payload)
        except ValueError as exc:
            return {
                "ok": False,
                "score": 0,
                "latency_s": latency,
                "error": str(exc),
                "finish_reason": ((payload.get("choices") or [{}])[0] or {}).get("finish_reason"),
            }
        points = score(obj, case)
        return {"ok": points >= 70, "score": points, "latency_s": latency}
    except httpx.TimeoutException:
        return {"ok": False, "score": 0, "latency_s": round(time.perf_counter() - started, 2), "error": "ReadTimeout"}
    except httpx.HTTPError as exc:
        return {"ok": False, "score": 0, "latency_s": round(time.perf_counter() - started, 2), "error": type(exc).__name__}
    except Exception as exc:
        return {"ok": False, "score": 0, "latency_s": round(time.perf_counter() - started, 2), "error": type(exc).__name__}


def main() -> None:
    if not KEY:
        raise SystemExit("KIOS_API_KEY missing")
    if not 2 <= len(MODELS) <= 8:
        raise SystemExit("use 2-8 models")
    if INTERVAL < 8:
        raise SystemExit("interval must be >=8s")
    print(f"MODELS={json.dumps(MODELS)}")
    print("STAGE1_CASES=1")
    print("STAGE2_CASES=3")
    print(f"INTERVAL={INTERVAL}")
    print(f"TIMEOUT={TIMEOUT}")
    print(f"MAX_TOKENS={TOKENS}")
    with httpx.Client(timeout=TIMEOUT) as client:
        screened = []
        for index, model in enumerate(MODELS):
            result = call(client, model, SCREEN)
            result["model"] = model
            screened.append(result)
            print("SCREEN=" + json.dumps(result))
            if index < len(MODELS) - 1:
                time.sleep(INTERVAL)

        viable = [x for x in screened if x["ok"]]
        if not viable:
            print("FINALISTS=[]")
            print("RANKING=[]")
            print("BEST_TRADING_MODEL=INCONCLUSIVE")
            print("NOTE=No model passed screening; deep stage skipped to avoid wasting requests")
            return

        finalists = [x["model"] for x in sorted(viable, key=lambda x: (-x["score"], x["latency_s"]))[:2]]
        print("FINALISTS=" + json.dumps(finalists))
        summaries = []
        for model in finalists:
            cases = [next(x for x in screened if x["model"] == model)]
            for case in DEEP:
                result = call(client, model, case)
                cases.append(result)
                print("DEEP=" + json.dumps({"model": model, "case": case.name, **result}))
                time.sleep(INTERVAL)
            summaries.append(
                {
                    "model": model,
                    "avg_score": round(sum(x["score"] for x in cases) / 4, 2),
                    "valid_cases": sum(x["ok"] for x in cases),
                    "cases": 4,
                    "avg_latency_s": round(sum(x["latency_s"] for x in cases) / 4, 2),
                }
            )
        ranked = sorted(summaries, key=lambda x: (-x["valid_cases"], -x["avg_score"], x["avg_latency_s"]))
        print("RANKING=" + json.dumps(ranked))
        qualified = [x for x in ranked if x["valid_cases"] == 4]
        print("BEST_TRADING_MODEL=" + (qualified[0]["model"] if qualified else "INCONCLUSIVE"))
        print("NOTE=Fast staged benchmark; not a profitability test")


if __name__ == "__main__":
    main()
