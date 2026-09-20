"""
Execution — the ONE code path that touches orders (sim or live).

Extracted from advisor.py so committee.py (and any future proposer) shares
exactly this path: propose -> journal -> risk_gate -> execute. The LLM never
holds the trigger; everything below is deterministic host-side Python.
"""
from __future__ import annotations

import json
import re
import uuid

import sleeve
from journal import JournalValidationError, TradeJournal
from lab import TICKER, account_standing, lab_env, mcp_call_tool
from risk_gate import APPETITE_PRESETS, evaluate, load_risk_config

# --- LIVE EXECUTION SAFETY -------------------------------------------------
# Live is OFF unless explicitly armed via env (SPY_LIVE=1) — never a code
# constant you might commit. Even when armed: a hard per-order ceiling for the
# ramp, a pre-trade review, and a typed confirmation before any real order.
LIVE_EXECUTION = (lab_env("SPY_LIVE", "") or "").lower() in ("1", "true", "yes")
LIVE_MAX_SHARES = 1                       # ramp cap: live orders may not exceed this
ACCOUNT = lab_env("ROBINHOOD_ACCOUNT_NUMBER")  # the agentic_allowed account

# Hard ceiling for a committee proposal executed WITHOUT a human present (see
# execute_autonomous below). Same SPY_LIVE switch arms this as arms the
# interactive typed-confirm path — this is not a separate, easier-to-flip
# gate, it's a size cap layered on top of the same one.
AUTONOMOUS_MAX_NOTIONAL = 30.0

J = TradeJournal()

# origin_reason (from the proposer) -> origin (stored on the journal entry).
# "exploration" is the tag the desk tracks to learn whether off-book instinct
# has edge (see exploration.py + journal.summarize()'s by_origin cohort).
_EXPLORATION_REASONS = {"against_engine", "hunch", "untested_playbook"}


def _derive_origin(inp: dict) -> str:
    reason = inp.get("origin_reason")
    if reason in _EXPLORATION_REASONS:
        return "exploration"
    if reason == "engine_aligned":
        return "committee"
    # advisor.py never sends origin_reason — preserves its existing default.
    return str(inp.get("origin", "advisor")).lower()


def h_propose(inp: dict) -> str:
    """Custom-tool handler for `propose_trade` — shared by advisor + committee."""
    mode = str(inp.get("mode", "live")).lower()
    origin = _derive_origin(inp)
    conviction = max(0.0, min(1.0, float(inp.get("conviction", 0))))
    quantity = float(inp.get("quantity", 0))
    notes = []

    # Trial hypotheses are sim-only until they earn live eligibility by the
    # deterministic playbook rule (see playbook.py) — an untested idea doesn't
    # get near real money just because conviction sounds high.
    hypothesis_id = inp.get("hypothesis_id")
    if hypothesis_id and mode == "live":
        from playbook import Playbook
        hyp = Playbook().get(hypothesis_id)
        if hyp and hyp.get("status") == "trial":
            mode = "sim"
            notes.append("Downgraded to sim: trial hypotheses are sim-only until "
                         "they graduate to active.")

    # Live exploration constraint: off-book gut calls don't get to skip the
    # human-approval lane freely — they need real conviction, and even then
    # are capped to the conservative preset regardless of current appetite.
    if mode == "live" and origin == "exploration":
        if conviction < 0.7:
            mode = "sim"
            notes.append(f"Downgraded to sim: live exploration trades require "
                         f"conviction >= 0.7 (was {conviction:.2f}).")
        else:
            cap = APPETITE_PRESETS["conservative"]["max_quantity"]
            if quantity > cap:
                notes.append(f"Resized {quantity:g} -> {cap:g}: live exploration "
                             f"trades are capped to the conservative preset "
                             f"regardless of current risk appetite.")
                quantity = cap

    note = " ".join(notes)

    try:
        e = J.propose(
            thesis=str(inp.get("thesis", "")).strip(),
            conviction=conviction,
            regime=str(inp.get("regime", "unspecified")),
            strategy=str(inp.get("strategy", "unspecified")),
            side=str(inp.get("side", "buy")).lower(),
            symbol=str(inp.get("symbol", TICKER)),
            quantity=quantity,
            entry_style=str(inp.get("entry_style", "market")).lower(),
            limit_price=(float(inp["limit_price"]) if inp.get("limit_price") not in (None, "") else None),
            kill_criteria=str(inp.get("kill_criteria", "")).strip(),
            exit_plan=inp.get("exit_plan") or {},
            mode=mode,
            origin=origin,
            debate_id=inp.get("debate_id"),
            hypothesis_id=inp.get("hypothesis_id"),
        )
    except JournalValidationError as ex:
        return f"Proposal rejected: {ex} Fix the missing field(s) and call propose_trade again."

    if note:
        J._update(e.id, human_notes=note)

    limit = f" @ ${e.limit_price:g}" if e.limit_price else ""
    print(f"\n  ┌─ 📋 PROPOSAL {e.id}")
    print(f"  │  {e.side} {e.quantity:g} {e.symbol} {e.entry_style}{limit}  "
          f"| conviction {e.conviction:.2f} | {e.strategy} / {e.regime}")
    print(f"  │  {e.thesis}")
    print(f"  │  kill_criteria: {e.kill_criteria}")
    print(f"  │  exit_plan: {e.exit_plan}")
    if note:
        print(f"  │  NOTE: {note}")
    print(f"  └─ review it, then:  /approve {e.id}   |   /tweak {e.id} qty=1 limit=687   |   /reject {e.id}\n")
    result = (f"Proposal {e.id} recorded ({e.side} {e.quantity:g} {e.symbol}, "
              f"conviction {e.conviction:.2f}). Awaiting the human's review/approval.")
    return result + f" NOTE: {note}" if note else result


