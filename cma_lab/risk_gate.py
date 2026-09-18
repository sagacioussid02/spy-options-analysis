"""
Chunk 4 — the deterministic risk gate.

This is the guardrail that does NOT depend on the model's judgment. It's plain
Python that inspects an order BEFORE it ever reaches your approval prompt. If the
order violates a hard limit, it's auto-denied and you're never even asked — so a
runaway agent can't pester you into approving something dangerous, and an order
that slips past the prompt (fat-finger 'y') still can't break a limit.

Design principle from the migration plan: "Risk gate validates limits and account
constraints before execution." Keep this as code, never as an LLM agent — limits
must be unbypassable.

It is ORDER-TOOL-AGNOSTIC: it recognizes equity AND option order tools by name,
so it already protects place_option_order the moment Robinhood enables it.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from lab import lab_env
from store import store

# The single active ticker (see lab.py) — same env/`.env` lookup lab.py's
# own TICKER constant uses, so risk_gate and every agent agree on it.
TICKER = lab_env("TICKER", "SPY")

# Tool-name classification (covers the rolling-out option tools too).
PLACE_TOOLS = {"place_equity_order", "place_option_order"}
CANCEL_TOOLS = {"cancel_equity_order", "cancel_option_order"}
SIMULATE_TOOLS = {"review_equity_order", "review_option_order"}  # no state change


@dataclass
class RiskConfig:
    """Hard limits. Tune per your risk tolerance; these are conservative."""
    kill_switch: bool = False              # True => block ALL order activity
    equity_only: bool = True               # True => block ALL option order tools (stocks only)
    symbol_whitelist: tuple = (TICKER,)    # only these underlyings may be traded
    allowed_sides: tuple = ("buy",)        # long-only (Robinhood agentic = long only anyway)
    max_quantity: float = 5                # max contracts (options) or shares (equity) per order
    max_notional_per_order: float = 1500.0 # $ cap when price is known
    allow_simulations: bool = True         # review_* (dry-run) calls allowed


# Option order tools — blocked entirely while RiskConfig.equity_only is True.
OPTION_ORDER_TOOLS = {"place_option_order", "review_option_order", "cancel_option_order"}


@dataclass
class RiskDecision:
    allowed: bool
    reasons: list = field(default_factory=list)

    def __str__(self) -> str:
        verdict = "ALLOW" if self.allowed else "DENY"
        return f"[risk-gate {verdict}] " + "; ".join(self.reasons)


def _num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def evaluate(tool_name: str, tool_input: dict, cfg: RiskConfig) -> RiskDecision:
    """
    Decide whether an order tool call is permitted by the hard limits.

    Returns RiskDecision(allowed, reasons). `reasons` always explains why — both
    for denials (so you/the agent know what to fix) and approvals (audit trail).
    """
    tool_input = tool_input or {}

    # 1. Kill switch: blocks every state-changing order tool, unconditionally.
    if cfg.kill_switch and (tool_name in PLACE_TOOLS or tool_name in CANCEL_TOOLS):
        return RiskDecision(False, ["KILL SWITCH active — all order activity blocked"])

    # 1b. Equity-only mode: agents trade STOCKS, not options. Hard-blocks every
    # option order tool even after Robinhood enables them — flip equity_only to
    # False (deliberately) when you're ready to let the agent trade options.
    if cfg.equity_only and tool_name in OPTION_ORDER_TOOLS:
        return RiskDecision(False, ["equity-only mode: option trading disabled for agents"])

    # 2. Cancels reduce risk — always permit (unless kill switch already blocked).
    if tool_name in CANCEL_TOOLS:
        return RiskDecision(True, ["cancel is risk-reducing — permitted"])

    # 3. Simulations / reviews never move money.
    if tool_name in SIMULATE_TOOLS:
        if cfg.allow_simulations:
            return RiskDecision(True, ["dry-run review — no state change"])
        return RiskDecision(False, ["simulations disabled in config"])

    # 4. Anything that isn't a place-order tool is out of scope (reads, watchlists).
    if tool_name not in PLACE_TOOLS:
        return RiskDecision(True, [f"{tool_name} is not an order tool — out of scope"])

    # 5. It's a real order. Run the hard checks.
    reasons: list = []
    symbol = str(tool_input.get("symbol") or tool_input.get("underlying") or "").upper()
    side = str(tool_input.get("side") or "").lower()
    qty = _num(tool_input.get("quantity") or tool_input.get("contracts") or tool_input.get("shares"))
    price = _num(tool_input.get("price") or tool_input.get("limit_price"))

    whitelist = {s.upper() for s in cfg.symbol_whitelist}
    if not symbol:
        reasons.append("no symbol/underlying present in order")
    elif symbol not in whitelist:
        reasons.append(f"symbol {symbol!r} not in whitelist {sorted(whitelist)}")

    if side and side not in cfg.allowed_sides:
        reasons.append(f"side {side!r} not allowed (allowed: {list(cfg.allowed_sides)})")

    if qty is None:
        reasons.append("quantity missing/unparseable")
    elif qty > cfg.max_quantity:
        reasons.append(f"quantity {qty:g} exceeds max {cfg.max_quantity:g}")
    elif qty <= 0:
        reasons.append(f"quantity {qty:g} must be positive")

    # Notional check only when price is known. Options carry a 100x multiplier.
    if price is not None and qty is not None and qty > 0:
        multiplier = 100 if tool_name == "place_option_order" else 1
        notional = price * qty * multiplier
        if notional > cfg.max_notional_per_order:
            reasons.append(
                f"notional ${notional:,.0f} exceeds cap ${cfg.max_notional_per_order:,.0f}"
            )

    if reasons:
        return RiskDecision(False, reasons)
    return RiskDecision(True, [f"{tool_name} passes all hard limits"])


# ===================== runtime overrides (copilot-tweakable) =================
# The copilot can adjust these within HARD caps. Stored in the "risk_overrides"
# collection (risk_overrides.json locally) so the change persists and the
# guarded trading agent picks it up on its next run.

APPETITE_PRESETS = {
    "conservative": {"max_quantity": 1, "max_notional_per_order": 700.0},
    "moderate":     {"max_quantity": 3, "max_notional_per_order": 1500.0},
    "aggressive":   {"max_quantity": 5, "max_notional_per_order": 3000.0},
}
# Absolute ceilings the copilot can NEVER exceed, no matter what it's told.
HARD_MAX_QUANTITY = 10
HARD_MAX_NOTIONAL = 5000.0


def load_overrides() -> dict:
    return store().load("risk_overrides", {}) or {}


def save_overrides(overrides: dict) -> None:
    store().save("risk_overrides", overrides)


def load_risk_config() -> RiskConfig:
    """Build the effective RiskConfig: conservative defaults, with copilot
    overrides applied and clamped to the hard ceilings. equity_only and the
    SPY/long-only posture are POLICY-LOCKED — never overridable from chat."""
    cfg = RiskConfig()
    ov = load_overrides()

    appetite = ov.get("risk_appetite")
    if appetite in APPETITE_PRESETS:
        cfg.max_quantity = APPETITE_PRESETS[appetite]["max_quantity"]
        cfg.max_notional_per_order = APPETITE_PRESETS[appetite]["max_notional_per_order"]

    if ov.get("max_quantity") is not None:
        cfg.max_quantity = max(1, min(float(ov["max_quantity"]), HARD_MAX_QUANTITY))
    if ov.get("max_notional_per_order") is not None:
        cfg.max_notional_per_order = min(float(ov["max_notional_per_order"]), HARD_MAX_NOTIONAL)
    if "kill_switch" in ov:
        cfg.kill_switch = bool(ov["kill_switch"])

    cfg.equity_only = True  # locked: options stay off regardless of overrides
    return cfg


# --------------------------- self-test / demo --------------------------------
if __name__ == "__main__":
    cfg = RiskConfig()  # SPY-only, long-only, max 5, $1500 cap
    cases = [
        ("place_equity_order", {"symbol": "SPY", "side": "buy", "quantity": 3, "price": 400}),
        ("place_equity_order", {"symbol": "TSLA", "side": "buy", "quantity": 1}),       # bad symbol
        ("place_equity_order", {"symbol": "SPY", "side": "sell", "quantity": 1}),        # bad side
        ("place_equity_order", {"symbol": "SPY", "side": "buy", "quantity": 50}),        # too many
        ("place_option_order", {"underlying": "SPY", "side": "buy", "contracts": 2, "price": 3.0}),  # blocked: equity-only
        ("review_equity_order", {"symbol": "SPY", "side": "buy", "quantity": 100}),      # dry-run ok
        ("get_portfolio", {"account_number": "123"}),                                     # read, out of scope
    ]
    print("RiskConfig:", cfg, "\n")
    for name, inp in cases:
        d = evaluate(name, inp, cfg)
        print(f"{name:22} {inp}")
        print(f"    -> {d}\n")

    print("--- kill switch ON ---")
    kcfg = RiskConfig(kill_switch=True)
    print(evaluate("place_equity_order", {"symbol": "SPY", "side": "buy", "quantity": 1}, kcfg))
    print(evaluate("cancel_equity_order", {"account_number": "1", "order_id": "x"}, kcfg))

    print("\n--- options ENABLED (equity_only=False): notional check resumes ---")
    ocfg = RiskConfig(equity_only=False)
    print(evaluate("place_option_order", {"underlying": "SPY", "side": "buy", "contracts": 2, "price": 9.0}, ocfg))  # $1800 > cap
    print(evaluate("place_option_order", {"underlying": "SPY", "side": "buy", "contracts": 2, "price": 3.0}, ocfg))  # ok ($600)
