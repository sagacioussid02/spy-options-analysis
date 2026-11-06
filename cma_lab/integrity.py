"""
Data-integrity checks for the trade journal — the desk learns from this data,
so a trade built on a bad price must never reach the lessons.

Two layers:
  * pre-trade: price_problem() rejects a limit price that is nowhere near the
    market (a model typo/hallucination, e.g. a 77 limit on a 285 stock).
  * post-hoc: audit() scans the journal and auto-excludes trades whose prices
    are implausible, so a bad fill that slipped through heals itself.
Both are deterministic Python; the LLM has no say.
"""
from __future__ import annotations

import statistics
from typing import Optional

import events

# A limit this far from the live quote is treated as a mistake, not a strategy.
MAX_LIMIT_DEVIATION = 0.05
# Sim limit buys fill only at/through the quote, or within this of the touch.
SIM_TOUCH_TOLERANCE = 0.01
# A closed trade moving more than this from its own entry is implausible for the
# horizons and instruments this desk trades (it caught a 3.8x "win" on SPXL).
EXIT_RATIO_BOUNDS = (0.6, 1.6)
# An entry price this far from the symbol's other recorded prices is suspect.
PEER_DEVIATION = 0.35


def price_problem(limit_price, quote) -> Optional[str]:
    """Reason a limit price is unusable against the live quote, else None."""
    try:
        limit, q = float(limit_price), float(quote)
    except (TypeError, ValueError):
        return None
    if limit <= 0 or q <= 0:
        return None
    dev = abs(limit / q - 1)
    if dev > MAX_LIMIT_DEVIATION:
        return (f"limit ${limit:.2f} is {dev:.0%} from the live quote ${q:.2f} "
                f"(max {MAX_LIMIT_DEVIATION:.0%}) — rejected as a likely mispricing")
    return None


def sim_limit_fill(limit_price, quote) -> Optional[float]:
    """Realistic paper fill for a limit BUY: at the quote if it is at/below the
    limit, at the limit if the quote is within the touch tolerance, else None
    (the order would not have filled)."""
    limit, q = float(limit_price), float(quote)
    if q <= limit:
        return q
    if limit / q >= 1 - SIM_TOUCH_TOLERANCE:
        return limit
    return None


def audit(journal) -> list[dict]:
    """Flag and exclude implausible trades. Returns [{id, reason}] for the
    newly flagged ones. Safe to run repeatedly (already-excluded are skipped)."""
    entries = journal._load()
    flagged: list[dict] = []

    def prices(sym, skip_id):
        out = []
        for e in entries:
            if e["id"] == skip_id or e["symbol"] != sym or e.get("excluded"):
                continue
            for k in ("fill_price", "exit_price"):
                if e.get(k):
                    out.append(float(e[k]))
        return out

    for e in entries:
        if e.get("excluded") or e["status"] not in ("open", "executed", "closed", "closing"):
            continue
        fill, exit_ = e.get("fill_price"), e.get("exit_price")
        reason = None
        if fill and exit_:
            r = float(exit_) / float(fill)
            if not (EXIT_RATIO_BOUNDS[0] <= r <= EXIT_RATIO_BOUNDS[1]):
                reason = (f"exit/fill ratio {r:.2f} outside {EXIT_RATIO_BOUNDS} "
                          f"(fill {fill}, exit {exit_}) — implausible price")
        if reason is None and fill:
            peers = prices(e["symbol"], e["id"])
            if len(peers) >= 3:  # a median of 2 can't say which one is wrong
                med = statistics.median(peers)
                if abs(float(fill) / med - 1) > PEER_DEVIATION:
                    reason = (f"fill ${float(fill):.2f} is far from {e['symbol']}'s other "
                              f"recorded prices (median ${med:.2f}) — suspected bad entry price")
        if reason:
            journal.exclude(e["id"], reason)
            e["excluded"] = True  # keep this pass's snapshot in step: a flagged
            # trade's prices must not count as a "peer" for the ones after it
            events.log_event("integrity_excluded", id=e["id"], symbol=e["symbol"], reason=reason)
            flagged.append({"id": e["id"], "symbol": e["symbol"], "reason": reason})
    return flagged
