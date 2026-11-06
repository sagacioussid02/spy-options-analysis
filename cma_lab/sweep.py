"""
Daily sweep — deterministic, no LLM.

Closes open positions when they hit their stop, target, or time_stop,
whichever comes first. Sim-lane positions close as a journal update only
(paper). Live-lane positions place a REAL closing sell order first (see
_close_live_position) — a journal entry marked "closed" must correspond to
an actual flat position at the broker, since execution.py's portfolio
exposure cap and sleeve.py's realized-P&L tracking both trust that. Meant
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
import sys
from datetime import date, datetime, timezone
from typing import Optional

import uuid

import exit_review
import integrity
import order_state
import sleeve
from execution import ACCOUNT, _extract_price, _qty_str
from journal import TradeJournal
from lab import mcp_call_tool
from risk_gate import evaluate_close, load_risk_config

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


def _close_live_position(entry: dict) -> Optional[float]:
    """Places the REAL closing sell order for a mode="live" position that
    hit its stop/target/time_stop. Returns the actual fill price, or None
    if the close couldn't be placed (in which case the caller must NOT
    mark the journal entry closed — a journal saying "closed" for a
    position that's still open at the broker is worse than a sweep pass
    that just tries again next time)."""
    if not ACCOUNT:
        print(f"  [sweep] {entry['id']}: no ROBINHOOD_ACCOUNT_NUMBER, cannot close live position")
        return None
    decision = evaluate_close(entry["symbol"], entry["filled_qty"], load_risk_config())
    print(f"  [sweep] [close-gate] {decision}")
    if not decision.allowed:
        return None
    args = {
        "account_number": ACCOUNT,
        "symbol": entry["symbol"],
        "side": "sell",
        "type": "market",
        "quantity": _qty_str(entry["filled_qty"]),
        "time_in_force": "gfd",
        "market_hours": "regular_hours",
        # Distinct ref_id from the opening order's (which used entry["id"]
        # directly) so this close is its own idempotent action, not a dedup
        # collision with the entry order.
        "ref_id": str(uuid.uuid5(uuid.NAMESPACE_OID, entry["id"] + "-close")),
    }
    try:
        raw = mcp_call_tool("place_equity_order", args)
    except Exception as ex:  # noqa: BLE001
        print(f"  [sweep] {entry['id']}: LIVE close order failed: {ex}")
        return None
    print(f"  [sweep] [close-order] {raw[:400]}")
    ref = args["ref_id"]
    order = order_state.match_record(raw, ref_id=ref) or order_state.match_record(raw)
    if order is None:
        J._update(entry["id"], status="closing", closing_order_ref_id=ref)
        print(f"  [sweep] {entry['id']}: close response unparseable — marked closing, will reconcile")
        return None
    kind = order_state.classify(order)
    if kind == "filled":
        px = order_state.average_price(order) or _quote(entry["symbol"])
        J._update(entry["id"], closing_order_id=str(order["id"]),
                  closing_order_state=str(order["state"]), closing_order_ref_id=ref)
        return px
    if kind == "rejected":
        print(f"  [sweep] {entry['id']}: close order {order['state']} — position stays open")
        return None
    J._update(entry["id"], status="closing", closing_order_id=str(order["id"]),
              closing_order_state=str(order["state"]), closing_order_ref_id=ref)
    print(f"  [sweep] {entry['id']}: close order {order['state']} — marked closing, will reconcile")
    return None


def _fetch_order(order_id: str) -> Optional[dict]:
    try:
        raw = mcp_call_tool("get_equity_orders", {"account_number": ACCOUNT, "order_id": order_id})
    except Exception as ex:  # noqa: BLE001
        print(f"  [sweep] order {order_id}: lookup failed: {ex}")
        return None
    return order_state.match_record(raw, order_id=order_id)


def _finish_close(entry: dict, exit_price: float, why: str) -> None:
    updated = J.close(entry["id"], exit_price=exit_price, reflection=f"Sweep auto-close: {why}.")
    _update_playbook(updated)
    sleeve.record_realized_pnl(updated.get("pnl") or 0.0)
    print(f"  [sweep] closed {entry['id']}: {why}, pnl={updated.get('pnl')}")


def reconcile() -> None:
    """Settle live orders that were pending when last seen: buys that were
    queued/partial and sells that were marked closing. Broker state is truth."""
    if not ACCOUNT:
        return
    for entry in J.orders_needing_reconciliation():
        if entry.get("mode") != "live":
            continue
        closing = entry["status"] == "closing"
        oid = entry.get("closing_order_id") if closing else entry.get("broker_order_id")
        if not oid:
            ref = entry.get("closing_order_ref_id") if closing else entry.get("broker_order_ref_id")
            try:
                raw = mcp_call_tool("get_equity_orders", {"account_number": ACCOUNT})
            except Exception as ex:  # noqa: BLE001
                print(f"  [sweep] {entry['id']}: order list failed: {ex}")
                continue
            order = order_state.match_record(raw, ref_id=ref) if ref else None
        else:
            order = _fetch_order(oid)
        if order is None:
            print(f"  [sweep] {entry['id']}: order not found at broker, still {entry['status']}")
            continue
        kind = order_state.classify(order)
        state = str(order["state"])
        px = order_state.average_price(order)
        qty = order_state.filled_quantity(order)
        if closing:
            if kind == "filled":
                _finish_close(entry, px or _quote(entry["symbol"]) or entry["fill_price"],
                              "closing sell filled")
            elif kind == "rejected":
                J._update(entry["id"], status="executed", closing_order_state=state,
                          closing_order_id=None)
                print(f"  [sweep] {entry['id']}: closing order {state} — back to open")
            else:
                J._update(entry["id"], closing_order_state=state)
        else:
            if kind == "filled":
                J.mark_executed(entry["id"], fill_price=px or entry.get("fill_price") or entry.get("snapshot_price"),
                                filled_qty=qty or float(entry["quantity"]),
                                broker_order_id=str(order["id"]), broker_order_state=state)
                print(f"  [sweep] {entry['id']}: buy filled {qty:g} @ {px}")
            elif kind == "rejected":
                J._update(entry["id"], status="rejected", broker_order_state=state)
                print(f"  [sweep] {entry['id']}: buy {state} — nothing bought")
            else:
                J._update(entry["id"], status=kind, broker_order_state=state,
                          filled_qty=qty or None)


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


def run(*, sim_only: bool = False) -> list[dict]:
    topup = sleeve.apply_topup_if_due()
    if topup:
        print(f"  [sweep] sleeve topup applied: +${topup:.2f}")

    for f in integrity.audit(J):
        print(f"  [sweep] [integrity] excluded {f['id']} {f['symbol']}: {f['reason']}")

    if not sim_only:
        reconcile()

    today = datetime.now(timezone.utc).date()
    closed = []
    for entry in J.open_positions():
        if entry["status"] == "closing":
            continue  # a sell is already in flight; reconcile() settles it
        if sim_only and entry.get("mode") == "live":
            print(f"  [sweep] {entry['id']}: live position skipped (--sim-only)")
            continue
        quote = _quote(entry["symbol"])
        if quote is None:
            print(f"  [sweep] {entry['id']}: no quote for {entry['symbol']}, skipping")
            continue
        lo, hi = integrity.EXIT_RATIO_BOUNDS
        if entry.get("fill_price") and not (lo <= quote / float(entry["fill_price"]) <= hi):
            print(f"  [sweep] {entry['id']} {entry['symbol']}: quote {quote} is implausible "
                  f"vs fill {entry['fill_price']} — ignoring this quote, will retry next sweep")
            continue
        reason = _should_close(entry, quote, today)
        if not reason:
            # No mechanical exit hit — let the model judge the thesis against
            # the entry's own kill_criteria. Close-only; failures mean hold.
            action, why = exit_review.review(entry, quote)
            print(f"  [sweep] exit-review {entry['id']} {entry['symbol']}: {action} — {why}")
            if action != "close":
                continue
            reason = f"discretionary exit ({why})"

        exit_price = quote
        if entry.get("mode") == "live":
            fill = _close_live_position(entry)
            if fill is None:
                print(f"  [sweep] {entry['id']}: live close order did not go through, "
                      f"leaving open — will retry next sweep")
                continue
            exit_price = fill

        if entry.get("mode") == "live":
            _finish_close(entry, exit_price, reason)
            closed.append(J.get(entry["id"]))
            continue
        updated = J.close(entry["id"], exit_price=exit_price,
                          reflection=f"Sweep auto-close: {reason}.")
        _update_playbook(updated)
        print(f"  [sweep] closed {entry['id']}: {reason}, pnl={updated.get('pnl')}")
        closed.append(updated)

    _resolve_shadow()
    _resolve_predictions()
    return closed


if __name__ == "__main__":
    print(f"===== sweep @ {datetime.now(timezone.utc).isoformat()} =====")
    result = run(sim_only="--sim-only" in sys.argv[1:])
    if not result:
        print("  [sweep] nothing to close.")
    else:
        print(json.dumps(result, indent=2))
