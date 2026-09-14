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

# These are the model families KiosAPI has documented as free. The /models
# endpoint may expose newer/different IDs, so the benchmark resolves them
# dynamically instead of assuming stale exact IDs.
FREE_FAMILIES = {
    "meta/llama-3.1-8b": ("llama", "3.1-8b"),
    "qwen/qwen3-30b": ("qwen3", "30b"),
    "zai/glm-4.7-flash": ("glm-4.7-flash",),
    "google/gemma-4-26b": ("gemma-4-26b",),
    "aisingapore/sea-lion-27b": ("sea-lion-27b",),
    "google/gemini-2.5-flash": ("gemini-2.5-flash",),
}

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
        return True, "ok", elapsed
    except (httpx.HTTPError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        return False, type(exc).__name__, time.perf_counter() - started


def model_is_explicitly_free(model: dict[str, Any]) -> bool:
    """Accept only explicit free metadata when available."""
    for key in ("free", "is_free"):
        if model.get(key) is True:
            return True
    pricing = model.get("pricing")
    if isinstance(pricing, dict):
        values = [pricing.get(k) for k in ("prompt", "completion", "input", "output", "input_price", "output_price")]
        if values and all(v in (0, 0.0, "0", "0.0", None) for v in values) and any(v is not None for v in values):
            return True
    return False


def resolve_candidates(models: list[dict[str, Any]]) -> list[tuple[str, str]]:
    """Resolve current model IDs to the documented free model families."""
    candidates: list[tuple[str, str]] = []
    for model in models:
        model_id = str(model.get("id", "")).strip()
        haystack = " ".join(str(model.get(k, "")) for k in ("id", "name", "description")).lower()
        if not model_id:
            continue
        for documented, family_tokens in FREE_FAMILIES.items():
            if all(token.lower() in haystack for token in family_tokens):
                # If the API exposes pricing/free metadata, require it to be free.
                # If it exposes no pricing metadata, family matching is the only
                # safe bridge to the provider's documented free-model list.
                if not any(k in model for k in ("pricing", "free", "is_free")) or model_is_explicitly_free(model):
                    candidates.append((documented, model_id))
                    break
    # One current ID per documented family, avoiding duplicate requests.
    unique: dict[str, tuple[str, str]] = {}
    for documented, model_id in candidates:
        unique.setdefault(documented, (documented, model_id))
    return list(unique.values())


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

        candidates = resolve_candidates(models)
        print(f"KIOSAPI_BASE_URL={BASE}")
        print(f"MODELS_VISIBLE={len(models)}")
        print("RESOLVED_FREE_MODELS")
        for documented, model_id in candidates:
            print(json.dumps({"documented_family": documented, "model_id": model_id}))

        if not candidates:
            # Do not guess a paid model. Print only a bounded inventory of IDs so
            # the next run can be audited without exposing any credentials.
            ids = [str(x.get("id")) for x in models if x.get("id")]
            print(f"NO_DOCUMENTED_FREE_FAMILY_MATCHED count={len(ids)}")
            print(json.dumps({"available_model_ids": ids[:100]}))
            return 1

        results = []
        for documented, model_id in candidates:
            ok, detail, latency = post(client, model_id)
            results.append((documented, model_id, ok, detail, latency))

    print("KIOSAPI_FREE_MODEL_BENCHMARK")
    for documented, model_id, ok, detail, latency in results:
        print(json.dumps({
            "documented_family": documented,
            "model": model_id,
            "ok": ok,
            "detail": detail,
            "latency_s": round(latency, 3),
        }))

    passing = [x for x in results if x[2]]
    if not passing:
        print("RESULT=NO_FREE_MODEL_PASSED")
        return 1

    # Quality is decided later with trader-task benchmarks. For connectivity,
    # prefer larger/reasoning-oriented documented families, then latency.
    priority = {
        "zai/glm-4.7-flash": 0,
        "qwen/qwen3-30b": 1,
        "google/gemini-2.5-flash": 2,
        "google/gemma-4-26b": 3,
        "meta/llama-3.1-8b": 4,
        "aisingapore/sea-lion-27b": 5,
    }
    best = min(passing, key=lambda x: (priority.get(x[0], 99), x[4]))
    print(f"BEST_CONNECTIVITY_MODEL={best[1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
