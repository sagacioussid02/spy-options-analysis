"""
Sleeve tracker — the $50-base / 15%-of-profit-every-2-weeks capital rule
described in conversation, translated into actual state for the first
time. Nothing in cma_lab tracked this before (no prior sleeve/topup code
existed anywhere in the repo); this is the minimal version that gives
execution.py's aggregate exposure cap something real to check against.

sleeve_value() = base + realized P&L accrued since the last topup. Every
~2 weeks, apply_topup_if_due() folds 15% of that accrued profit
permanently into base and resets the accrual counter — a losing stretch
never reduces base, it just leaves nothing to fold in.

Run:
    .venv/bin/python cma_lab/sleeve.py            # print current state
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

import events
from store import store

_COLLECTION = "sleeve"
DEFAULT_BASE = 50.0
TOPUP_INTERVAL_DAYS = 14
TOPUP_RATE = 0.15


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load() -> dict:
    state = store().load(_COLLECTION, None)
    if state is None:
        state = {"base": DEFAULT_BASE, "realized_pnl_since_topup": 0.0, "last_topup_at": _now()}
        store().save(_COLLECTION, state)
    return state


def sleeve_value() -> float:
    state = _load()
    return float(state["base"]) + float(state.get("realized_pnl_since_topup", 0.0))


def record_realized_pnl(pnl: float) -> None:
    """Only call this for mode="live" closes — sim P&L is paper and must
    never move real sleeve dollars."""
    state = _load()
    state["realized_pnl_since_topup"] = float(state.get("realized_pnl_since_topup", 0.0)) + float(pnl)
    store().save(_COLLECTION, state)


def apply_topup_if_due() -> Optional[float]:
    """Returns the topup amount folded into base, or None if not due yet."""
    state = _load()
    last_topup = datetime.fromisoformat(state["last_topup_at"])
    if datetime.now(timezone.utc) - last_topup < timedelta(days=TOPUP_INTERVAL_DAYS):
        return None
    accrued = max(0.0, float(state.get("realized_pnl_since_topup", 0.0)))
    topup = round(accrued * TOPUP_RATE, 2)
    state["base"] = float(state["base"]) + topup
    state["realized_pnl_since_topup"] = 0.0
    state["last_topup_at"] = _now()
    store().save(_COLLECTION, state)
    if topup > 0:
        events.log_event("sleeve_topup", amount=topup, new_base=round(state["base"], 2))
    return topup


if __name__ == "__main__":
    s = _load()
    print(f"base={s['base']:.2f}  accrued_since_topup={s.get('realized_pnl_since_topup', 0.0):.2f}  "
          f"sleeve_value={sleeve_value():.2f}  last_topup_at={s['last_topup_at']}")
