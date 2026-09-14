from __future__ import annotations

from datetime import datetime, timezone

from .models import Position
from .paper import PaperBroker
from .trader import CryptoTrader


class TradingRuntime:
    """Event-driven paper runtime; it never sends real exchange orders."""

    def __init__(self, symbol="BTCUSDT", state_path="data/trader.sqlite3"):
        self.trader = CryptoTrader(symbol, state_path=state_path)
        self.broker = PaperBroker(
            cash=self.trader.limits.starting_equity,
            max_leverage=self.trader.limits.max_leverage,
        )
        self._restore()

    def _restore(self):
        account = self.trader.state.get("paper_account") or {}
        self.broker.cash = float(account.get("cash", self.broker.cash))
        self.broker.realized_pnl = float(account.get("realized_pnl", 0.0))
        self.broker.funding_paid = float(account.get("funding_paid", 0.0))
        positions = self.trader.state.get("paper_positions") or {}
        for symbol, raw in positions.items():
            try:
                self.broker.positions[symbol] = Position(
                    symbol,
                    raw["side"],
                    float(raw["qty"]),
                    float(raw["entry"]),
                    float(raw["stop"]),
                    raw.get("take_profit_1"),
                    raw.get("take_profit_2"),
                )
            except (KeyError, TypeError, ValueError):
                # Corrupt persisted position must not crash the whole runtime.
                continue

    def _persist(self, price: float):
        marks = {self.trader.symbol: price}
        account = {
            "cash": self.broker.cash,
            "equity": self.broker.equity(marks),
            "realized_pnl": self.broker.realized_pnl,
            "funding_paid": self.broker.funding_paid,
        }
        positions = {
            symbol: {
                "side": position.side,
                "qty": position.qty,
                "entry": position.entry,
                "stop": position.stop,
                "take_profit_1": position.take_profit_1,
                "take_profit_2": position.take_profit_2,
            }
            for symbol, position in self.broker.positions.items()
        }
        self.trader.state.set("paper_account", account)
        self.trader.state.set("paper_positions", positions)

    def step(self):
        result = self.trader.analyze()
        snapshot = result.get("snapshot", {})
        price = snapshot.get("price")
        if price is None:
            return result
        price = float(price)

        if not self.broker.positions and result.get("risk", {}).get("allowed") and result.get("plan"):
            plan = result["plan"]
            qty = float(result["risk"]["qty"])
            side = "long" if plan["decision"] == "LONG" else "short"
            opened = self.broker.open(
                self.trader.symbol,
                side,
                qty,
                price,
                float(plan["stop"]),
                plan.get("take_profit_1"),
                plan.get("take_profit_2"),
            )
            result["paper_order"] = {"opened": opened, "side": side, "qty": qty, "price": price}
            if opened:
                self.trader.state.log_trade(
                    datetime.now(timezone.utc).isoformat(),
                    self.trader.symbol,
                    "OPEN",
                    result["paper_order"],
                )

        events = self.broker.check_exits({self.trader.symbol: price})
        result["paper_exits"] = events
        for event in events:
            self.trader.state.log_trade(
                datetime.now(timezone.utc).isoformat(), self.trader.symbol, "CLOSE", event
            )

        self._persist(price)
        result["paper_account"] = {
            "cash": self.broker.cash,
            "equity": self.broker.equity({self.trader.symbol: price}),
            "realized_pnl": self.broker.realized_pnl,
            "funding_paid": self.broker.funding_paid,
            "open_positions": len(self.broker.positions),
        }
        return result
