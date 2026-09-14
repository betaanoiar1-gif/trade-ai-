from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .indicators import enrich


@dataclass(frozen=True)
class Regime:
    name: str
    trend_strength: float
    volatility: str
    momentum: str


def detect_regime(df: pd.DataFrame) -> Regime:
    x = enrich(df)
    r = x.iloc[-1]
    adx = float(r.adx14) if pd.notna(r.adx14) else 0.0
    atr_pct = float(r.atr14 / r.close * 100) if pd.notna(r.atr14) and r.close else 0.0
    vol = "high" if atr_pct >= 5 else "low" if atr_pct <= 1 else "normal"
    name = "trend" if adx >= 25 else "high_volatility_range" if vol == "high" else "range"
    momentum = (
        "bullish"
        if r.ema20 > r.ema50 and r.macd_hist > 0
        else "bearish"
        if r.ema20 < r.ema50 and r.macd_hist < 0
        else "mixed"
    )
    return Regime(name, round(max(0.0, min(100.0, adx)), 2), vol, momentum)


def fibonacci(df: pd.DataFrame, lookback: int = 200) -> dict:
    x = df.tail(lookback)
    hi, lo = float(x.high.max()), float(x.low.min())
    if hi <= lo:
        return {}
    span = hi - lo
    return {str(k): hi - span * k for k in (0.236, 0.382, 0.5, 0.618, 0.786)}


def volume_profile(df: pd.DataFrame, bins: int = 24, lookback: int = 300) -> dict:
    x = df.tail(lookback)
    lo, hi = float(x.low.min()), float(x.high.max())
    if x.empty or hi == lo:
        return {}
    step = (hi - lo) / bins
    buckets = [0.0] * bins
    for row in x.itertuples():
        bucket = min(bins - 1, max(0, int((float(row.close) - lo) / step)))
        buckets[bucket] += float(row.volume)
    poc = max(range(bins), key=buckets)
    return {
        "low": lo,
        "high": hi,
        "bins": bins,
        "poc": lo + (poc + 0.5) * step,
        "total_volume": sum(buckets),
    }


def multi_timeframe(data: dict[str, pd.DataFrame]) -> dict:
    out = {}
    for tf, df in data.items():
        x = enrich(df)
        r = x.iloc[-1]
        out[tf] = {
            "close": float(r.close),
            "ema20": float(r.ema20) if pd.notna(r.ema20) else None,
            "ema50": float(r.ema50) if pd.notna(r.ema50) else None,
            "ema200": float(r.ema200) if pd.notna(r.ema200) else None,
            "rsi14": float(r.rsi14) if pd.notna(r.rsi14) else None,
            "atr14": float(r.atr14) if pd.notna(r.atr14) else None,
            "adx14": float(r.adx14) if pd.notna(r.adx14) else None,
            "macd_hist": float(r.macd_hist) if pd.notna(r.macd_hist) else None,
            "rel_volume": float(r.rel_volume) if pd.notna(r.rel_volume) else None,
        }
    return out


def orderbook_metrics(depth: dict, levels: int = 20) -> dict:
    bids = [(float(p), float(q)) for p, q in depth.get("bids", [])[:levels]]
    asks = [(float(p), float(q)) for p, q in depth.get("asks", [])[:levels]]
    if not bids or not asks:
        return {"available": False}
    bq, aq = sum(q for _, q in bids), sum(q for _, q in asks)
    mid = (bids[0][0] + asks[0][0]) / 2
    return {
        "available": True,
        "best_bid": bids[0][0],
        "best_ask": asks[0][0],
        "mid": mid,
        "spread_bps": (asks[0][0] - bids[0][0]) / mid * 10000,
        "bid_depth": bq,
        "ask_depth": aq,
        "imbalance": (bq - aq) / (bq + aq) if bq + aq else 0.0,
    }


def _number(record: dict, key: str) -> float | None:
    try:
        value = record.get(key)
        if value is None or value == "":
            return None
        value = float(value)
        return value if pd.notna(value) else None
    except (TypeError, ValueError):
        return None


def derivative_metrics(funding: list, oi: list) -> dict:
    f = funding[0] if funding else {}
    o = oi[0] if oi else {}
    fr = _number(f, "fundingRate")
    now = _number(o, "openInterest")
    prev = _number(oi[1], "openInterest") if len(oi) > 1 else None
    change = round(((now / prev) - 1) * 100, 10) if now is not None and prev not in (None, 0) else None
    return {
        "funding_rate": fr,
        "open_interest": now,
        "open_interest_change_pct": change,
        "funding_available": fr is not None,
        "open_interest_available": now is not None,
        "available": fr is not None or now is not None,
    }
