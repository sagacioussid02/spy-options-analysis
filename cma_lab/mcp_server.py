"""Local stdio MCP server exposing SPY desk capabilities to Sutra.

Run from the repository root with:
    .venv/bin/python cma_lab/mcp_server.py

The server has no raw, ungated order-placement/cancellation tools. Its only
live order path is a separate explicit-confirmation tool with host-side risk
checks. Imports that access project state are lazy so clients can discover the
catalog without initializing broker credentials.
"""
from __future__ import annotations

import json
import math
import os
import subprocess
import sys
import threading
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

REPO_ROOT = Path(__file__).resolve().parent.parent
DECISION_PATH = REPO_ROOT / "spy_decision_engine" / "reports" / "final_decision.json"
MAX_LIST_LIMIT = 50
MAX_PAPER_SWEEP_POSITIONS = 10
ENGINE_TIMEOUT_SECONDS = 900

mcp = FastMCP("spy-desk")
_trade_execute_lock = threading.Lock()


def _read_decision() -> dict[str, Any]:
    if not DECISION_PATH.exists():
        return {"error": "No engine report found. Run run_engine first."}
    try:
        return json.loads(DECISION_PATH.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        return {"error": f"Could not read engine report: {exc}"}


def _limit(value: int, default: int = 10) -> int:
    return max(1, min(int(value or default), MAX_LIST_LIMIT))


@mcp.tool(description="Read the latest engine decision report. Does not refresh analysis or place orders.")
def get_engine_signal() -> dict[str, Any]:
    """Return the latest score, signal, market conditions, and rationale."""
    return _read_decision()


@mcp.tool(description="Read recent committee debates, including Bull/Bear cases and PM outcome.")
def get_recent_debates(limit: int = 5) -> list[dict[str, Any]]:
    from store import store

    docs = store().load("debates", {}) or {}
    debates = sorted(docs.values(), key=lambda item: item.get("created_at", ""))
    return debates[-_limit(limit):]


@mcp.tool(description="Read the desk journal's performance summary. No writes or broker calls.")
def get_journal_summary() -> dict[str, Any]:
    from journal import TradeJournal

    return TradeJournal().summarize()


@mcp.tool(description="Read recent journal entries, including proposals and actual execution status.")
def get_recent_trades(limit: int = 10) -> list[dict[str, Any]]:
    from journal import TradeJournal

    return TradeJournal().recent(_limit(limit))


@mcp.tool(description="Read open positions from the project journal; these are journaled positions, not a broker reconciliation.")
def get_open_positions() -> list[dict[str, Any]]:
    from journal import TradeJournal

    return TradeJournal().open_positions()


@mcp.tool(description="Read journal orders awaiting broker reconciliation; does not contact the broker.")
def get_unreconciled_orders() -> list[dict[str, Any]]:
    from journal import TradeJournal

    return TradeJournal().orders_needing_reconciliation()

def _broker_account() -> str | None:
    from execution import ACCOUNT

    return ACCOUNT


@mcp.tool(description="Read Robinhood account balances and buying power. This tool is read-only.")
def get_broker_account() -> dict[str, Any]:
    from execution import ACCOUNT
    from lab import account_standing

    if not ACCOUNT:
        return {"error": "ROBINHOOD_ACCOUNT_NUMBER is not configured for this process."}
    try:
        return account_standing(ACCOUNT)
    except Exception as exc:  # noqa: BLE001
        return {"error": f"Robinhood account read failed: {exc}"}


@mcp.tool(description="Read current Robinhood equity positions. This is broker state, separate from the local project journal.")
def get_broker_positions() -> dict[str, Any]:
    from lab import mcp_call_tool

    account = _broker_account()
    if not account:
        return {"error": "ROBINHOOD_ACCOUNT_NUMBER is not configured for this process."}
    try:
        return json.loads(mcp_call_tool("get_equity_positions", {"account_number": account}))
    except Exception as exc:  # noqa: BLE001
        return {"error": f"Robinhood positions read failed: {exc}"}


@mcp.tool(description="Read Robinhood equity order history. This tool never places or modifies orders.")
def get_broker_orders(order_id: str | None = None) -> dict[str, Any]:
    from lab import mcp_call_tool

    account = _broker_account()
    if not account:
        return {"error": "ROBINHOOD_ACCOUNT_NUMBER is not configured for this process."}
    args = {"account_number": account}
    if order_id:
        args["order_id"] = str(order_id).strip()
    try:
        return json.loads(mcp_call_tool("get_equity_orders", args))
    except Exception as exc:  # noqa: BLE001
        return {"error": f"Robinhood order-history read failed: {exc}"}


@mcp.tool(description="Read-only status for one whitelisted ticker: broker-held shares, recent broker order records, and matching local journal entries. Never changes state.")
def get_ticker_trade_status(ticker: str) -> dict[str, Any]:
    from journal import TradeJournal
    from lab import mcp_call_tool
    from risk_gate import load_risk_config

    symbol = str(ticker).strip().upper()
    allowed = {item.upper() for item in load_risk_config().symbol_whitelist}
    if symbol not in allowed:
        return {"error": f"{symbol} is not in the active trade whitelist.",
                "allowed_symbols": sorted(allowed)}
    account = _broker_account()
    if not account:
        return {"error": "ROBINHOOD_ACCOUNT_NUMBER is not configured for this process."}
    try:
        positions = json.loads(mcp_call_tool("get_equity_positions", {"account_number": account}))
        orders = json.loads(mcp_call_tool("get_equity_orders", {"account_number": account}))
    except Exception as exc:  # noqa: BLE001
        return {"error": f"Broker status read failed: {exc}"}

    broker_positions = [
        item for item in (positions.get("data") or {}).get("positions", [])
        if str(item.get("symbol", "")).upper() == symbol
    ]
    broker_orders = []
    stack = [orders]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            if str(item.get("symbol", "")).upper() == symbol and item.get("state"):
                broker_orders.append({key: item.get(key) for key in (
                    "id", "symbol", "side", "type", "state", "quantity",
                    "cumulative_quantity", "average_price", "ref_id",
                ) if key in item})
            else:
                stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)
    journal = [entry for entry in TradeJournal().recent(MAX_LIST_LIMIT)
               if str(entry.get("symbol", "")).upper() == symbol]
    return {"ticker": symbol, "broker_positions": broker_positions,
            "broker_orders": broker_orders, "journal_entries": journal}