# ------------------------------ execution (host-side) ------------------------
def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _extract_price(text: str):
    """Parse a current price out of an MCP tool result. Robinhood returns price
    fields as STRINGS (e.g. "751.150000"), so a naive isinstance(v, (int,
    float)) check silently matches nothing and falls through to a raw-text
    regex — which can grab a stale reference price (previous_close) instead of
    the live one. Prefer last_trade_price explicitly; only fall back to a
    generic *price* field search (for order review/place responses) after."""
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        data = None

    if data is not None:
        stack = [data]
        while stack:
            cur = stack.pop()
            if isinstance(cur, dict):
                if "last_trade_price" in cur:
                    v = _num(cur["last_trade_price"])
                    if v is not None:
                        return v
                stack.extend(cur.values())
            elif isinstance(cur, list):
                stack.extend(cur)
        stack = [data]
        while stack:
            cur = stack.pop()
            if isinstance(cur, dict):
                for k, v in cur.items():
                    if "price" in k.lower():
                        n = _num(v)
                        if n is not None:
                            return n
                    stack.append(v)
            elif isinstance(cur, list):
                stack.extend(cur)

    m = re.search(r"\b(\d{1,6}\.\d{1,6})\b", text or "")
    return float(m.group(1)) if m else None


def _live_price(symbol: str):
    """Quote for `symbol` — takes it explicitly rather than defaulting to the
    global TICKER, since a basket run has multiple entries in flight with
    different symbols in the same process lifetime (a stale TICKER default
    here would price one ticker's order off another ticker's quote)."""
    try:
        return _extract_price(mcp_call_tool("get_equity_quotes", {"symbols": [symbol]}))
    except Exception:  # noqa: BLE001
        return None


def _qty_str(q) -> str:
    q = float(q)
    return str(int(q)) if q == int(q) else str(q)


def _order_args(entry: dict, include_ref: bool) -> dict:
    """Build Robinhood place/review args (strings, per the MCP schema)."""
    args = {
        "account_number": ACCOUNT,
        "symbol": entry["symbol"],
        "side": entry["side"],
        "type": entry["entry_style"],
        "quantity": _qty_str(entry["quantity"]),
        "time_in_force": "gfd",
        "market_hours": "regular_hours",
    }
    if entry["entry_style"] == "limit" and entry.get("limit_price"):
        args["limit_price"] = f"{float(entry['limit_price']):.2f}"
    if include_ref:
        # Stable idempotency key per journal entry — retries dedup upstream.
        args["ref_id"] = str(uuid.uuid5(uuid.NAMESPACE_OID, entry["id"]))
    return args


