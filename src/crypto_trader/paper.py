from __future__ import annotations
from dataclasses import dataclass, field
from .models import Position

@dataclass
class PaperBroker:
    """Perpetual-futures paper broker with explicit fee/slippage and leverage cap."""
    cash: float = 1000.0
    fee_rate: float = 0.0005
    slippage_bps: float = 5.0
    max_leverage: float = 3.0
    positions: dict[str,Position] = field(default_factory=dict)
    realized_pnl: float = 0.0

    def _fill(self, price: float, side: str) -> float:
        slip=price*(self.slippage_bps/10000)
        return price+slip if side=="buy" else price-slip

    def open(self, symbol: str, side: str, qty: float, price: float, stop: float, tp1=None, tp2=None):
        if qty<=0 or symbol in self.positions or side not in {"long","short"}: return False
        fill=self._fill(price,"buy" if side=="long" else "sell"); notional=fill*qty; fee=notional*self.fee_rate
        if notional > self.cash*self.max_leverage or fee > self.cash: return False
        self.cash-=fee
        self.positions[symbol]=Position(symbol,side,qty,fill,stop,tp1,tp2); return True

    def close(self, symbol: str, price: float) -> float:
        p=self.positions.pop(symbol,None)
        if not p: return 0.0
        exitp=self._fill(price,"sell" if p.side=="long" else "buy")
        pnl=(exitp-p.entry)*p.qty if p.side=="long" else (p.entry-exitp)*p.qty
        fee=exitp*p.qty*self.fee_rate; net=pnl-fee
        self.cash+=net; self.realized_pnl+=net; return net

    def equity(self, marks: dict[str,float]) -> float:
        value=self.cash
        for s,p in self.positions.items():
            mark=marks.get(s,p.entry); value += (mark-p.entry)*p.qty if p.side=="long" else (p.entry-mark)*p.qty
        return value
