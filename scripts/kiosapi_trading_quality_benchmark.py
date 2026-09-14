from __future__ import annotations

import json
import os
import re
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
MODELS = [x.strip() for x in os.getenv("KIOSAPI_TRADING_BENCHMARK_MODELS", "deepseek-v4-flash,deepseek-v4-flash-0731,qwen3.8-27b").split(",") if x.strip()]
REQUEST_INTERVAL_S = float(os.getenv("KIOSAPI_BENCHMARK_REQUEST_INTERVAL_S", "7.0"))


@dataclass(frozen=True)
class Case:
    name: str
    expected: str
    snapshot: str
    must_mention: tuple[str, ...]


CASES = [
    Case("bullish_breakout", "LONG", """BTCUSDT perpetual. Current price 104200. 1D trend is bullish: HH/HL structure intact. 4H closed above resistance 103500 after three failed attempts, with volume 2.1x its 20-period average. 1H EMA20 > EMA50 > EMA200, RSI 64, ADX 29. 15M retest is holding 103500-103800. Funding is mildly positive at 0.008%, OI increased 7% during the breakout. No liquidation data is available. No external news is supplied. Invalidation: a confirmed 1H close back below 103500.""", ("103500", "volume", "EMA", "RSI", "funding", "OI")),
    Case("bearish_breakdown", "SHORT", """ETHUSDT perpetual. Current price 3520. 1D structure is bearish with lower highs. 4H closed below support 3600 and the retest failed at 3590. 1H EMA20 < EMA50 < EMA200, RSI 34, ADX 31. 15M shows lower high and renewed selling volume at 1.8x the 20-period average. Funding is mildly negative at -0.012%, OI increased 5% during the breakdown. No liquidation data is available. No external news is supplied. Invalidation: a confirmed 1H close above 3600.""", ("3600", "volume", "EMA", "RSI", "funding", "OI")),
    Case("range_no_trade", "NO_TRADE", """SOLUSDT perpetual. Current price 148.2. 4H price is inside a 142-154 range with repeated failed breaks on both sides. 1H EMA20 and EMA50 are flat and intertwined, ADX 14, RSI 51. Volume is 0.8x its 20-period average. Funding is 0.001%, OI is flat. No clean liquidity sweep or confirmed BOS is present. No liquidation data is available. No external news is supplied. There is no validated entry, stop, or directional edge at the current price. A breakout and successful retest would be required before considering a directional trade.""", ("range", "ADX", "RSI", "volume", "OI")),
]

SYSTEM = """You are the decision engine of a crypto paper-trading research system. Use only the supplied market facts. Never invent missing data. Treat SMC/liquidity interpretations as hypotheses, not certainties. Return one JSON object only. Do not execute a trade. Confidence is not probability of profit. Respect the requested decision when the evidence supports it, but independently evaluate the case."""
PROMPT = """Analyze this deterministic crypto market case and return exactly one JSON object with these keys:
 decision, confidence, entry_low, entry_high, stop, take_profit_1, take_profit_2, thesis, invalidation, warnings.
Allowed decision values: LONG, SHORT, HOLD, WAIT, NO_TRADE.
Use numeric price fields or null. Confidence must be a number from 0 to 1. If proposing LONG/SHORT, provide a logically placed stop and TP1 with at least 1:1 reward/risk. If the case has no validated edge, use NO_TRADE and leave price fields null.
Do not mention indicators or data that are absent from the case.

CASE:
{snapshot}
"""


def _content_candidates(message: dict[str, Any]) -> list[str]:
    candidates: list[str] = []
    for key in ("content", "reasoning_content", "reasoning", "text", "output_text"):
        value = message.get(key)
        if isinstance(value, str) and value.strip():
            candidates.append(value)
        elif isinstance(value, list):
            parts: list[str] = []
            for item in value:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    for field in ("text", "content", "output_text", "reasoning_content"):
                        part = item.get(field)
                        if isinstance(part, str):
                            parts.append(part)
                            break
            if parts:
                candidates.append("".join(parts))
    tool_calls = message.get("tool_calls")
    if isinstance(tool_calls, list):
        for call in tool_calls:
            if not isinstance(call, dict):
                continue
            function = call.get("function")
            if isinstance(function, dict):
                arguments = function.get("arguments")
                if isinstance(arguments, str) and arguments.strip():
                    candidates.append(arguments)
    return candidates


