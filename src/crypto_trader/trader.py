from __future__ import annotations
from .data import BinancePublic, BybitPublic
from .indicators import enrich, market_structure
from .models import RiskLimits, position_size
from .ai import AIGateway, TRADER_SYSTEM, decision_prompt

class CryptoTrader:
    def __init__(self, symbol="BTCUSDT"):
        self.symbol=symbol; self.binance=BinancePublic(); self.bybit=BybitPublic(); self.ai=AIGateway()
    def snapshot(self, interval="1h", limit=500):
        df=enrich(self.binance.klines(self.symbol,interval,limit)); st=market_structure(df)
        last=df.iloc[-1]
        deriv={"funding":self.bybit.funding(self.symbol),"open_interest":self.bybit.open_interest(self.symbol)}
        return {"symbol":self.symbol,"interval":interval,"timestamp":str(last.close_time),"price":float(last.close),"technical":{k:None if last[k]!=last[k] else float(last[k]) for k in ["ema20","ema50","ema200","rsi14","atr14","adx14","vwap","macd","macd_signal","macd_hist","bb_high","bb_low","rel_volume","volume_z"]},"structure":st.__dict__,"derivatives":deriv}
    def analyze(self):
        snap=self.snapshot()
        if not self.ai.enabled(): return {"mode":"deterministic","snapshot":snap,"decision":"WAIT","reason":"AI gateway not configured; no autonomous decision is fabricated."}
        return self.ai.chat(TRADER_SYSTEM,decision_prompt(snap))
