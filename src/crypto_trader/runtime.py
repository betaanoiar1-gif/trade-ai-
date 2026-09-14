from __future__ import annotations
from datetime import datetime, timezone
from .paper import PaperBroker
from .trader import CryptoTrader

class TradingRuntime:
    """Event-driven paper runtime. One decision cycle never sends a real exchange order."""
    def __init__(self, symbol="BTCUSDT", state_path="data/trader.sqlite3"):
        self.trader=CryptoTrader(symbol,state_path=state_path)
        self.broker=PaperBroker(cash=self.trader.limits.starting_equity,max_leverage=self.trader.limits.max_leverage)

    def step(self):
        result=self.trader.analyze()
        snap=result.get("snapshot",{})
        if result.get("risk",{}).get("allowed") and result.get("plan"):
            p=result["plan"]; price=float(snap["price"]); qty=float(result["risk"]["qty"])
            side="long" if p["decision"]=="LONG" else "short"
            opened=self.broker.open(self.trader.symbol,side,qty,price,float(p["stop"]),p.get("take_profit_1"),p.get("take_profit_2"))
            result["paper_order"]={"opened":opened,"side":side,"qty":qty,"price":price}
            if opened:
                self.trader.state.log_trade(datetime.now(timezone.utc).isoformat(),self.trader.symbol,"OPEN",result["paper_order"])
        if snap.get("price") is not None:
            events=self.broker.check_exits({self.trader.symbol:float(snap["price"])})
            result["paper_exits"]=events
            for event in events:
                self.trader.state.log_trade(datetime.now(timezone.utc).isoformat(),self.trader.symbol,"CLOSE",event)
        result["paper_account"]={"cash":self.broker.cash,"equity":self.broker.equity({self.trader.symbol:float(snap["price"])}) if snap.get("price") else self.broker.cash,"realized_pnl":self.broker.realized_pnl,"funding_paid":self.broker.funding_paid,"open_positions":len(self.broker.positions)}
        return result
