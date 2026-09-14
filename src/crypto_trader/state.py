from __future__ import annotations
import json, sqlite3
from pathlib import Path

class StateStore:
    """Small persistent SQLite store; safe for Colab/Drive and local runs."""
    def __init__(self, path: str = "data/trader.sqlite3"):
        self.path = Path(path); self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path, check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS decisions (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, symbol TEXT NOT NULL, payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS trades (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, symbol TEXT NOT NULL, action TEXT NOT NULL, payload TEXT NOT NULL);
        """); self.db.commit()

    def set(self, key: str, value):
        self.db.execute("INSERT INTO kv(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, json.dumps(value, default=str))); self.db.commit()

    def get(self, key: str, default=None):
        row = self.db.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
        return default if not row else json.loads(row[0])

    def log_decision(self, ts: str, symbol: str, payload: dict):
        self.db.execute("INSERT INTO decisions(ts,symbol,payload) VALUES(?,?,?)", (ts, symbol, json.dumps(payload, default=str))); self.db.commit()

    def log_trade(self, ts: str, symbol: str, action: str, payload: dict):
        self.db.execute("INSERT INTO trades(ts,symbol,action,payload) VALUES(?,?,?,?)", (ts, symbol, action, json.dumps(payload, default=str))); self.db.commit()

    def recent_decisions(self, limit: int = 20):
        rows = self.db.execute("SELECT ts,symbol,payload FROM decisions ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [{"ts":r[0], "symbol":r[1], "payload":json.loads(r[2])} for r in rows]

    def recent_trades(self, limit: int = 20):
        rows = self.db.execute("SELECT ts,symbol,action,payload FROM trades ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [{"ts":r[0], "symbol":r[1], "action":r[2], "payload":json.loads(r[3])} for r in rows]

    def close(self): self.db.close()
