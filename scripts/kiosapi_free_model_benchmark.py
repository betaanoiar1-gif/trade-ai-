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

# KiosAPI's current free/promo catalog has changed from the older six-model
# documentation. These are CURRENT model IDs/families observed in the free
# group during September 2026. The resolver only selects an ID if it is also
# present in this account's /models response. This prevents accidentally
# probing arbitrary paid models.
CURRENT_FREE_IDS = {
    "kimi-k3",
    "minimax-m3",
    "glm-5.3-flash",
    "glm-5.2",
    "glm-5.3",
    "deepseek-v4-flash",
    "deepseek-v4-flash-0731",
    "qwen3.8-27b",
    "qwen3.8-flash",
    "nemotron-3-ultra-550b-a55b",
    "nemotron-3-super-120b-a12b",
    "oc/nemotron-3.5-lightning",
    "oc/mimo-v2.5",
    "oc/big-pickle",
    "oc/muse-spark-1.3-contributor",
    "oc/muse-spark-1.2-contributor",
    "ling-3.0-flash-fin",
    "oc/ling-3.0-flash-fin",
    "laguna-s-2.1",
    "laguna-xs-2.1",
    "gpt-oss-20b",
    "hy3",
    "agnes-2.5-flash",
    "agnes-2.0-flash",
    "sensenova-6.8-flash-lite",
    "north-mini-code",
}

# Optional explicit override for future KiosAPI catalog changes. Example:
# KIOSAPI_FREE_MODELS="model-a,model-b,model-c"
EXPLICIT_FREE = {
    x.strip() for x in os.getenv("KIOSAPI_FREE_MODELS", "").split(",") if x.strip()
}

# Do not consume the whole daily quota. The benchmark tests only the strongest
# current free candidates first. Set KIOSAPI_BENCHMARK_LIMIT to increase it.
DEFAULT_LIMIT = 12

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
            body = " ".join(r.text.split())[:500]
            return False, f"HTTP {r.status_code}: {body}", elapsed
        data = r.json()
        content = data["choices"][0]["message"]["content"]
        if isinstance(content, list):
            content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
        text = str(content).strip()
        if text.startswith("```"):
            text = text.strip("`").replace("json\n", "", 1).strip()
        obj = json.loads(text)
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
        if not isinstance(obj["thesis"], str) or not obj["thesis"].strip():
            return False, "thesis_empty", elapsed
        if not isinstance(obj["invalidation"], str) or not obj["invalidation"].strip():
            return False, "invalidation_empty", elapsed
        return True, "ok", elapsed
    except (httpx.HTTPError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        return False, type(exc).__name__, time.perf_counter() - started


def is_free_candidate(model: dict[str, Any]) -> bool:
    """Select only models known to belong to the current free catalog."""
    model_id = str(model.get("id", "")).strip()
    if not model_id:
        return False
    if EXPLICIT_FREE:
        return model_id in EXPLICIT_FREE
    if model_id in CURRENT_FREE_IDS:
        return True

    # Some gateways expose pricing/free metadata. Honor it only when it is
    # unambiguous; never infer free access from a model name alone.
    for key in ("free", "is_free"):
        if model.get(key) is True:
            return True
    pricing = model.get("pricing")
    if isinstance(pricing, dict):
        values = [pricing.get(k) for k in (
            "prompt", "completion", "input", "output", "input_price", "output_price"
        )]
        if values and all(v in (0, 0.0, "0", "0.0", None) for v in values) and any(v is not None for v in values):
            return True
    return False


def priority(model_id: str) -> int:
    """Prefer strong reasoning models while keeping the benchmark small."""
    order = [
        "kimi-k3",
        "deepseek-v4-flash",
        "deepseek-v4-flash-0731",
        "glm-5.3-flash",
        "qwen3.8-27b",
        "qwen3.8-flash",
        "minimax-m3",
        "nemotron-3-super-120b-a12b",
        "nemotron-3-ultra-550b-a55b",
        "oc/mimo-v2.5",
        "gpt-oss-20b",
        "glm-5.3",
        "hy3",
        "agnes-2.5-flash",
        "oc/muse-spark-1.3-contributor",
        "oc/big-pickle",
    ]
    try:
        return order.index(model_id)
    except ValueError:
        return 999


def main() -> int:
    if not KEY:
        raise SystemExit("KIOS_API_KEY is not configured")

    headers = {"Authorization": f"Bearer {KEY}"}
    models: list[dict[str, Any]] = []
    with httpx.Client(timeout=45.0) as client:
        try:
            r = client.get(f"{BASE}/models", headers=headers)
            if r.status_code >= 400:
                print(f"MODEL_LIST_WARNING=HTTP {r.status_code}: {' '.join(r.text.split())[:500]}")
                return 1
            payload: dict[str, Any] = r.json()
            raw = payload.get("data", [])
            models = [x for x in raw if isinstance(x, dict)]
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            print(f"MODEL_LIST_WARNING={type(exc).__name__}")
            return 1

        free_models = [m for m in models if is_free_candidate(m)]
        free_models.sort(key=lambda m: priority(str(m.get("id", ""))))
        limit = max(1, int(os.getenv("KIOSAPI_BENCHMARK_LIMIT", str(DEFAULT_LIMIT))))
        candidates = [str(m["id"]) for m in free_models[:limit]]

        print(f"KIOSAPI_BASE_URL={BASE}")
        print(f"MODELS_VISIBLE={len(models)}")
        print(f"FREE_CANDIDATES_VISIBLE={len(free_models)}")
        print("FREE_CANDIDATES")
        print(json.dumps([str(m.get("id")) for m in free_models], ensure_ascii=False))

        if not candidates:
            ids = [str(x.get("id")) for x in models if x.get("id")]
            print("NO_CURRENT_FREE_CANDIDATE_MATCHED")
            print(json.dumps({"available_model_ids": ids[:100]}, ensure_ascii=False))
            return 1

        print(f"BENCHMARK_LIMIT={limit}")
        results = []
        for model_id in candidates:
            ok, detail, latency = post(client, model_id)
            results.append((model_id, ok, detail, latency))

    print("KIOSAPI_FREE_MODEL_BENCHMARK")
    for model_id, ok, detail, latency in results:
        print(json.dumps({
            "model": model_id,
            "ok": ok,
            "detail": detail,
            "latency_s": round(latency, 3),
        }))

    passing = [x for x in results if x[1]]
    if not passing:
        print("RESULT=NO_FREE_MODEL_PASSED")
        return 1

    # This is only a connectivity/schema benchmark. The project must run a
    # separate trading-quality benchmark before selecting the production model.
    best = min(passing, key=lambda x: (priority(x[0]), x[3]))
    print(f"BEST_CONNECTIVITY_MODEL={best[0]}")
    print("NOTE=Connectivity success does not imply trading quality or profitability")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