def _json_objects(text: str) -> list[str]:
    text = text.strip()
    candidates: list[str] = []
    candidates.extend(re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL | re.IGNORECASE))
    for start, ch in enumerate(text):
        if ch != "{":
            continue
        depth = 0
        in_string = False
        escaped = False
        for i in range(start, len(text)):
            ch = text[i]
            if in_string:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    candidates.append(text[start : i + 1])
                    break
    return list(dict.fromkeys(candidates))


def _response_diagnostic(data: dict[str, Any]) -> str:
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return f"shape=no_choices;top_keys={sorted(data)[:12]}"
    choice = choices[0]
    message = choice.get("message")
    if not isinstance(message, dict):
        return f"shape=no_message;choice_keys={sorted(choice)[:12]}"
    content = message.get("content")
    reasoning = message.get("reasoning_content")
    return (
        f"message_keys={sorted(message)[:20]};"
        f"content_type={type(content).__name__};content_len={len(content) if isinstance(content, str) else '-'};"
        f"content_items={len(content) if isinstance(content, list) else '-'};"
        f"has_reasoning_content={isinstance(reasoning, str) and bool(reasoning.strip())};"
        f"reasoning_len={len(reasoning) if isinstance(reasoning, str) else '-'};"
        f"has_tool_calls={isinstance(message.get('tool_calls'), list) and bool(message.get('tool_calls'))};"
        f"finish_reason={choice.get('finish_reason')!r}"
    )


def parse_response(data: dict[str, Any]) -> dict[str, Any]:
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise ValueError("missing choices")
    message = choices[0].get("message")
    if not isinstance(message, dict):
        raise ValueError("missing message")
    errors: list[str] = []
    for text in _content_candidates(message):
        for candidate in _json_objects(text):
            try:
                obj = json.loads(candidate)
            except json.JSONDecodeError as exc:
                errors.append(exc.msg)
                continue
            if isinstance(obj, dict):
                return obj
    detail = errors[0] if errors else "no JSON object found"
    raise json.JSONDecodeError(f"{detail}; {_response_diagnostic(data)}", "", 0)


def _as_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def score(obj: dict[str, Any], case: Case) -> tuple[int, list[str]]:
    score = 0
    notes: list[str] = []
    required = {"decision", "confidence", "entry_low", "entry_high", "stop", "take_profit_1", "take_profit_2", "thesis", "invalidation", "warnings"}
    missing = required - set(obj)
    if missing:
        return 0, [f"missing={sorted(missing)}"]
    score += 20
    if obj.get("decision") == case.expected:
        score += 35
        notes.append("decision_match")
    else:
        notes.append(f"decision_mismatch={obj.get('decision')}")
    confidence = _as_number(obj.get("confidence"))
    if confidence is not None and 0 <= confidence <= 1:
        score += 10
    else:
        notes.append("confidence_invalid")
    thesis = str(obj.get("thesis", "")).lower()
    invalidation = str(obj.get("invalidation", "")).lower()
    if thesis.strip(): score += 5
    if invalidation.strip(): score += 5
    combined = f"{thesis} {invalidation}"
    matched = sum(1 for term in case.must_mention if term.lower() in combined)
    score += min(15, matched * 3)
    if matched < len(case.must_mention): notes.append(f"evidence_terms={matched}/{len(case.must_mention)}")
    if case.expected == "NO_TRADE":
        if all(obj.get(k) is None for k in ("entry_low", "entry_high", "stop", "take_profit_1", "take_profit_2")): score += 10
        else: notes.append("no_trade_contains_prices")
    else:
        nums = [_as_number(obj.get(k)) for k in ("entry_low", "entry_high", "stop", "take_profit_1")]
        if all(x is not None and x > 0 for x in nums):
            score += 10
            lo, hi, stop, tp1 = nums
            if lo > hi: return 0, notes + ["entry_range_invalid"]
            entry = (lo + hi) / 2
            distance = abs(entry - stop)
            reward = (tp1 - entry) if case.expected == "LONG" else (entry - tp1)
            if distance > 0 and reward >= distance:
                if case.expected == "LONG" and stop < entry < tp1: score += 5
                elif case.expected == "SHORT" and tp1 < entry < stop: score += 5
                else: notes.append("trade_geometry_invalid")
            else: notes.append("reward_risk_below_1")
        else: notes.append("trade_price_fields_invalid")
    return min(score, 100), notes