def _gate_and_afford(entry: dict) -> tuple[str | None, float]:
    """Shared by execute_approved and execute_sim: risk gate the EXACT order,
    then check it against real buying power. Returns (block_reason_or_None,
    price_used_for_the_check) — never lets a $5 account "fill" a $1,485 order,
    sim or live alike, since buying power is broker truth."""
    gate_order = {"symbol": entry["symbol"], "side": entry["side"],
                  "type": entry["entry_style"], "quantity": entry["quantity"]}
    if entry.get("limit_price"):
        gate_order["price"] = entry["limit_price"]
    decision = evaluate("place_equity_order", gate_order, load_risk_config())
    print(f"  [gate] {decision}")
    if not decision.allowed:
        return "BLOCKED by risk gate — not executed. Proposal stays pending.", 0.0

    px = entry.get("limit_price") or _live_price(entry["symbol"]) or entry.get("snapshot_price") or 0
    notional = float(px) * float(entry["quantity"])
    try:
        bp = account_standing(ACCOUNT)["buying_power"]
    except Exception:  # noqa: BLE001
        bp = None
    if bp is not None and notional > bp + 0.01:
        afford = (bp / px) if px else 0
        return (f"BLOCKED — insufficient buying power: order ~${notional:.2f} vs "
                f"available ${bp:.2f}. You could afford ~{afford:.4f} share. "
                f"Reduce size (/tweak) or fund the account.", px)
    print(f"  [affordability] order ~${notional:.2f} vs buying power "
          f"${bp if bp is None else round(bp, 2)} — OK")
    return None, px


def execute_sim(entry: dict) -> str:
    """Autonomous SIM lane: risk gate -> simulated fill -> journaled OPEN.
    No human approval step — this is what lets the desk run without a human
    in the loop, bounded only by risk_gate + affordability (same as live)."""
    reason, px = _gate_and_afford(entry)
    if reason:
        return reason
    if entry["entry_style"] == "limit" and entry.get("limit_price"):
        fill = entry["limit_price"]
    else:
        fill = _live_price(entry["symbol"]) or entry.get("limit_price") or entry.get("snapshot_price") or px
    J.open_sim(entry["id"], fill_price=float(fill), filled_qty=float(entry["quantity"]))
    return (f"SIM fill: {entry['quantity']:g} {entry['symbol']} @ ${float(fill):.2f}. "
            f"Journaled as open (mode=sim).")


def execute_approved(entry: dict) -> str:
    """Deterministic: risk gate the EXACT approved order, then execute. No LLM."""
    reason, _px = _gate_and_afford(entry)
    if reason:
        return reason

    if LIVE_EXECUTION:
        if not ACCOUNT:
            return "No ROBINHOOD_ACCOUNT_NUMBER in .env — cannot place a live order."
        if float(entry["quantity"]) > LIVE_MAX_SHARES:
            return (f"Live ramp cap: live orders are limited to {LIVE_MAX_SHARES} "
                    f"share(s) for now. /tweak the size down to go live.")
        # 1) Pre-trade review — REAL call, but no order is placed.
        try:
            review = mcp_call_tool("review_equity_order", _order_args(entry, include_ref=False))
        except Exception as ex:  # noqa: BLE001
            return f"Pre-trade review failed: {ex}. Proposal stays approved."
        print(f"  [review] {review[:600]}")
        # 2) Typed confirmation — the real-money gate.
        est = (entry.get("limit_price") or _live_price(entry["symbol"]) or entry.get("snapshot_price") or 0) \
            * float(entry["quantity"])
        confirm = input(f"  ⚠ PLACE REAL ORDER — {entry['quantity']:g} {entry['symbol']} "
                        f"~${est:.0f}. Type LIVE to confirm: ").strip()
        if confirm != "LIVE":
            return "Aborted — not confirmed. Proposal stays approved (re-/approve to retry)."
        # 3) Place — idempotent via ref_id.
        try:
            raw = mcp_call_tool("place_equity_order", _order_args(entry, include_ref=True))
        except Exception as ex:  # noqa: BLE001
            return f"LIVE place failed: {ex}. Proposal stays approved (re-/approve to retry)."
        print(f"  [order] {raw[:400]}")
        fill = _extract_price(raw) or entry.get("limit_price") or entry.get("snapshot_price")
        mode = "LIVE"
    else:
        if entry["entry_style"] == "limit" and entry.get("limit_price"):
            fill = entry["limit_price"]
        else:
            fill = _live_price(entry["symbol"]) or entry.get("limit_price") or entry.get("snapshot_price")
        mode = "SIMULATED"

    J.mark_executed(entry["id"], fill_price=float(fill), filled_qty=float(entry["quantity"]))
    return f"{mode} fill: {entry['quantity']:g} {entry['symbol']} @ ${float(fill):.2f}. Journaled as executed."


