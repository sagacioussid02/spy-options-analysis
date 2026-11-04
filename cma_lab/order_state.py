"""Helpers for interpreting Robinhood equity-order responses."""
from __future__ import annotations

import json
from typing import Any


PENDING_STATES = {"new", "queued", "confirmed", "unconfirmed"}
TERMINAL_FAILURE_STATES = {"cancelled", "rejected", "failed", "voided"}


def records(payload: Any) -> list[dict]:
    """Extract order-shaped dictionaries from an MCP JSON response."""
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except (TypeError, json.JSONDecodeError):
            return []
    found: list[dict] = []
    stack = [payload]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            if item.get("id") and item.get("state"):
                found.append(item)
            else:
                stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)
    return found


def match_record(payload: Any, *, order_id: str | None = None,
                 ref_id: str | None = None) -> dict | None:
    orders = records(payload)
    if order_id:
        return next((o for o in orders if str(o.get("id")) == str(order_id)), None)
    if ref_id:
        return next((o for o in orders if o.get("ref_id") == ref_id), None)
    return orders[0] if len(orders) == 1 else None


def filled_quantity(order: dict) -> float:
    for key in ("cumulative_quantity", "filled_quantity", "filled_qty"):
        try:
            value = float(order.get(key) or 0)
        except (TypeError, ValueError):
            continue
        if value >= 0:
            return value
    return 0.0


def average_price(order: dict) -> float | None:
    for key in ("average_price", "avg_fill_price", "price"):
        try:
            value = float(order.get(key))
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    return None


def classify(order: dict) -> str:
    state = str(order.get("state", "")).lower()
    if state == "filled":
        return "filled"
    if state == "partially_filled":
        return "partially_filled"
    if state in PENDING_STATES:
        return "submitted"
    if state in TERMINAL_FAILURE_STATES:
        return "rejected"
    return "reconciliation_required"