@mcp.tool(description="Read effective hard limits, ticker whitelist, and kill-switch state.")
def get_risk_settings() -> dict[str, Any]:
    from risk_gate import load_risk_config

    cfg = load_risk_config()
    return {
        "kill_switch": cfg.kill_switch,
        "equity_only": cfg.equity_only,
        "symbols": list(cfg.symbol_whitelist),
        "allowed_sides": list(cfg.allowed_sides),
        "max_quantity": cfg.max_quantity,
        "max_notional_per_order": cfg.max_notional_per_order,
    }


@mcp.tool(description="Read current distilled desk lessons.")
def get_lessons() -> str:
    import lessons

    return lessons.read_lessons()


@mcp.tool(description="Refresh one whitelisted ticker's engine report. This runs analysis only and cannot place orders.")
def run_engine(ticker: str) -> dict[str, Any]:
    from risk_gate import load_risk_config

    symbol = str(ticker).strip().upper()
    allowed = {item.upper() for item in load_risk_config().symbol_whitelist}
    if symbol not in allowed:
        return {"error": f"Ticker {symbol!r} is not in the configured whitelist.",
                "allowed_symbols": sorted(allowed)}

    env = os.environ.copy()
    env["TICKER"] = symbol
    try:
        result = subprocess.run(
            [sys.executable, "main.py"],
            cwd=REPO_ROOT / "spy_decision_engine",
            env=env,
            capture_output=True,
            text=True,
            timeout=ENGINE_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {"error": f"Engine exceeded {ENGINE_TIMEOUT_SECONDS}s and was stopped."}
    if result.returncode:
        return {"error": "Engine failed.", "exit_code": result.returncode,
                "stderr": result.stderr[-4000:]}

    report = _read_decision()
    report["run_ticker"] = symbol
    report["run_completed_at"] = datetime.now(timezone.utc).isoformat()
    return report


@mcp.tool(description="Record a sim-lane trade proposal for human review. It is not filled and no order is submitted.")
def create_trade_proposal(
    thesis: str,
    conviction: float,
    regime: str,
    strategy: str,
    symbol: str,
    quantity: float,
    entry_style: str,
    kill_criteria: str,
    exit_plan: dict[str, Any],
    side: str = "buy",
    limit_price: float | None = None,
) -> dict[str, Any]:
    from journal import JournalValidationError, TradeJournal
    from risk_gate import evaluate, load_risk_config

    cfg = load_risk_config()
    symbol = str(symbol).strip().upper()
    side = str(side).strip().lower()
    entry_style = str(entry_style).strip().lower()
    try:
        quantity = float(quantity)
        conviction = float(conviction)
        limit_price = float(limit_price) if limit_price is not None else None
    except (TypeError, ValueError):
        return {"error": "quantity, conviction, and limit_price must be numeric."}

    if not math.isfinite(quantity) or not math.isfinite(conviction):
        return {"error": "quantity and conviction must be finite numbers."}
    if not 0 <= conviction <= 1:
        return {"error": "conviction must be between 0 and 1."}
    if limit_price is not None and (not math.isfinite(limit_price) or limit_price <= 0):
        return {"error": "limit_price must be a positive finite number when supplied."}
    if entry_style not in {"market", "limit"}:
        return {"error": "entry_style must be 'market' or 'limit'."}
    if entry_style == "limit" and limit_price is None:
        return {"error": "limit orders require a positive limit_price."}
    if side != "buy":
        return {"error": "Only long equity proposals are supported."}

    order = {"symbol": symbol, "side": side, "type": entry_style, "quantity": quantity}
    if limit_price is not None:
        order["price"] = limit_price
    gate = evaluate("place_equity_order", order, cfg)
    if not gate.allowed:
        return {"error": "Proposal rejected by the local risk gate.", "risk_gate": str(gate)}

    try:
        entry = TradeJournal().propose(
            thesis=thesis,
            conviction=conviction,
            regime=regime,
            strategy=strategy,
            side=side,
            symbol=symbol,
            quantity=quantity,
            entry_style=entry_style,
            limit_price=limit_price,
            kill_criteria=kill_criteria,
            exit_plan=exit_plan,
            mode="sim",
            origin="sutra",
        )
    except JournalValidationError as exc:
        return {"error": str(exc)}

    return {
        "proposal_id": entry.id,
        "status": entry.status,
        "mode": "sim",
        "symbol": symbol,
        "side": side,
        "quantity": quantity,
        "message": "Proposal recorded only. It has not been filled; no broker order was submitted.",
    }


@mcp.tool(description="Reject an existing proposed journal entry. Only status='proposed' entries can be rejected; no broker call is made.")
def reject_trade_proposal(proposal_id: str, note: str = "Rejected via Sutra") -> dict[str, Any]:
    from journal import TradeJournal

    journal = TradeJournal()
    entry = journal.get(str(proposal_id).strip())
    if not entry or entry.get("status") != "proposed":
        return {"error": "No matching proposed entry; nothing changed."}
    rejected = journal.reject(entry["id"], note=note)
    return {"proposal_id": entry["id"], "status": rejected["status"] if rejected else "unknown"}


@mcp.tool(description="Analyze a requested buy/sell before any order. Runs fresh ticker analysis plus a three-year strategy backtest, caches the review, and waits up to 120 seconds. If still running, returns a review_id and wait/proceed choices. This tool never submits orders.")
def analyze_trade_request(
    ticker: str,
    side: str,
    quantity: float,
    entry_style: str = "market",
    limit_price: float | None = None,
    wait_seconds: int = 120,
) -> dict[str, Any]:
    from trade_analyst import start_trade_review

    return start_trade_review(ticker, side, quantity, entry_style, limit_price, wait_seconds)


@mcp.tool(description="Wait for or retrieve an existing cached trade analysis. Maximum wait per call is 120 seconds. This tool never submits orders.")
def wait_for_trade_analysis(review_id: str, wait_seconds: int = 120) -> dict[str, Any]:
    from trade_analyst import wait_for_trade_review

    return wait_for_trade_review(review_id, wait_seconds)


@mcp.tool(description="Retrieve the full cached analyst report for a review_id, including backtest and sentiment details. Read-only.")
def get_trade_analysis_details(review_id: str) -> dict[str, Any]:
    from trade_analyst import get_trade_review

    return get_trade_review(review_id)


@mcp.tool(description="Read-only summary of this ticker's latest cached trade review and current broker/journal status.")
def get_trading_analyst_status(ticker: str) -> dict[str, Any]:
    symbol = str(ticker).strip().upper()
    from trade_analyst import _all_reviews

    matches = [review for review in _all_reviews().values()
               if (review.get("request") or {}).get("ticker") == symbol]
    latest = max(matches, key=lambda item: item.get("created_at", ""), default=None)
    if latest is None:
        return {"ticker": symbol, "status": "no_cached_review",
                "message": "Call analyze_trade_request to start a fresh review."}
    judgment = latest.get("judgment") or {}
    execution = latest.get("execution") or {}
    return {
        "ticker": symbol,
        "review_id": latest["review_id"],
        "analysis_status": latest.get("status"),
        "requested_side": (latest.get("request") or {}).get("side"),
        "judgment": judgment.get("label"),
        "summary": judgment.get("summary") or latest.get("message"),
        "execution_status": execution.get("status", "not_executed"),
        "broker_status": execution.get("broker_status"),
        "order_submitted": execution.get("order_submitted", False),
    }


@mcp.tool(description="Execute a previously analyzed exact order only after confirm=true and the required second confirmation when the analyst reported doubts or analysis is incomplete. Long-only buy or close-owned-shares sell; no shorting. Live orders require SPY_LIVE and pass existing risk, buying-power, quantity, notional, and account checks.")
def execute_confirmed_trade(
    review_id: str,
    confirm: bool,
    acknowledge_doubts: bool = False,
    proceed_without_analysis: bool = False,
) -> dict[str, Any]:
    from execution import (
        ACCOUNT, AUTONOMOUS_MAX_NOTIONAL, J, LIVE_EXECUTION, LIVE_MAX_SHARES,
        _extract_price, _live_price, execute_autonomous,
    )
    from journal import TradeJournal
    from lab import account_standing, mcp_call_tool
    from risk_gate import evaluate, evaluate_close, load_risk_config
    from trade_analyst import get_trade_review

    if confirm is not True:
        return {"error": "Set confirm=true only after reviewing the analysis. No order was submitted.",
            "order_submitted": False}
    review = get_trade_review(review_id)
    if review.get("error"):
        return review
    status = review.get("status")
    if status != "complete" and proceed_without_analysis is not True:
        if status == "running":
            return {"error": "Analysis is still running. Wait for it, or explicitly set proceed_without_analysis=true to authorize the same exact order without results.",
                    "review_id": review_id, "order_submitted": False}
        return {"error": "Analysis is incomplete. To continue anyway, explicitly set proceed_without_analysis=true along with confirm=true.",
                "review_id": review_id, "analysis_status": status, "order_submitted": False}

    judgment = review.get("judgment") or {
        "label": "unreviewed",
        "summary": "User explicitly chose to proceed without completed analysis.",
        "doubts": ["Analysis was not available at execution time."],
        "trend": "unknown",
        "backtest_strategy": {},
    }
    if judgment.get("label") == "doubt" and acknowledge_doubts is not True:
        return {"error": "Analyst has doubts. Read the cached reasons, then set acknowledge_doubts=true along with confirm=true if you still want this order.",
                "review_id": review_id, "doubts": judgment.get("doubts", []),
                "order_submitted": False}

    request = review["request"]
    symbol, side = request["ticker"], request["side"]
    quantity = float(request["quantity"])
    entry_style, limit_price = request["entry_style"], request.get("limit_price")
    cfg = load_risk_config()
    if not ACCOUNT:
        return {"error": "Broker account is not configured.", "order_submitted": False}
    allowed = {item.upper() for item in cfg.symbol_whitelist}
    if symbol not in allowed:
        return {"error": f"{symbol} is not in the active risk whitelist.", "order_submitted": False}
    if quantity > cfg.max_quantity:
        return {"error": f"Quantity {quantity:g} exceeds limit {cfg.max_quantity:g}.", "order_submitted": False}

    if side == "buy":
        gate_order = {"symbol": symbol, "side": "buy", "type": entry_style,
                      "quantity": quantity}
        if limit_price is not None:
            gate_order["price"] = limit_price
        gate = evaluate("place_equity_order", gate_order, cfg)
        if not gate.allowed:
            return {"error": "Current risk settings block this request.",
                    "risk_gate": str(gate), "order_submitted": False}
    elif side == "sell":
        close_gate = evaluate_close(symbol, quantity, cfg)
        if not close_gate.allowed:
            return {"error": str(close_gate), "order_submitted": False}
        try:
            position_result = json.loads(mcp_call_tool(
                "get_equity_positions", {"account_number": ACCOUNT},
            ))
            sellable = sum(
                float(p.get("shares_available_for_sells") or p.get("quantity") or 0)
                for p in (position_result.get("data") or {}).get("positions", [])
                if str(p.get("symbol", "")).upper() == symbol
            )
        except Exception as exc:  # noqa: BLE001
            return {"error": f"Could not verify sellable shares: {exc}", "order_submitted": False}
        if sellable <= 0 or quantity > sellable:
            return {"error": f"Sell refused: requesting {quantity:g} {symbol}, broker reports {sellable:g} sellable shares. Shorting is disabled.",
                    "order_submitted": False}
    else:
        return {"error": "Only buy or sell-to-close requests are supported.", "order_submitted": False}

    with _trade_execute_lock:
        review = get_trade_review(review_id)
        prior = review.get("execution") or {}
        if prior.get("attempted") or prior.get("status") in {"submitting", "submitted", "filled", "partially_filled", "blocked", "recorded_sim_proposal"}:
            return {"error": "This review has already entered execution and cannot be submitted again.",
                    "review_id": review_id, "execution": prior,
                    "order_submitted": prior.get("order_submitted", False)}

        def persist_execution(value: dict[str, Any]) -> None:
            review["execution"] = value
            review["updated_at"] = datetime.now(timezone.utc).isoformat()
            from trade_analyst import _save_review
            _save_review(review)

        if not LIVE_EXECUTION:
            entry = J.propose(
                thesis=f"User-confirmed analyst review {review_id}: {judgment.get('summary', 'analysis bypassed by explicit user choice')}",
                conviction=float(judgment.get("backtest_strategy", {}).get("win_rate", 0) or 0),
                regime=str(judgment.get("trend") or "user_confirmed"),
                strategy="trend_follow", side=side, symbol=symbol, quantity=quantity,
                entry_style=entry_style, limit_price=limit_price,
                kill_criteria="User must review and set exits before live execution.",
                exit_plan={"target": limit_price or 1, "stop": limit_price or 1,
                           "time_stop": datetime.now(timezone.utc).date().isoformat()},
                mode="sim", origin="sutra",
            )
            result = {"status": "recorded_sim_proposal", "proposal_id": entry.id,
                      "order_submitted": False, "attempted": True,
                      "message": "Live execution is not armed; this is a simulation proposal only."}
            persist_execution(result)
            return result

        if side == "sell":
            return _execute_confirmed_sell(
                review_id=review_id, review=review, persist=persist_execution,
                symbol=symbol, quantity=quantity, entry_style=entry_style,
                limit_price=limit_price, account=ACCOUNT, cfg=cfg,
            )
        if side != "buy":
            return {"error": "Only buy or sell-to-close requests are supported.", "order_submitted": False}

        if entry_style == "limit" and not quantity.is_integer():
            return {"error": "Robinhood rejects fractional-share limit orders; no order was submitted.",
                    "order_submitted": False}
        if quantity > LIVE_MAX_SHARES:
            return {"error": f"Live ramp is limited to {LIVE_MAX_SHARES:g} share(s) per order.",
                    "order_submitted": False}
        try:
            exit_plan = _review_exit_plan(review, limit_price)
        except ValueError as exc:
            return {"error": str(exc), "order_submitted": False}
        entry = J.propose(
            thesis=f"User-confirmed trade analyst review {review_id}: {judgment.get('summary', 'analysis bypassed by explicit user choice')}",
            conviction=float(judgment.get("backtest_strategy", {}).get("win_rate", 0) or 0),
            regime=str(judgment.get("trend") or "user_confirmed"),
            strategy="trend_follow", side="buy", symbol=symbol, quantity=quantity,
            entry_style=entry_style, limit_price=limit_price,
            kill_criteria="User-confirmed analyst request; see cached review.",
            exit_plan=exit_plan,
            mode="live", origin="sutra",
        )
        J.approve(entry.id, note=f"Explicit confirmation for review {review_id}")
        entry = J.get(entry.id)
        persist_execution({"status": "submitting", "proposal_id": entry.id,
                           "order_submitted": False, "attempted": True,
                           "message": "Live preflight/submission started; do not retry if this response is interrupted."})
        result = execute_autonomous(entry, allow_resize=False)
        status = J.get(entry.id) or {}
        uncertain = ("place failed" in result.lower()
                 or "unparseable" in result.lower()
                 or status.get("status") == "reconciliation_required")
        submitted = status.get("status") in ("submitted", "partially_filled", "executed")
        execution = {"status": ("reconciliation_required" if uncertain else
                     status.get("status") if submitted else "blocked_or_not_submitted"),
                 "proposal_id": entry.id,
                     "broker_status": status.get("broker_order_state"),
                     "message": result,
                 "order_submitted": submitted or uncertain,
                 "attempted": True,
                 "must_reconcile_before_retry": uncertain}
        persist_execution(execution)
        return execution


def _review_exit_plan(review: dict[str, Any], limit_price: float | None) -> dict[str, Any]:
    final = ((review.get("engine") or {}).get("final_decision") or {})
    rr = final.get("risk_reward") or {}
    target = rr.get("take_profit_target")
    stop = rr.get("stop_loss_level")
    entry = limit_price or (final.get("entry_strategy") or {}).get("recommended_entry")
    if not isinstance(entry, (int, float)) or entry <= 0:
        from execution import _live_price
        entry = _live_price((review.get("request") or {}).get("ticker", ""))
    if not isinstance(target, (int, float)) or not isinstance(stop, (int, float)):
        if not isinstance(entry, (int, float)) or entry <= 0:
            raise ValueError("A fresh positive entry price and exit levels are required before proposing a live buy.")
        target, stop = round(entry * 1.03, 2), round(entry * 0.98, 2)
    return {"target": float(target), "stop": float(stop),
            "time_stop": (datetime.now(timezone.utc).date() + timedelta(days=5)).isoformat()}


def _execute_confirmed_sell(
    *, review_id: str, review: dict[str, Any], persist, symbol: str,
    quantity: float, entry_style: str, limit_price: float | None,
    account: str, cfg,
) -> dict[str, Any]:
    from lab import mcp_call_tool
    from order_state import average_price, classify, match_record

    if cfg.kill_switch:
        return {"error": "Kill switch is active; sell-to-close is blocked.", "order_submitted": False}
    if symbol not in {s.upper() for s in cfg.symbol_whitelist}:
        return {"error": f"{symbol} is outside the active close whitelist.", "order_submitted": False}
    if quantity > cfg.max_quantity:
        return {"error": f"Quantity {quantity:g} exceeds risk limit {cfg.max_quantity:g}.", "order_submitted": False}
    if entry_style == "limit" and limit_price is None:
        return {"error": "limit sell requires limit_price.", "order_submitted": False}
    if not LIVE_EXECUTION:
        return {"error": "Live execution is not armed. No sell order was submitted.", "order_submitted": False}

    try:
        positions = json.loads(mcp_call_tool("get_equity_positions", {"account_number": account}))
        held = 0.0
        for position in (positions.get("data") or {}).get("positions", []):
            if str(position.get("symbol", "")).upper() == symbol:
                held += float(position.get("shares_available_for_sells") or position.get("quantity") or 0)
    except Exception as exc:  # noqa: BLE001
        return {"error": f"Could not verify sellable broker shares: {exc}", "order_submitted": False}
    if quantity > held or held <= 0:
        return {"error": f"Sell refused: requested {quantity:g}; broker reports {held:g} sellable {symbol} shares. Shorting is disabled.",
                "order_submitted": False}
    close_gate = evaluate_close(symbol, quantity, cfg)
    if not close_gate.allowed:
        return {"error": str(close_gate), "order_submitted": False}

    ref_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"spy-desk:{review_id}:sell"))
    order_args = {
        "account_number": account, "symbol": symbol, "side": "sell",
        "type": entry_style, "quantity": str(quantity),
        "time_in_force": "gfd", "market_hours": "regular_hours",
        "ref_id": ref_id,
    }
    if limit_price is not None:
        order_args["limit_price"] = f"{limit_price:.2f}"
    persist({"status": "submitting", "order_submitted": False, "attempted": True,
             "client_reference": ref_id, "side": "sell", "symbol": symbol,
             "quantity": quantity})
    try:
        mcp_call_tool("review_equity_order", {k: v for k, v in order_args.items() if k != "ref_id"})
    except Exception as exc:  # noqa: BLE001
        result = {"status": "preflight_failed", "error": str(exc),
                  "client_reference": ref_id, "order_submitted": False, "attempted": True}
        persist(result)
        return result
    try:
        raw = mcp_call_tool("place_equity_order", order_args)
    except Exception as exc:  # noqa: BLE001
        result = {"status": "reconciliation_required", "error": str(exc),
                  "client_reference": ref_id, "order_submitted": True,
                  "attempted": True,
                  "message": "Submission result is ambiguous; check broker order history before any retry."}
        persist(result)
        return result
    order = match_record(raw, ref_id=ref_id) or match_record(raw)
    if not order:
        result = {"status": "reconciliation_required", "client_reference": ref_id,
                  "order_submitted": True, "attempted": True,
                  "message": "Broker response was not parseable; check order history before retrying."}
        persist(result)
        return result
    state = classify(order)
    result = {"status": state, "client_reference": ref_id,
              "broker_order_id": str(order.get("id")),
              "broker_status": str(order.get("state")),
              "fill_price": average_price(order),
              "filled_quantity": float(order.get("cumulative_quantity") or 0),
              "order_submitted": True, "attempted": True}
    persist(result)
    return result


