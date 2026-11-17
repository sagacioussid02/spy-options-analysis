"""Buy and sell through the Sutra adapter, off by default.

When ``SPY_DESK_SUTRA_TRADING`` is set, the adapter lists one more tool,
``place_desk_order``. It submits an order the desk has already analysed (a
``review_id`` from ``analyze_trade_request``) through the desk's existing
``execute_confirmed_trade`` path, so every desk check still applies: the risk
gate, whitelist, kill switch, quantity limit, live ramp cap, buying power,
no shorting, one submission per review, and the live switch. When live
trading isn't armed, a buy becomes a simulation proposal and a sell is
refused, exactly as through the stdio server.

On top of that this module adds, for orders arriving through Sutra only:

- a per-order cap and a per-day cap in US dollars, plus a per-day order count,
  all read from the environment each time. Without both dollar caps set, no
  order goes through;
- a ledger (``cma_lab/sutra_orders.json``) of Sutra orders by New York trading
  day, written before the broker is called so a crash can't hide an order;
- an order window: the adapter's broker guard lets ``review_equity_order`` and
  ``place_equity_order`` through only while ``place_desk_order`` is running, in
  that thread. Everything else in the process stays read-only.

Sutra must register ``place_desk_order`` as ``confirm-first`` so each call
waits for the operator's confirmation. Nothing here sets or changes
``SPY_LIVE`` or ``SPY_SIM_ONLY``.
"""
from __future__ import annotations

import contextvars
import json
import math
import os
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import mcp_server

ENABLE_ENV = "SPY_DESK_SUTRA_TRADING"
MAX_ORDER_ENV = "SPY_DESK_SUTRA_MAX_ORDER_USD"
MAX_DAILY_ENV = "SPY_DESK_SUTRA_MAX_DAILY_USD"
MAX_ORDERS_ENV = "SPY_DESK_SUTRA_MAX_DAILY_ORDERS"
DEFAULT_MAX_DAILY_ORDERS = 3

LEDGER_PATH = Path(__file__).resolve().parent / "sutra_orders.json"
MARKET_TZ = ZoneInfo("America/New_York")

# The broker tools an order needs. They pass the guard only inside the window.
ORDER_TOOLS = frozenset({"review_equity_order", "place_equity_order"})

_window: contextvars.ContextVar[bool] = contextvars.ContextVar("sutra_order_window", default=False)
# One Sutra order at a time, so the caps can't be raced.
_order_lock = threading.Lock()


def _env(key: str) -> str | None:
    from lab import lab_env

    return lab_env(key)


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in ("1", "true", "yes")


def enabled() -> bool:
    return _truthy(_env(ENABLE_ENV))


def order_window_open() -> bool:
    return _window.get()


@contextmanager
def _order_window() -> Iterator[None]:
    token = _window.set(True)
    try:
        yield
    finally:
        _window.reset(token)


def _positive(raw: str | None) -> float | None:
    try:
        value = float(raw) if raw not in (None, "") else None
    except ValueError:
        return None
    return value if value is not None and math.isfinite(value) and value > 0 else None


def caps() -> dict[str, Any]:
    max_orders = _positive(_env(MAX_ORDERS_ENV))
    return {
        "max_order_usd": _positive(_env(MAX_ORDER_ENV)),
        "max_daily_usd": _positive(_env(MAX_DAILY_ENV)),
        "max_daily_orders": int(max_orders) if max_orders else DEFAULT_MAX_DAILY_ORDERS,
    }


def status() -> dict[str, Any]:
    """For /api/health: whether Sutra trading is on and capped. No amounts spent."""
    on = enabled()
    c = caps()
    return {"enabled": on, "caps_set": bool(c["max_order_usd"] and c["max_daily_usd"])}


# ----------------------------------------------------------------------- ledger


def _today() -> str:
    return datetime.now(MARKET_TZ).date().isoformat()


def _load() -> list[dict[str, Any]]:
    try:
        data = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    return data if isinstance(data, list) else []


def _save(entries: list[dict[str, Any]]) -> None:
    tmp = LEDGER_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(entries, indent=2), encoding="utf-8")
    os.replace(tmp, LEDGER_PATH)


