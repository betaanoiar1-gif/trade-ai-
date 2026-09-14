from __future__ import annotations

import json
import os
import time
from typing import Any

import httpx


BASE = (
    os.getenv("KIOSAPI_BASE_URL")
    or os.getenv("AI_BASE_URL")
    or "https://router.kiosapi.com/v1/"
).rstrip("/")
KEY = os.getenv("KIOS_API_KEY") or os.getenv("KIOSAPI_API_KEY") or os.getenv("AI_API_KEY", "")

# KiosAPI currently documents these as free text/chat models.
FREE_MODELS = [
    "meta/llama-3.1-8b",
    "qwen/qwen3-30b",
    "zai/glm-4.7-flash",
    "google/gemma-4-26b",
    "aisingapore/sea-lion-27b",
    "google/gemini-2.5-flash",
]

SYSTEM = """You are testing a crypto trading decision model. Do not invent market facts. Return JSON only. You are not executing trades."""
PROMPT = """Return exactly one JSON object with these keys:
 decision, confidence, entry_low, entry_high, stop, take_profit_1, take_profit_2, thesis, invalidation, warnings.
Allowed decision values: LONG, SHORT, HOLD, WAIT, NO_TRADE.
For this connectivity test use decision=NO_TRADE, confidence between 0 and 1, all price fields null, thesis/invalidation short non-empty strings, warnings as a JSON array.
"""


def post(client: httpx.Client, model: str) -> tuple[bool, str, float]:
    started = time.perf_counter()
    try:
        r = client.post(
            f"{BASE}/chat/completions",
            headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": SYSTEM},
                    {"role": "user", "content": PROMPT},
                ],
                "temperature": 0.0,
                "max_tokens": 300,
            },
        )
        elapsed = time.perf_counter() - started
        if r.status_code >= 400:
            # Never print response headers or request data; only the provider's
            # HTTP status and a bounded, whitespace-normalized error body.
            body = " ".join(r.text.split())[:500]
            return False, f"HTTP {r.status_code}: {body}", elapsed
        data = r.json()
        content = data["choices"][0]["message"]["content"]
        if isinstance(content, list):
            content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
        obj = json.loads(str(content).strip().strip("`").replace("json\n", "", 1))
        required = {
            "decision", "confidence", "entry_low", "entry_high", "stop",
            "take_profit_1", "take_profit_2", "thesis", "invalidation", "warnings"
        }
        missing = required - set(obj)
        if missing:
            return False, f"missing={sorted(missing)}", elapsed
        if obj["decision"] != "NO_TRADE":
            return False, f"unexpected_decision={obj['decision']}", elapsed
        if not isinstance(obj["confidence"], (int, float)) or not 0 <= obj["confidence"] <= 1:
            return False, "confidence_invalid", elapsed
        if not isinstance(obj["warnings"], list):
            return False, "warnings_not_array", elapsed
        return True, "ok", elapsed
    except (httpx.HTTPError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        return False, type(exc).__name__, time.perf_counter() - started


def main() -> int:
    if not KEY:
        raise SystemExit("KIOS_API_KEY is not configured")

    headers = {"Authorization": f"Bearer {KEY}"}
    with httpx.Client(timeout=45.0) as client:
        available: set[str] = set()
        try:
            r = client.get(f"{BASE}/models", headers=headers)
            if r.status_code < 400:
                payload: dict[str, Any] = r.json()
                available = {str(x.get("id")) for x in payload.get("data", []) if isinstance(x, dict)}
            else:
                print(f"MODEL_LIST_WARNING=HTTP {r.status_code}: {' '.join(r.text.split())[:500]}")
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            print(f"MODEL_LIST_WARNING={type(exc).__name__}")

        results = []
        for model in FREE_MODELS:
            if available and model not in available:
                results.append((model, False, "not_listed", 0.0))
                continue
            ok, detail, latency = post(client, model)
            results.append((model, ok, detail, latency))

    print(f"KIOSAPI_BASE_URL={BASE}")
    print("KIOSAPI_FREE_MODEL_BENCHMARK")
    for model, ok, detail, latency in results:
        print(json.dumps({"model": model, "ok": ok, "detail": detail, "latency_s": round(latency, 3)}))

    passing = [x for x in results if x[1]]
    if not passing:
        print("RESULT=NO_FREE_MODEL_PASSED")
        return 1

    # Prefer reasoning/context/tool-capable free models, then latency.
    priority = {
        "zai/glm-4.7-flash": 0,
        "qwen/qwen3-30b": 1,
        "google/gemini-2.5-flash": 2,
        "google/gemma-4-26b": 3,
        "meta/llama-3.1-8b": 4,
        "aisingapore/sea-lion-27b": 5,
    }
    best = min(passing, key=lambda x: (priority.get(x[0], 99), x[3]))
    print(f"BEST_FREE_MODEL={best[0]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
