"""
Shadow trades — regret tracking for committee PASSes.

When the PM passes on a debate, the desk still records what the bull case
WOULD have traded (direction + exit plan), so reflection can later ask "were
we too timid?" with a real hit-rate instead of a vibe. Resolved by
sweep.py's daily pass at the shadow entry's time_stop (not early on a
stop/target touch — the point is "would this have worked out", graded once,
not managed as a live position).
"""
from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

SHADOW_PATH = Path(__file__).parent / "shadow.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ShadowEntry:
    id: str
    created_at: str
    debate_id: Optional[str]
    symbol: str
    side: str
    entry_price: float            # hypothetical entry = live quote at pass time
    exit_plan: dict                # {target, stop, time_stop} from the bull case
    reason: str                    # PM's reason for passing
    status: str = "open"           # open|resolved
    resolved_at: Optional[str] = None
    exit_price: Optional[float] = None
    pnl: Optional[float] = None    # per-share hypothetical — this is regret
                                    # tracking, not P&L accounting

    def to_dict(self) -> dict:
        return asdict(self)


class ShadowStore:
    def __init__(self, path: Path = SHADOW_PATH):
        self.path = path

    def _load(self) -> list[dict]:
        if self.path.exists():
            try:
                return json.loads(self.path.read_text())
            except (json.JSONDecodeError, OSError):
                return []
        return []

    def _save(self, entries: list[dict]) -> None:
        self.path.write_text(json.dumps(entries, indent=2))

    def record_pass(self, *, debate_id: Optional[str], symbol: str, side: str,
                     entry_price: float, exit_plan: dict, reason: str) -> ShadowEntry:
        e = ShadowEntry(id="sh_" + uuid.uuid4().hex[:10], created_at=_now(),
                        debate_id=debate_id, symbol=symbol.upper(), side=side,
                        entry_price=float(entry_price), exit_plan=exit_plan or {},
                        reason=reason)
        entries = self._load()
        entries.append(e.to_dict())
        self._save(entries)
        return e

    def get(self, entry_id: str) -> Optional[dict]:
        return next((e for e in self._load() if e["id"] == entry_id), None)

    def open_entries(self) -> list[dict]:
        return [e for e in self._load() if e["status"] == "open"]

    def resolve(self, entry_id: str, *, exit_price: float) -> Optional[dict]:
        entries = self._load()
        for e in entries:
            if e["id"] == entry_id:
                pnl = (exit_price - e["entry_price"]) if e["side"] == "buy" \
                    else (e["entry_price"] - exit_price)
                e.update(status="resolved", exit_price=exit_price, pnl=pnl,
                         resolved_at=_now())
                self._save(entries)
                return e
        return None

    def summarize(self) -> dict:
        resolved = [e for e in self._load() if e["status"] == "resolved"]
        n = len(resolved)
        would_profit = sum(1 for e in resolved if (e.get("pnl") or 0) > 0)
        return {
            "resolved": n,
            "would_have_profited": would_profit,
            "hit_rate": round(would_profit / n, 2) if n else None,
        }
