from __future__ import annotations
from .data import BinancePublic, BybitPublic, MarketDataError, data_age_seconds
from .indicators import enrich, market_structure
from .analysis import multi_timeframe, orderbook_metrics, derivative_metrics, detect_regime, fibonacci, volume_profile
from .ai import AIGateway, TRADER_SYSTEM, decision_prompt, AIError
from .models import TradePlan, RiskLimits
from .risk import validate_plan
from .state import StateStore

class CryptoTrader:
    """Single-agent crypto trader. Data/quant/risk are deterministic; AI interprets evidence."""
    def __init__(self, symbol="BTCUSDT", state_path="data/trader.sqlite3", limits=None):
        self.symbol=symbol.upper(); self.binance=BinancePublic(); self.bybit=BybitPublic(); self.ai=AIGateway(); self.limits=limits or RiskLimits(); self.state=StateStore(state_path)

    def snapshot(self, interval="1h", limit=500):
        frames={tf:self.binance.klines(self.symbol,tf,limit) for tf in ("1d","4h","1h","15m","5m")}
        base=frames[interval] if interval in frames else frames["1h"]
        df=enrich(base); last=df.iloc[-1]
        depth=self.binance.depth(self.symbol,100)
        funding=self.bybit.funding(self.symbol); oi=self.bybit.open_interest(self.symbol)
        tech={k:(None if last[k]!=last[k] else float(last[k])) for k in ["ema20","ema50","ema200","rsi14","atr14","adx14","vwap","macd","macd_signal","macd_hist","bb_high","bb_low","rel_volume","volume_z"]}
        return {"symbol":self.symbol,"interval":interval,"timestamp":str(last.close_time),"data_age_seconds":data_age_seconds(last.close_time),"price":float(last.close),"technical":tech,"structure":market_structure(df).__dict__,"regime":detect_regime(base).__dict__,"multi_timeframe":multi_timeframe(frames),"orderbook":orderbook_metrics(depth),"derivatives":derivative_metrics(funding,oi),"fibonacci":fibonacci(base),"volume_profile":volume_profile(base)}

    def _account_equity(self) -> float:
        account=self.state.get("paper_account") or {}
        try: return max(0.0, float(account.get("equity", self.limits.starting_equity)))
        except (TypeError, ValueError): return self.limits.starting_equity

    def analyze(self):
        try: snap=self.snapshot()
        except MarketDataError as exc: return {"mode":"blocked","decision":"NO_TRADE","reason":str(exc)}
        if snap["data_age_seconds"] > 180: return {"mode":"blocked","decision":"NO_TRADE","snapshot":snap,"reason":"stale market data"}
        if not self.ai.enabled(): return {"mode":"deterministic","snapshot":snap,"decision":"WAIT","reason":"AI gateway not configured; no autonomous decision is fabricated."}
        try:
            raw=self.ai.chat(TRADER_SYSTEM,decision_prompt(snap)); plan=self.ai.extract_plan(raw)
        except AIError as exc: return {"mode":"blocked","snapshot":snap,"decision":"NO_TRADE","reason":str(exc)}
        self.state.log_decision(snap["timestamp"],self.symbol,plan)
        if plan["decision"] in {"LONG","SHORT"}:
            tp=TradePlan(symbol=self.symbol,decision=plan["decision"],confidence=plan["confidence"],entry_low=plan["entry_low"],entry_high=plan["entry_high"],stop=plan["stop"],take_profit_1=plan["take_profit_1"],take_profit_2=plan["take_profit_2"],thesis=plan["thesis"],invalidation=plan["invalidation"],warnings=tuple(plan["warnings"]),timestamp=snap["timestamp"])
            equity=self._account_equity(); account=self.state.get("paper_account") or {}
            current_exposure=float(account.get("exposure", 0.0) or 0.0)
            risk=validate_plan(tp,equity,self.limits,price=snap["price"],current_exposure=current_exposure)
            return {"mode":"ai","snapshot":snap,"plan":plan,"risk":risk.__dict__,"paper_equity":equity}
        return {"mode":"ai","snapshot":snap,"plan":plan,"risk":{"allowed":False,"reason":"non-executable decision"}}
