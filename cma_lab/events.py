"""
Event log — a durable record of the handful of things that only exist as a
moment in time, not as a queryable field on some other collection. Journal
entries already carry full history (created/executed/closed timestamps), so
"a live order was placed or closed" needs no event of its own here. What
DOES need one: a sleeve-cap block (today just a printed string, gone the
moment the log scrolls), a playbook hypothesis's status actually changing
(playbook.py only keeps the CURRENT status, not a transition history), and
a sleeve topup being applied.

Run:
    .venv/bin/python cma_lab/events.py            # print recent events
"""
from __future__ import annotations

from datetime import datetime, timezone

from store import store

_COLLECTION = "events"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def log_event(kind: str, **fields) -> dict:
    events = store().load(_COLLECTION, []) or []
    event = {"at": _now(), "kind": kind, **fields}
    events.append(event)
    store().save(_COLLECTION, events)
    return event


def recent(n: int = 20) -> list[dict]:
    return (store().load(_COLLECTION, []) or [])[-n:]


if __name__ == "__main__":
    for e in recent(20):
        print(f"{e.get('at', '')[:19]}  {e.get('kind'):24}  "
              f"{ {k: v for k, v in e.items() if k not in ('at', 'kind')} }")
