import pandas as pd
from crypto_trader.analysis import detect_regime, orderbook_metrics, derivative_metrics
from crypto_trader.ai import AIGateway, AIError
from crypto_trader.models import RiskLimits, TradePlan
from crypto_trader.risk import validate_plan
from crypto_trader.paper import PaperBroker
from crypto_trader.state import StateStore


def candles(n=260):
    close=pd.Series([100+i*0.1 for i in range(n)])
    return pd.DataFrame({"open":close,"high":close+1,"low":close-1,"close":close,"volume":1000.0})


def test_regime_and_orderbook():
    r=detect_regime(candles()); assert r.name in {"trend","range","high_volatility_range"}
    m=orderbook_metrics({"bids":[[100,2],[99,1]],"asks":[[101,1],[102,1]]}); assert m["available"] and m["spread_bps"]>0


def test_derivatives():
    d=derivative_metrics([{"fundingRate":"0.001"}],[{"openInterest":"110"},{"openInterest":"100"}])
    assert d["funding_rate"]==0.001 and d["open_interest_change_pct"]==10


def test_risk_long_and_short():
    limits=RiskLimits()
    for decision, stop in [("LONG",95),("SHORT",105)]:
        p=TradePlan("BTCUSDT",decision,0.8,stop=stop,take_profit_1=110 if decision=="LONG" else 90)
        out=validate_plan(p,1000,limits,price=100); assert out.allowed and out.qty>0


def test_paper_short_and_stop():
    b=PaperBroker(); assert b.open("BTCUSDT","short",1,100,105)
    events=b.check_exits({"BTCUSDT":106}); assert events and events[0]["reason"]=="stop"


def test_state(tmp_path):
    s=StateStore(str(tmp_path/"state.sqlite3")); s.set("equity",1000); assert s.get("equity")==1000
    s.log_decision("now","BTCUSDT",{"decision":"WAIT"}); assert s.recent_decisions(1)[0]["payload"]["decision"]=="WAIT"; s.close()


def test_ai_plan_extraction():
    r={"choices":[{"message":{"content":"{\"decision\":\"WAIT\",\"confidence\":0.4,\"entry_low\":null,\"entry_high\":null,\"stop\":null,\"take_profit_1\":null,\"take_profit_2\":null,\"thesis\":\"wait\",\"invalidation\":\"none\",\"warnings\":[]}"}}]}
    p=AIGateway.extract_plan(r); assert p["decision"]=="WAIT"
    bad={"choices":[{"message":{"content":"not json"}}]}
    try: AIGateway.extract_plan(bad); assert False
    except AIError: pass
