from __future__ import annotations
from .data import BinancePublic, BybitPublic
from .indicators import enrich, market_structure

class CryptoContext:
    def __init__(self, symbol="BTCUSDT"):
        self.symbol=symbol; self.market=BinancePublic(); self.deriv=BybitPublic()
    def build(self, timeframes=("1d","4h","1h","15m"), limit=300):
        frames={}
        for tf in timeframes:
            df=enrich(self.market.klines(self.symbol,tf,limit)); last=df.iloc[-1]
            st=market_structure(df)
            frames[tf]={"price":float(last.close),"rsi":float(last.rsi14),"atr":float(last.atr14),"adx":float(last.adx14),"rel_volume":float(last.rel_volume) if last.rel_volume==last.rel_volume else None,"structure":st.__dict__}
        return {"symbol":self.symbol,"timeframes":frames,"funding":self.deriv.funding(self.symbol),"open_interest":self.deriv.open_interest(self.symbol)}
