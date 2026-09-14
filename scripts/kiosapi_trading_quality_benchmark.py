from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any

import httpx

BASE = (
    os.getenv("KIOSAPI_BASE_URL")
    or os.getenv("AI_BASE_URL")
    or "https://router.kiosapi.com/v1/"
).rstrip("/")
KEY = os.getenv("KIOS_API_KEY") or os.getenv("KIOSAPI_API_KEY") or os.getenv("AI_API_KEY", "")

MODELS = [
    x.strip()
    for x in os.getenv(
        "KIOSAPI_TRADING_BENCHMARK_MODELS",
        "deepseek-v4-flash,deepseek-v4-flash-0731,qwen3.8-27b",
    ).split(",")
    if x.strip()
]

# KiosAPI has recently returned HTTP 429 after roughly 10 requests/minute for this
# free key. Keep the benchmark deliberately below that ceiling so a rate limit is
# not mistaken for a model-quality failure.
REQUEST_INTERVAL_S = float(os.getenv("KIOSAPI_BENCHMARK_REQUEST_INTERVAL_S", "7.0"))


@dataclass(frozen=True)
class Case:
    name: str
    expected: str
    snapshot: str
    must_mention: tuple[str, ...]


CASES = [
    Case(
        "bullish_breakout",
        "LONG",
        """BTCUSDT perpetual. Current price 104200. 1D trend is bullish: HH/HL structure intact. 4H closed above resistance 103500 after three failed attempts, with volume 2.1x its 20-period average. 1H EMA20 > EMA50 > EMA200, RSI 64, ADX 29. 15M retest is holding 103500-103800. Funding is mildly positive at 0.008%, OI increased 7% during the breakout. No liquidation data is available. No external news is supplied. Invalidation: a confirmed 1H close back below 103500.""",
        ("103500", "volume", "EMA", "RSI", "funding", "OI"),
    ),
    Case(
        "bearish_breakdown",
        "SHORT",
        """ETHUSDT perpetual. Current price 3520. 1D structure is bearish with lower highs. 4H closed below support 3600 and the retest failed at 3590. 1H EMA20 < EMA50 < EMA200, RSI 34, ADX 31. 15M shows lower high and renewed selling volume at 1.8x the 20-period average. Funding is mildly negative at -0.012%, OI increased 5% during the breakdown. No liquidation data is available. No external news is supplied. Invalidation: a confirmed 1H close above 3600.""",
        ("3600", "volume", "EMA", "RSI", "funding", "OI"),
    ),
    Case(
        "range_no_trade",
        "NO_TRADE",
        """SOLUSDT perpetual. Current price 148.2. 4H price is inside a 142-154 range with repeated failed breaks on both sides. 1H EMA20 and EMA50 are flat and intertwined, ADX 14, RSI 51. Volume is 0.8x its 20-period average. Funding is 0.001%, OI is flat. No clean liquidity sweep or confirmed BOS is present. No liquidation data is available. No external news is supplied. There is no validated entry, stop, or directional edge at the current price. A breakout and successful retest would be required before considering a directional trade.""",
        ("range", "ADX", "RSI", "volume", "OI"),
    ),
]

SYSTEM = """You are the decision engine of a crypto paper-trading research system. Use only the supplied market facts. Never invent missing data. Treat SMC/liquidity interpretations as hypotheses, not certainties. Return JSON only. Do not execute a trade. Confidence is not probability of profit. Respect the requested decision when the evidence supports it, but independently evaluate the case."""

PROMPT = """Analyze this deterministic crypto market case and return exactly one JSON object with these keys:
 decision, confidence, entry_low, entry_high, stop, take_profit_1, take_profit_2, thesis, invalidation, warnings.
Allowed decision values: LONG, SHORT, HOLD, WAIT, NO_TRADE.
Use numeric price fields or null. If proposing LONG/SHORT, provide a logically placed stop and TP1 with at least 1:1 reward/risk. If the case has no validated edge, use NO_TRADE and leave price fields null.
Do not mention indicators or data that are absent from the case.

CASE:
{snapshot}
"""


def parse_response(data: dict[str, Any]) -> dict[str, Any]:
    content = data["choices"][0]["message"]["content"]
    if isinstance(content, list):
        content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
    text = str(content).strip()
    if text.startswith("```"):
        text = text.strip("`").replace("json\n", "", 1).strip()
    return json.loads(text)