def run_model(client: httpx.Client, model: str) -> list[dict[str, Any]]:
    results = []
    for case in CASES:
        started = time.perf_counter()
        try:
            r = client.post(
                f"{BASE}/chat/completions",
                headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
                json={"model": model, "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": PROMPT.format(snapshot=case.snapshot)}], "temperature": 0.0, "max_tokens": 500},
            )
            elapsed = time.perf_counter() - started
            if r.status_code >= 400:
                results.append({"case": case.name, "ok": False, "score": 0, "detail": f"HTTP {r.status_code}", "latency_s": round(elapsed, 3)})
                continue
            data = r.json()
            obj = parse_response(data)
            points, notes = score(obj, case)
            results.append({"case": case.name, "ok": True, "score": points, "detail": notes, "latency_s": round(elapsed, 3)})
        except json.JSONDecodeError as exc:
            results.append({"case": case.name, "ok": False, "score": 0, "detail": str(exc), "latency_s": round(time.perf_counter() - started, 3)})
        except Exception as exc:
            results.append({"case": case.name, "ok": False, "score": 0, "detail": type(exc).__name__, "latency_s": round(time.perf_counter() - started, 3)})
        finally:
            time.sleep(REQUEST_INTERVAL_S)
    return results


def main() -> int:
    if not KEY: raise SystemExit("KIOS_API_KEY is not configured")
    if not MODELS: raise SystemExit("No benchmark models configured")
    if REQUEST_INTERVAL_S < 6.0: raise SystemExit("KIOSAPI_BENCHMARK_REQUEST_INTERVAL_S must be >= 6 seconds")
    print(f"KIOSAPI_BASE_URL={BASE}")
    print(f"MODELS={json.dumps(MODELS)}")
    print(f"CASES={len(CASES)}")
    print(f"REQUEST_INTERVAL_S={REQUEST_INTERVAL_S}")
    summaries = []
    with httpx.Client(timeout=45.0) as client:
        for model in MODELS:
            results = run_model(client, model)
            avg = sum(x["score"] for x in results) / len(results) if results else 0.0
            valid_cases = sum(1 for x in results if x["ok"])
            avg_latency = sum(x["latency_s"] for x in results) / len(results)
            all_cases_valid = valid_cases == len(CASES)
            summary = {"model": model, "avg_score": round(avg, 2), "avg_latency_s": round(avg_latency, 3), "valid_cases": valid_cases, "all_cases_valid": all_cases_valid, "results": results}
            summaries.append(summary)
            print("MODEL_RESULT=" + json.dumps(summary, ensure_ascii=False))
    ranked = sorted(summaries, key=lambda x: (not x["all_cases_valid"], -x["avg_score"], x["avg_latency_s"]))
    print("TRADING_QUALITY_RANKING=" + json.dumps(ranked, ensure_ascii=False))
    qualified = [x for x in ranked if x["all_cases_valid"]]
    if qualified: print(f"BEST_TRADING_MODEL={qualified[0]['model']}")
    else:
        print("BEST_TRADING_MODEL=INCONCLUSIVE")
        print("NOTE=No model passed all benchmark cases; do not select a production model from this run")
    print("NOTE=This benchmark measures deterministic reasoning/schema discipline, not profitability or future returns")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
