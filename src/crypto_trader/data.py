from __future__ import annotations
import httpx, pandas as pd

class MarketDataError(RuntimeError): pass

class BinancePublic:
    base="https://api.binance.com"
    def klines(self,symbol="BTCUSDT",interval="1h",limit=500):
        r=httpx.get(self.base+"/api/v3/klines",params={"symbol":symbol,"interval":interval,"limit":limit},timeout=15); r.raise_for_status(); rows=r.json()
        if not rows: raise MarketDataError("empty klines")
        return pd.DataFrame(rows,columns=["open_time","open","high","low","close","volume","close_time","quote_volume","trades","taker_buy_base","taker_buy_quote","ignore"]).assign(**{c:lambda x:pd.to_numeric(x[c]) for c in ["open","high","low","close","volume"]})
    def depth(self,symbol="BTCUSDT",limit=100):
        r=httpx.get(self.base+"/api/v3/depth",params={"symbol":symbol,"limit":limit},timeout=15); r.raise_for_status(); return r.json()

class BybitPublic:
    base="https://api.bybit.com"
    def funding(self,symbol="BTCUSDT",category="linear"):
        r=httpx.get(self.base+"/v5/market/funding/history",params={"category":category,"symbol":symbol,"limit":1},timeout=15); r.raise_for_status(); return r.json().get("result",{}).get("list",[])
    def open_interest(self,symbol="BTCUSDT",interval="1h",category="linear",limit=50):
        r=httpx.get(self.base+"/v5/market/open-interest",params={"category":category,"symbol":symbol,"intervalTime":interval,"limit":limit},timeout=15); r.raise_for_status(); return r.json().get("result",{}).get("list",[])

class DeribitPublic:
    base="https://www.deribit.com/api/v2/public"
    def ticker(self,instrument="BTC-PERPETUAL"):
        r=httpx.get(self.base+"/ticker",params={"instrument_name":instrument},timeout=15); r.raise_for_status(); return r.json().get("result",{})