def _spent_today(entries: list[dict[str, Any]]) -> tuple[float, int]:
    today = [e for e in entries if e.get("day") == _today() and e.get("counts", True)]
    return sum(float(e.get("notional_usd") or 0) for e in today), len(today)


def _update(review_id: str, **changes: Any) -> None:
    entries = _load()
    for entry in reversed(entries):
        if entry.get("review_id") == review_id:
            entry.update(changes)
            break
    _save(entries)


# ------------------------------------------------------------------------ order


def _reference_price(symbol: str, limit_price: float | None) -> float | None:
    if limit_price:
        return float(limit_price)
    from execution import _live_price  # quote only; reads get_equity_quotes

    price = _live_price(symbol)
    return float(price) if price else None


def place_desk_order(review_id: str, acknowledge_doubts: bool = False,
                     proceed_without_analysis: bool = False) -> dict[str, Any]:
    """Submit the exact order of an analysed review, within the Sutra caps."""
    if not enabled():
        return {"error": f"Sutra trading is off ({ENABLE_ENV} is not set). No order was submitted.",
                "order_submitted": False}
    c = caps()
    if not (c["max_order_usd"] and c["max_daily_usd"]):
        return {"error": f"Set {MAX_ORDER_ENV} and {MAX_DAILY_ENV} before trading through Sutra. "
                         "No order was submitted.", "order_submitted": False}

    with _order_lock:
        from trade_analyst import get_trade_review

        review = get_trade_review(review_id)
        if review.get("error"):
            return {**review, "order_submitted": False}
        request = review.get("request") or {}
        symbol = str(request.get("ticker", "")).upper()
        side = request.get("side")
        try:
            quantity = float(request.get("quantity"))
        except (TypeError, ValueError):
            return {"error": "The review has no valid quantity. No order was submitted.", "order_submitted": False}
        limit_price = request.get("limit_price")

        price = _reference_price(symbol, limit_price)
        if not price:
            return {"error": f"Could not get a price for {symbol} to check the Sutra caps. "
                             "No order was submitted.", "order_submitted": False}
        notional = round(quantity * price, 2)
        entries = _load()
        spent, count = _spent_today(entries)
        if notional > c["max_order_usd"]:
            return {"error": f"About ${notional:,.2f} is over the Sutra per-order cap of "
                             f"${c['max_order_usd']:,.2f}. No order was submitted.", "order_submitted": False}
        if spent + notional > c["max_daily_usd"]:
            return {"error": f"This would bring today's Sutra orders to ${spent + notional:,.2f}, over the "
                             f"daily cap of ${c['max_daily_usd']:,.2f}. No order was submitted.",
                    "order_submitted": False}
        if count >= c["max_daily_orders"]:
            return {"error": f"Today's Sutra order limit ({c['max_daily_orders']}) is used up. "
                             "No order was submitted.", "order_submitted": False}

        # Record the order before the broker hears about it.
        entries.append({"day": _today(), "at": datetime.now(timezone.utc).isoformat(),
                        "review_id": review_id, "symbol": symbol, "side": side,
                        "quantity": quantity, "notional_usd": notional,
                        "status": "submitting", "counts": True})
        _save(entries)

        try:
            with _order_window():
                result = mcp_server.execute_confirmed_trade(
                    review_id, confirm=True, acknowledge_doubts=acknowledge_doubts,
                    proceed_without_analysis=proceed_without_analysis)
        except Exception as exc:
            # Unknown whether the broker saw it: keep it counted and say so.
            _update(review_id, status="error", error=type(exc).__name__)
            raise

        result = dict(result) if isinstance(result, dict) else {"result": result}
        submitted = bool(result.get("order_submitted"))
        _update(review_id, status=str(result.get("status") or ("error" if result.get("error") else "done")),
                order_submitted=submitted, counts=submitted)
        result["sutra_caps"] = {
            "order_usd": notional,
            "today_usd": round(spent + (notional if submitted else 0), 2),
            "max_daily_usd": c["max_daily_usd"],
        }
        return result