def execute_autonomous(entry: dict) -> str:
    """Committee proposals under AUTONOMOUS_MAX_NOTIONAL execute for real with
    NO human confirmation — this is the one path in the whole codebase that
    places a live order without a typed "LIVE". Called only from
    committee.py's make_h_pm_propose, and only after it has independently
    confirmed the same notional cap (belt-and-suspenders: this function
    re-checks so it is never the only place enforcing it).

    Every other guardrail is identical to execute_approved: risk_gate +
    buying-power check via _gate_and_afford, the same LIVE_MAX_SHARES ramp
    cap, a real pre-trade review call, and the same idempotent ref_id so a
    retry can never double-fill."""
    if not LIVE_EXECUTION:
        return "Not armed (SPY_LIVE unset) — autonomous execution skipped; proposal stays pending."
    if not ACCOUNT:
        return "No ROBINHOOD_ACCOUNT_NUMBER configured — cannot place a live order."

    est_price = entry.get("limit_price") or _live_price(entry["symbol"]) or entry.get("snapshot_price") or 0
    notional = float(est_price) * float(entry["quantity"])
    if notional > AUTONOMOUS_MAX_NOTIONAL:
        return (f"${notional:.2f} exceeds the ${AUTONOMOUS_MAX_NOTIONAL:.0f} autonomous cap — "
                f"leaving queued for human /approve via advisor.py.")
    if float(entry["quantity"]) > LIVE_MAX_SHARES:
        return (f"Live ramp cap: live orders are limited to {LIVE_MAX_SHARES} share(s) — "
                f"leaving queued for human /approve via advisor.py.")

    # Portfolio-wide exposure cap — a per-order cap alone doesn't stop a
    # basket of tickers from stacking past the sleeve in aggregate. Valued
    # at each open live position's own fill price x filled qty (no extra
    # live-quote calls — this is a cap check, not a mark-to-market).
    open_notional = sum((e.get("fill_price") or 0) * (e.get("filled_qty") or 0)
                        for e in J.open_positions() if e.get("mode") == "live")
    sleeve_cap = sleeve.sleeve_value()
    if open_notional + notional > sleeve_cap:
        return (f"Would exceed sleeve exposure cap (open ${open_notional:.2f} + this "
                f"${notional:.2f} > sleeve ${sleeve_cap:.2f}) — leaving queued for "
                f"human /approve via advisor.py.")

    reason, _px = _gate_and_afford(entry)
    if reason:
        return reason

    try:
        review = mcp_call_tool("review_equity_order", _order_args(entry, include_ref=False))
    except Exception as ex:  # noqa: BLE001
        return f"Pre-trade review failed: {ex}. Proposal stays pending (not executed)."
    print(f"  [autonomous review] {review[:600]}")

    try:
        raw = mcp_call_tool("place_equity_order", _order_args(entry, include_ref=True))
    except Exception as ex:  # noqa: BLE001
        return f"Autonomous LIVE place failed: {ex}. Proposal stays pending (not executed)."
    print(f"  [autonomous order] {raw[:400]}")

    fill = _extract_price(raw) or entry.get("limit_price") or entry.get("snapshot_price")
    J.mark_executed(entry["id"], fill_price=float(fill), filled_qty=float(entry["quantity"]))
    return (f"AUTONOMOUS LIVE fill: {entry['quantity']:g} {entry['symbol']} @ ${float(fill):.2f} "
            f"(~${notional:.2f}, under the ${AUTONOMOUS_MAX_NOTIONAL:.0f} cap). "
            f"Journaled as executed — no human confirmation.")
