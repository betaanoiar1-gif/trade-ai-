from __future__ import annotations
from datetime import datetime, timezone
from .paper import PaperBroker
from .trader import CryptoTrader
from .models import Position

class TradingRuntime:
    """Event-driven paper runtime. One decision cycle never sends a real exchange order."""
    def __init__(self, symbol="BTCUSDT", state_path="data/trader.sqlite3"):
        self.trader=CryptoTrader(symbol,state_path=state_path)
        self.broker=PaperBroker(cash=self.trader.limits.starting_equity,max_leverage=self.trader.limits.max_leverage)
        self._restore()
    def _restore(self):
        a=self.trader.state.get("paper_account")
        if a:
            self.broker.cash=float(a.get("cash",self.broker.cash)); self.broker.realized_pnl=float(a.get("realized_pnl",0)); self.broker.funding_paid=float(a.get("funding_paid",0))
        for s,p in self.trader.state.get("paper_positions",{}).items(): self.broker.positions[s]=Position(s,p["side"],float(p["qty"]),float(p["entry"]),float(p["stop"]),p.get("take_profit_1"),p.get("take_profit_2"))
    def _persist(self, price: float):
        self.trader.state.set("paper_account",{"cash":self.broker.cash,"equity":self.broker.equity({self.trader.symbol:price}),"realized_pnl":self.broker.realized_pnl,"funding_paid":self.broker.funding_paid})
        self.trader.state.set("paper_positions",{s:{"side":p.side,"qty":p.qty,"entry":p.entry,"stop":p.stop,"take_profit_1":p.take_profit_1,"take_profit_2":p.take_profit_2} for s,p in self.broker.positions.items()})
    def step(self):
        result=self.trader.analyze(); snap=result.get("snapshot",{}); price=snap.get("price")
        if price is None: return result
        price=float(price)
        if not self.broker.positions and result.get("risk",{}).get("allowed") and result.get("plan"):
            p=result["plan"]; qty=float(result["risk"]["qty"]); side="long" if p["decision"]=="LONG" else "short"
            opened=self.broker.open(self.trader.symbol,side,qty,price,float(p["stop"]),p.get("take_profit_1"),p.get("take_profit_2")); result["paper_order"]={"opened":opened,"side":side,"qty":qty,"price":price}
            if opened: self.trader.state.log_trade(datetime.now(timezone.utc).isoformat(),self.trader.symbol,"OPEN",result["paper_order"])
        events=self.broker.check_exits({self.trader.symbol:price}); result["paper_exits"]=events
        for event in events: self.trader.state.log_trade(datetime.now(timezone.utc).isoformat(),self.trader.symbol,"CLOSE",event)
        self._persist(price); result["paper_account"]={"cash":self.broker.cash,"equity":self.broker.equity({self.trader.symbol:price}),"realized_pnl":self.broker.realized_pnl,"funding_paid":self.broker.funding_paid,"open_positions":len(self.broker.positions)}
        return result
