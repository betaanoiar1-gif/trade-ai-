from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


class Journal:
    def __init__(self, path="state/trades.jsonl"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, event: dict):
        row = {"ts": datetime.now(timezone.utc).isoformat(), **event}
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, default=str) + "\n")

    def read(self):
        if not self.path.exists():
            return []
        return [
            json.loads(x)
            for x in self.path.read_text(encoding="utf-8").splitlines()
            if x.strip()
        ]
