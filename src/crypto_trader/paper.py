from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from .models import Position

@dataclass
class PaperBroker:
    """Deterministic perpetual-futures paper broker: fees, slippage, funding and maintenance margin."""
    cash: float = 1000.0
    fee_rate: float = 0.0005
    slippage_bps: float = 5.0
    max_leverage: float = 3.0
    maintenance_margin_rate: float = 0.005
    positions: dict[str,Position] = field(default_factory=dict)
    realized_pnl: float = 0.0
    funding_paid: float = 0.0

    def _fill(self, price: float, side: str) -> float:
        slip=price*(self.slippage_bps/10000)
        return price+slip if side=="buy" else price-slip

    def open(self, symbol: str, side: str, qty: float, price: float, stop: float, tp1=None, tp2=None):
        if qty<=0 or symbol in self.positions or side not in {"long","short"}: return False
        fill=self._fill(price,"buy" if side=="long" else "sell"); notional=fill*qty; fee=notional*self.fee_rate
        if notional > self.cash*self.max_leverage or fee > self.cash: return False
        self.cash-=fee
        self.positions[symbol]=Position(symbol,side,qty,fill,stop,tp1,tp2)
        return True

    def unrealized(self, symbol: str, mark: float) -> float:
        p=self.positions.get(symbol)
        if not p: return 0.0
        return (mark-p.entry)*p.qty if p.side=="long" else (p.entry-mark)*p.qty

    def equity(self, marks: dict[str,float]) -> float:
        return self.cash + sum(self.unrealized(s,marks.get(s,p.entry)) for s,p in self.positions.items())

    def liquidation_price(self, symbol: str) -> float | None:
        p=self.positions.get(symbol)
        if not p: return None
        # Conservative isolated-style approximation for a paper account.
        if p.side=="long": return p.entry*(1-1/self.max_leverage+self.maintenance_margin_rate)
        return p.entry*(1+1/self.max_leverage-self.maintenance_margin_rate)

    def apply_funding(self, rates: dict[str,float]):
        """Positive funding means longs pay shorts; negative means shorts pay longs."""
        for symbol,p in self.positions.items():
            rate=float(rates.get(symbol,0.0)); payment=p.entry*p.qty*rate
            self.cash -= payment if p.side=="long" else -payment
            self.funding_paid += payment if p.side=="long" else -payment

    def check_exits(self, marks: dict[str,float]) -> list[dict]:
        events=[]
        for symbol,p in list(self.positions.items()):
            mark=marks.get(symbol)
            if mark is None: continue
            liq=self.liquidation_price(symbol)
            hit_liq=(p.side=="long" and mark<=liq) or (p.side=="short" and mark>=liq)
            hit_stop=(p.side=="long" and mark<=p.stop) or (p.side=="short" and mark>=p.stop)
            hit_tp=p.take_profit_1 is not None and ((p.side=="long" and mark>=p.take_profit_1) or (p.side=="short" and mark<=p.take_profit_1))
            if hit_liq:
                pnl=self.close(symbol,liq or mark); events.append({"symbol":symbol,"reason":"liquidation","pnl":pnl})
            elif hit_stop:
                pnl=self.close(symbol,p.stop); events.append({"symbol":symbol,"reason":"stop","pnl":pnl})
            elif hit_tp:
                pnl=self.close(symbol,p.take_profit_1); events.append({"symbol":symbol,"reason":"take_profit","pnl":pnl})
        return events

    def close(self, symbol: str, price: float) -> float:
        p=self.positions.pop(symbol,None)
        if not p: return 0.0
        exitp=self._fill(price,"sell" if p.side=="long" else "buy")
        pnl=(exitp-p.entry)*p.qty if p.side=="long" else (p.entry-exitp)*p.qty
        fee=exitp*p.qty*self.fee_rate; net=pnl-fee
        self.cash+=net; self.realized_pnl+=net
        return net