def score(obj: dict[str, Any], case: Case) -> tuple[int, list[str]]:
    score = 0
    notes: list[str] = []
    required = {
        "decision", "confidence", "entry_low", "entry_high", "stop",
        "take_profit_1", "take_profit_2", "thesis", "invalidation", "warnings"
    }
    missing = required - set(obj)
    if missing:
        return 0, [f"missing={sorted(missing)}"]
    score += 20

    if obj.get("decision") == case.expected:
        score += 35
        notes.append("decision_match")
    else:
        notes.append(f"decision_mismatch={obj.get('decision')}")

    confidence = obj.get("confidence")
    if isinstance(confidence, (int, float)) and 0 <= confidence <= 1:
        score += 10
    else:
        notes.append("confidence_invalid")

    thesis = str(obj.get("thesis", "")).lower()
    invalidation = str(obj.get("invalidation", "")).lower()
    if thesis.strip():
        score += 5
    if invalidation.strip():
        score += 5

    combined = f"{thesis} {invalidation}"
    matched = sum(1 for term in case.must_mention if term.lower() in combined)
    score += min(15, matched * 3)
    if matched < len(case.must_mention):
        notes.append(f"evidence_terms={matched}/{len(case.must_mention)}")

    if case.expected == "NO_TRADE":
        if all(obj.get(k) is None for k in ("entry_low", "entry_high", "stop", "take_profit_1", "take_profit_2")):
            score += 10
        else:
            notes.append("no_trade_contains_prices")
    else:
        nums = [obj.get(k) for k in ("entry_low", "entry_high", "stop", "take_profit_1")]
        if all(isinstance(x, (int, float)) and x > 0 for x in nums):
            score += 10
            lo, hi, stop, tp1 = nums
            entry = (lo + hi) / 2
            if case.expected == "LONG" and stop < entry < tp1:
                score += 5
            elif case.expected == "SHORT" and tp1 < entry < stop:
                score += 5
            else:
                notes.append("trade_geometry_invalid")
        else:
            notes.append("trade_price_fields_invalid")

    return min(score, 100), notes


def run_model(client: httpx.Client, model: str) -> list[dict[str, Any]]:
    results = []
    for case in CASES:
        started = time.perf_counter()
        try:
            r = client.post(
                f"{BASE}/chat/completions",
                headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": SYSTEM},
                        {"role": "user", "content": PROMPT.format(snapshot=case.snapshot)},
                    ],
                    "temperature": 0.0,
                    "max_tokens": 500,
                },
            )
            elapsed = time.perf_counter() - started
            if r.status_code >= 400:
                results.append({"case": case.name, "ok": False, "score": 0, "detail": f"HTTP {r.status_code}", "latency_s": round(elapsed, 3)})
                continue
            obj = parse_response(r.json())
            points, notes = score(obj, case)
            results.append({"case": case.name, "ok": True, "score": points, "detail": notes, "latency_s": round(elapsed, 3)})
        except Exception as exc:
            results.append({"case": case.name, "ok": False, "score": 0, "detail": type(exc).__name__, "latency_s": round(time.perf_counter() - started, 3)})
        finally:
            time.sleep(REQUEST_INTERVAL_S)
    return results


def main() -> int:
    if not KEY:
        raise SystemExit("KIOS_API_KEY is not configured")
    if not MODELS:
        raise SystemExit("No benchmark models configured")
    if REQUEST_INTERVAL_S < 6.0:
        raise SystemExit("KIOSAPI_BENCHMARK_REQUEST_INTERVAL_S must be >= 6 seconds")

    print(f"KIOSAPI_BASE_URL={BASE}")
    print(f"MODELS={json.dumps(MODELS)}")
    print(f"CASES={len(CASES)}")
    print(f"REQUEST_INTERVAL_S={REQUEST_INTERVAL_S}")

    summaries = []
    with httpx.Client(timeout=45.0) as client:
        for model in MODELS:
            results = run_model(client, model)
            valid = [x for x in results if x["ok"]]
            avg = sum(x["score"] for x in valid) / len(valid) if valid else 0.0
            avg_latency = sum(x["latency_s"] for x in results) / len(results)
            summary = {"model": model, "avg_score": round(avg, 2), "avg_latency_s": round(avg_latency, 3), "results": results}
            summaries.append(summary)
            print("MODEL_RESULT=" + json.dumps(summary, ensure_ascii=False))

    ranked = sorted(summaries, key=lambda x: (-x["avg_score"], x["avg_latency_s"]))
    print("TRADING_QUALITY_RANKING=" + json.dumps(ranked, ensure_ascii=False))
    if ranked:
        print(f"BEST_TRADING_MODEL={ranked[0]['model']}")
        print("NOTE=This benchmark measures deterministic reasoning/schema discipline, not profitability or future returns")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
