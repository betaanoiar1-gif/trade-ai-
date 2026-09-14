from __future__ import annotations
import time
import httpx
import pandas as pd

class MarketDataError(RuntimeError): pass

def _get(url: str, params: dict, timeout: float = 15):
    try:
        r = httpx.get(url, params=params, timeout=timeout)
        r.raise_for_status(); return r.json()
    except Exception as exc:
        raise MarketDataError(f"market data request failed: {url}: {exc}") from exc

class BinancePublic:
    base = "https://api.binance.com"
    def klines(self, symbol="BTCUSDT", interval="1h", limit=500):
        rows=_get(self.base+"/api/v3/klines", {"symbol":symbol,"interval":interval,"limit":limit})
        if not rows: raise MarketDataError("empty klines")
        cols=["open_time","open","high","low","close","volume","close_time","quote_volume","trades","taker_buy_base","taker_buy_quote","ignore"]
        df=pd.DataFrame(rows,columns=cols)
        for c in ["open","high","low","close","volume","quote_volume","taker_buy_base","taker_buy_quote"]: df[c]=pd.to_numeric(df[c],errors="coerce")
        df["open_time"]=pd.to_datetime(df["open_time"],unit="ms",utc=True); df["close_time"]=pd.to_datetime(df["close_time"],unit="ms",utc=True)
        if df[["open","high","low","close","volume"]].isna().any().any(): raise MarketDataError("invalid numeric candle data")
        if not df.open_time.is_monotonic_increasing or df.open_time.duplicated().any(): raise MarketDataError("non-monotonic or duplicate candles")
        return df
    def depth(self,symbol="BTCUSDT",limit=100): return _get(self.base+"/api/v3/depth", {"symbol":symbol,"limit":limit})
    def ticker_24h(self,symbol="BTCUSDT"): return _get(self.base+"/api/v3/ticker/24hr", {"symbol":symbol})

class BybitPublic:
    base="https://api.bybit.com"
    def funding(self,symbol="BTCUSDT",category="linear"):
        return _get(self.base+"/v5/market/funding/history", {"category":category,"symbol":symbol,"limit":10}).get("result",{}).get("list",[])
    def open_interest(self,symbol="BTCUSDT",interval="1h",category="linear",limit=50):
        return _get(self.base+"/v5/market/open-interest", {"category":category,"symbol":symbol,"intervalTime":interval,"limit":limit}).get("result",{}).get("list",[])
    def tickers(self,symbol="BTCUSDT",category="linear"):
        return _get(self.base+"/v5/market/tickers", {"category":category,"symbol":symbol}).get("result",{}).get("list",[])
    def liquidations(self,symbol="BTCUSDT",category="linear",limit=50):
        return _get(self.base+"/v5/market/recent-trade", {"category":category,"symbol":symbol,"limit":limit}).get("result",{}).get("list",[])

class DeribitPublic:
    base="https://www.deribit.com/api/v2/public"
    def ticker(self,instrument="BTC-PERPETUAL"): return _get(self.base+"/ticker", {"instrument_name":instrument}).get("result",{})

def data_age_seconds(timestamp)->float:
    ts=pd.Timestamp(timestamp)
    if ts.tzinfo is None: ts=ts.tz_localize("UTC")
    return max(0.0,time.time()-ts.timestamp())
