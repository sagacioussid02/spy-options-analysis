"""
Daily sweep — deterministic, no LLM.

Closes open positions (currently: sim-lane positions opened via execute_sim)
when they hit their stop, target, or time_stop, whichever comes first. Meant
to run once a day after the engine, piggybacked on the existing decision-view
launchd job.

Idempotent: only entries with status "open" are considered, and close()
flips status to "closed", so running this twice in a row is a no-op the
second time.

Also calls playbook/shadow/prediction resolution hooks — stubbed until those
subsystems exist (Phases 3/5/6 of openspec/changes/agentic-trader-v2).

Run:
    .venv/bin/python cma_lab/sweep.py
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone

from execution import _extract_price
from journal import TradeJournal
from lab import mcp_call_tool

J = TradeJournal()


def _quote(symbol: str) -> float | None:
    try:
        return _extract_price(mcp_call_tool("get_equity_quotes", {"symbols": [symbol]}))
    except Exception:  # noqa: BLE001
        return None


def _should_close(entry: dict, quote: float, today: date) -> str | None:
    """Returns a close reason string, or None to keep the position open."""
    plan = entry.get("exit_plan") or {}
    target, stop, time_stop = plan.get("target"), plan.get("stop"), plan.get("time_stop")
    side = entry.get("side", "buy")
    if side == "buy":
        if target is not None and quote >= float(target):
            return f"target {target} hit (quote {quote})"
        if stop is not None and quote <= float(stop):
            return f"stop {stop} hit (quote {quote})"
    else:  # sells / shorts, if ever allowed — mirror the logic
        if target is not None and quote <= float(target):
            return f"target {target} hit (quote {quote})"
        if stop is not None and quote >= float(stop):
            return f"stop {stop} hit (quote {quote})"
    if time_stop:
        try:
            if today >= date.fromisoformat(str(time_stop)):
                return f"time_stop {time_stop} reached"
        except ValueError:
            pass
    return None


def _update_playbook(entry: dict) -> None:
    """Deterministic trial-stat update + graduation/retirement rule, if this
    entry came from a registered hypothesis."""
    if not entry.get("hypothesis_id"):
        return
    from playbook import Playbook
    Playbook().update_from_close(entry)


def _resolve_shadow() -> None:
    """Resolve shadow (PM PASS) entries at their time_stop — graded once, not
    managed like a live position (no early stop/target exit)."""
    from shadow import ShadowStore
    today = datetime.now(timezone.utc).date()
    store = ShadowStore()
    for e in store.open_entries():
        time_stop = (e.get("exit_plan") or {}).get("time_stop")
        if not time_stop:
            continue
        try:
            if today < date.fromisoformat(str(time_stop)):
                continue
        except ValueError:
            continue
        quote = _quote(e["symbol"])
        if quote is None:
            print(f"  [sweep] shadow {e['id']}: no quote for {e['symbol']}, skipping")
            continue
        resolved = store.resolve(e["id"], exit_price=quote)
        print(f"  [sweep] shadow {e['id']} resolved: pnl/share={resolved.get('pnl')}")


def _resolve_predictions() -> None:
    """Auto-resolve matured PRICE predictions from quotes — deterministic, no
    NLP/LLM involved. Non-price predictions are resolved by reflect.py
    (web_search + justification) or overridden via advisor.py's /resolve."""
    from predictions import PredictionStore
    resolved = PredictionStore().resolve_price_predictions(_quote)
    for r in resolved:
        print(f"  [sweep] prediction {r['id']} resolved: outcome={r['outcome']} "
              f"brier={r['brier']}")


def run() -> list[dict]:
    today = datetime.now(timezone.utc).date()
    closed = []
    for entry in J.open_positions():
        quote = _quote(entry["symbol"])
        if quote is None:
            print(f"  [sweep] {entry['id']}: no quote for {entry['symbol']}, skipping")
            continue
        reason = _should_close(entry, quote, today)
        if not reason:
            continue
        updated = J.close(entry["id"], exit_price=quote,
                          reflection=f"Sweep auto-close: {reason}.")
        _update_playbook(updated)
        print(f"  [sweep] closed {entry['id']}: {reason}, pnl={updated.get('pnl')}")
        closed.append(updated)

    _resolve_shadow()
    _resolve_predictions()
    return closed


if __name__ == "__main__":
    print(f"===== sweep @ {datetime.now(timezone.utc).isoformat()} =====")
    result = run()
    if not result:
        print("  [sweep] nothing to close.")
    else:
        print(json.dumps(result, indent=2))