@mcp.tool(description="Preview mechanical stop/target/time-stop exits. Reads quotes only and changes no state.")
def preview_sweep() -> list[dict[str, Any]]:
    import sweep

    preview = []
    today = datetime.now(timezone.utc).date()
    for entry in sweep.J.open_positions():
        quote = sweep._quote(entry["symbol"])
        if quote is None:
            preview.append({"id": entry["id"], "symbol": entry["symbol"],
                            "status": "quote_unavailable", "would_close": False})
            continue
        reason = sweep._should_close(entry, quote, today)
        preview.append({
            "id": entry["id"],
            "symbol": entry["symbol"],
            "mode": entry.get("mode", "live"),
            "status": entry.get("status"),
            "quote": quote,
            "would_close_mechanically": reason is not None,
            "reason": reason,
            "note": "Preview checks only mechanical exit rules; no discretionary exit review is run.",
        })
    return preview


@mcp.tool(description="Close eligible sim-only journal positions at mechanical stop/target/time-stop. Requires confirm=true. Never touches live positions or submits broker orders.")
def run_paper_sweep(confirm: bool, limit: int = 10) -> dict[str, Any]:
    import sweep

    if confirm is not True:
        return {"error": "Set confirm=true to run the paper sweep. No state changed."}
    max_positions = max(1, min(int(limit or 10), MAX_PAPER_SWEEP_POSITIONS))
    today = datetime.now(timezone.utc).date()
    candidates = [entry for entry in sweep.J.open_positions()
                  if entry.get("mode") == "sim" and entry.get("status") == "open"]
    closed = []
    skipped = []
    for entry in candidates[:max_positions]:
        quote = sweep._quote(entry["symbol"])
        if quote is None:
            skipped.append({"id": entry["id"], "reason": "quote unavailable"})
            continue
        reason = sweep._should_close(entry, quote, today)
        if reason is None:
            continue
        updated = sweep.J.close(
            entry["id"], exit_price=quote,
            reflection=f"Sutra paper sweep: {reason}.",
        )
        if updated:
            sweep._update_playbook(updated)
            closed.append({"id": updated["id"], "symbol": updated["symbol"],
                           "exit_price": quote, "pnl": updated.get("pnl"),
                           "reason": reason})
    return {
        "closed_paper_positions": closed,
        "skipped": skipped,
        "checked": min(len(candidates), max_positions),
        "live_positions_touched": 0,
        "broker_orders_submitted": 0,
        "note": "No discretionary exits, live reconciliation, shadow resolution, prediction resolution, or sleeve top-up was run.",
    }


if __name__ == "__main__":
    mcp.run(transport="stdio")