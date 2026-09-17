"""
Copilot — a hosted CMA agent you can chat with about your SPY workflow.

What it can do (all read/advisory — it CANNOT place trades):
  - discuss the engine's analysis            (custom tool: get_engine_analysis)
  - look at trades you've made               (custom tool: get_my_trades + Robinhood get_equity_orders)
  - see live account + market                (Robinhood read tools)
  - research sentiment / news / signals       (web_search, web_fetch)
  - tell you your current risk settings       (custom tool: get_risk_settings)
  - tweak risk settings within GUARDRAILS     (custom tool: set_risk_parameter)

The guardrails for parameter tweaks live in host-side code (risk_gate.load_risk_config
+ the handler below), NOT in the model. So "make me aggressive" maps to a bounded
preset; "set max shares to 500" gets clamped to the hard cap; options can't be
enabled from chat. Changes persist to risk_overrides.json and flow into the
guarded trading agent's RISK.

Run (interactive chat):
    .venv/bin/python cma_lab/copilot.py
Deploy only:
    .venv/bin/python cma_lab/copilot.py deploy
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from chunk6_read_agent import READ_TOOLS
from lab import (
    ROBINHOOD_MCP_URL,
    TICKER,
    client,
    console_url,
    ensure_robinhood_credential,
    get_or_create_environment,
    get_or_create_vault,
    load_state,
    report_cost,
    save_state,
)
from risk_gate import (
    APPETITE_PRESETS,
    HARD_MAX_NOTIONAL,
    HARD_MAX_QUANTITY,
    load_overrides,
    load_risk_config,
    save_overrides,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
# Sonnet for a sharper thought-partner. Drop to claude-haiku-4-5 to cut cost,
# or claude-opus-4-8 for the deepest analysis (pricier).
MODEL = "claude-sonnet-4-6"
AGENT_ID_KEY = "copilot_agent_id"
AGENT_SPEC_KEY = "copilot_agent_spec"
SPEC_VERSION = 1

CUSTOM_TOOLS = [
    {
        "type": "custom",
        "name": "get_engine_analysis",
        "description": f"Return the {TICKER} decision engine's latest analysis "
                       "(final_decision.json): scores, signals, sentiment, "
                       "bullish/bearish factors, risk/reward.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "type": "custom",
        "name": "get_my_trades",
        "description": "Return the local trade journal (trades.json) of trades "
                       "the user has logged. For live broker fills, use the "
                       "Robinhood get_equity_orders tool instead.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "type": "custom",
        "name": "get_risk_settings",
        "description": "Return the user's current effective risk settings and the "
                       "hard caps.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "type": "custom",
        "name": "set_risk_parameter",
        "description": "Adjust ONE risk setting within hard guardrails. Use for "
                       "requests like 'increase my risk appetite' or 'pause "
                       "trading'. parameter ∈ {risk_appetite, max_shares, "
                       "kill_switch}. risk_appetite ∈ {conservative, moderate, "
                       "aggressive}. Values are validated/clamped; out-of-bounds "
                       "or disallowed requests are rejected with a reason.",
        "input_schema": {
            "type": "object",
            "properties": {
                "parameter": {"type": "string"},
                "value": {"type": "string"},
            },
            "required": ["parameter", "value"],
            "additionalProperties": False,
        },
    },
]

TOOLS = [
    # Robinhood read-only allowlist (same as the read agent).
    {
        "type": "mcp_toolset",
        "mcp_server_name": "robinhood",
        "default_config": {"enabled": False, "permission_policy": {"type": "always_allow"}},
        "configs": [{"name": name, "enabled": True} for name in READ_TOOLS],
    },
    # Web research for sentiment / news / signals — only web tools enabled.
    {
        "type": "agent_toolset_20260401",
        "default_config": {"enabled": False},
        "configs": [
            {"name": "web_search", "enabled": True},
            {"name": "web_fetch", "enabled": True},
        ],
    },
    *CUSTOM_TOOLS,
]

MCP_SERVERS = [{"type": "url", "name": "robinhood", "url": ROBINHOOD_MCP_URL}]

SYSTEM = (
    f"You are the user's {TICKER} trading copilot and thought-partner. You help them "
    "reason about their own decision engine's analysis, their trades, market "
    "sentiment, and logical next steps. You are ADVISORY and READ-ONLY: you have "
    "no order tools and must never place, modify, or cancel a trade, nor imply "
    "you did. The human makes every trading decision.\n\n"
    "Tools: use get_engine_analysis for the engine's latest read; get_my_trades "
    "and the Robinhood read tools for positions/orders/quotes/buying power; "
    "web_search/web_fetch for current sentiment, news, and market signals (cite "
    "sources). For risk settings, use get_risk_settings to report and "
    "set_risk_parameter to change them — these are guardrailed; if a change is "
    "rejected or clamped, explain the limit honestly. Be concise, concrete, and "
    "say when you're uncertain. Always leave the final call to the human."
)


# ------------------------------ host-side handlers ---------------------------
def _read_file(path: Path, limit: int = 6000) -> str:
    if not path.exists():
        return f"(not found: {path.name})"
    return path.read_text()[:limit]


def h_get_engine_analysis(_inp: dict) -> str:
    p = REPO_ROOT / "spy_decision_engine" / "reports" / "final_decision.json"
    if not p.exists():
        return "No final_decision.json yet — run the engine first."
    return _read_file(p)


def h_get_my_trades(_inp: dict) -> str:
    p = REPO_ROOT / "spy_decision_engine" / "data" / "trades.json"
    out = _read_file(p)
    return out if p.exists() else (out + "  (Tip: ask me to check Robinhood order history instead.)")


def h_get_risk_settings(_inp: dict) -> str:
    cfg = load_risk_config()
    ov = load_overrides()
    return (
        f"Effective risk settings:\n"
        f"  risk_appetite : {ov.get('risk_appetite', '(default/moderate-ish)')}\n"
        f"  max_shares    : {cfg.max_quantity:g} per order\n"
        f"  notional_cap  : ${cfg.max_notional_per_order:g} per order\n"
        f"  kill_switch   : {cfg.kill_switch}\n"
        f"  locked policy : equity_only={cfg.equity_only}, symbols={list(cfg.symbol_whitelist)}, "
        f"sides={list(cfg.allowed_sides)}\n"
        f"  HARD CAPS     : max {HARD_MAX_QUANTITY} shares, ${HARD_MAX_NOTIONAL:g} notional"
    )


def h_set_risk_parameter(inp: dict) -> str:
    param = str(inp.get("parameter", "")).strip().lower()
    raw = str(inp.get("value", "")).strip()
    ov = load_overrides()

    if param in ("risk_appetite", "appetite", "risk"):
        v = raw.lower()
        if v not in APPETITE_PRESETS:
            return f"Rejected: risk_appetite must be one of {list(APPETITE_PRESETS)}."
        ov["risk_appetite"] = v
        ov.pop("max_quantity", None)            # let the preset govern size again
        ov.pop("max_notional_per_order", None)
        save_overrides(ov)
        cfg = load_risk_config()
        return (f"Done: risk appetite = {v}. Now max {cfg.max_quantity:g} shares / "
                f"${cfg.max_notional_per_order:g} per order. (equity-only, {TICKER}-only, "
                f"long-only stay locked.)")

    if param in ("max_shares", "max_quantity", "size"):
        try:
            n = float(raw)
        except ValueError:
            return "Rejected: max_shares must be a number."
        clamped = max(1.0, min(n, float(HARD_MAX_QUANTITY)))
        ov["max_quantity"] = clamped
        save_overrides(ov)
        note = "" if clamped == n else f" (clamped from {n:g} to hard cap {HARD_MAX_QUANTITY})"
        return f"Done: max shares per order = {clamped:g}{note}."

    if param in ("kill_switch", "killswitch", "halt", "pause"):
        on = raw.lower() in ("true", "on", "1", "yes", "stop", "halt", "pause")
        ov["kill_switch"] = on
        save_overrides(ov)
        return ("Done: KILL SWITCH ON — all orders blocked." if on
                else "Done: kill switch OFF — orders allowed (still gated + your approval).")

    if param in ("equity_only", "options", "option"):
        return ("Rejected: options trading is disabled by policy and cannot be "
                "enabled from chat.")

    return (f"Rejected: unknown parameter '{param}'. Allowed: risk_appetite, "
            f"max_shares, kill_switch.")


HANDLERS = {
    "get_engine_analysis": h_get_engine_analysis,
    "get_my_trades": h_get_my_trades,
    "get_risk_settings": h_get_risk_settings,
    "set_risk_parameter": h_set_risk_parameter,
}


# ------------------------------ deploy + chat --------------------------------
def deploy_copilot() -> str:
    state = load_state()
    agent_id = state.get(AGENT_ID_KEY)
    if agent_id:
        if state.get(AGENT_SPEC_KEY) != SPEC_VERSION:
            current = client().beta.agents.retrieve(agent_id)
            client().beta.agents.update(
                agent_id, version=current.version, model=MODEL,
                system=SYSTEM, tools=TOOLS, mcp_servers=MCP_SERVERS,
            )
            state[AGENT_SPEC_KEY] = SPEC_VERSION
            save_state(state)
            print(f"[deploy] updated copilot {agent_id} -> spec v{SPEC_VERSION}")
        else:
            print(f"[deploy] copilot already hosted: {agent_id}")
        return agent_id

    agent = client().beta.agents.create(
        name=f"{TICKER} Trading Copilot", model=MODEL, system=SYSTEM,
        mcp_servers=MCP_SERVERS, tools=TOOLS,
    )
    state[AGENT_ID_KEY] = agent.id
    state[AGENT_SPEC_KEY] = SPEC_VERSION
    save_state(state)
    print(f"[deploy] hosted new copilot on CMA: {agent.id} (v{agent.version})")
    return agent.id


def run_turn(session_id: str, user_text: str) -> bool:
    """Send a user message and stream one assistant turn, executing custom tools
    host-side. Stream-first: we open the stream, THEN send. Returns False if the
    session terminated."""
    c = client()
    pending: list = []
    with c.beta.sessions.events.stream(session_id=session_id) as stream:
        c.beta.sessions.events.send(
            session_id=session_id,
            events=[{"type": "user.message", "content": [{"type": "text", "text": user_text}]}],
        )
        for event in stream:
            t = event.type
            if t == "agent.message":
                for b in event.content:
                    if b.type == "text":
                        print(b.text, end="", flush=True)
            elif t == "agent.custom_tool_use":
                pending.append(event)
            elif t == "agent.mcp_tool_use":
                print(f"\n  · reading {getattr(event, 'name', '?')}…", flush=True)
            elif t == "agent.tool_use":
                print(f"\n  · {getattr(event, 'name', '?')}…", flush=True)
            elif t == "session.error":
                print(f"\n[session error] {getattr(event, 'error', event)}")
            elif t == "session.status_terminated":
                return False
            elif t == "session.status_idle":
                stop = getattr(getattr(event, "stop_reason", None), "type", None)
                if stop == "requires_action":
                    results = []
                    for ev in pending:
                        fn = HANDLERS.get(ev.name)
                        out = fn(getattr(ev, "input", {}) or {}) if fn else f"Unknown tool {ev.name}"
                        results.append({
                            "type": "user.custom_tool_result",
                            "custom_tool_use_id": ev.id,
                            "content": [{"type": "text", "text": str(out)}],
                        })
                    pending = []
                    if results:
                        c.beta.sessions.events.send(session_id=session_id, events=results)
                    continue
                print()  # newline at end of the turn
                return True
    return True


def main() -> None:
    agent_id = deploy_copilot()
    if len(sys.argv) > 1 and sys.argv[1] == "deploy":
        print("[copilot] deploy-only: hosted; skipping chat.")
        return

    env_id = get_or_create_environment()
    vault_id = get_or_create_vault()
    ensure_robinhood_credential(vault_id)
    session = client().beta.sessions.create(
        agent=agent_id, environment_id=env_id, vault_ids=[vault_id], title="copilot chat",
    )

    print(f"\n{TICKER} Copilot ready. Session {session.id}")
    print(f"Watch live: {console_url(session.id)}")
    print("Ask about engine analysis, your trades, sentiment, next steps, or say "
          "things like 'make me more aggressive' / 'pause trading'.")
    print("Type 'exit' to quit.\n")

    while True:
        try:
            user = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not user:
            continue
        if user.lower() in ("exit", "quit", "q"):
            break
        print("\ncopilot> ", end="", flush=True)
        if not run_turn(session.id, user):
            print("[session ended]")
            break
        print()

    report_cost(session.id, model=MODEL)


if __name__ == "__main__":
    main()
