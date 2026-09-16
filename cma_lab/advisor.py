"""
Advisor desk (step 2) — propose -> discuss/tweak -> approve -> execute -> journal.

The flow you asked for:
  - The advisor (an LLM agent) reads the engine, your account, market context, AND
    your journal's track record, then PROPOSES a sized trade with a thesis +
    conviction (via the propose_trade tool -> writes a 'proposed' journal entry).
  - You talk to it: ask "why this size?", "what's the risk?" — normal chat.
  - You tweak: tell it in chat ("make it 1 share"), or use /tweak for precision.
  - You APPROVE with a command (/approve) — the deterministic button.
  - On approval, HOST-SIDE CODE (not the LLM) runs the risk gate and executes the
    EXACT approved order, then journals the fill. The model never holds the trigger.

Execution is SIMULATED while LIVE_EXECUTION = False (fills modeled from the live
quote / your limit). Flip it to True to place real equity orders — the risk gate
and your approval still apply.

Run:
    .venv/bin/python cma_lab/advisor.py
    .venv/bin/python cma_lab/advisor.py deploy
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import lessons as lessons_store
from chunk6_read_agent import READ_TOOLS
from execution import ACCOUNT, J, LIVE_EXECUTION, LIVE_MAX_SHARES, execute_approved, h_propose
from lab import (
    ROBINHOOD_MCP_URL,
    account_standing,
    client,
    console_url,
    ensure_robinhood_credential,
    get_or_create_environment,
    get_or_create_vault,
    load_state,
    report_cost,
    save_state,
)
from risk_gate import load_risk_config

REPO_ROOT = Path(__file__).resolve().parent.parent
MODEL = "claude-sonnet-4-6"
AGENT_ID_KEY = "advisor_agent_id"
AGENT_SPEC_KEY = "advisor_agent_spec"
SPEC_VERSION = 4  # +falsifiable proposals (kill_criteria, exit_plan required)

STRATEGIES = "trend_follow, pullback_buy, breakout, stand_aside"

CUSTOM_TOOLS = [
    {"type": "custom", "name": "get_engine_analysis",
     "description": "The SPY engine's latest analysis (final_decision.json).",
     "input_schema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"type": "custom", "name": "get_journal_summary",
     "description": "Your track record: win-rate and P&L by strategy, regime, and "
                    "conviction bucket, with sample counts. Use to favor setups "
                    "with demonstrated edge and avoid ones that lose.",
     "input_schema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"type": "custom", "name": "get_recent_trades",
     "description": "The most recent journal entries (theses, outcomes, reflections).",
     "input_schema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"type": "custom", "name": "get_lessons",
     "description": "Distilled lessons from past trades (written by the reflection "
                    "reviewer). Consult before proposing — let it inform conviction "
                    "and strategy choice.",
     "input_schema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"type": "custom", "name": "get_risk_settings",
     "description": "Current effective risk settings + hard caps. Size proposals "
                    "within these.",
     "input_schema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"type": "custom", "name": "get_account_standing",
     "description": "The user's LIVE buying power, cash, and account value. This is "
                    "what they can actually afford — ALWAYS check before proposing "
                    "and never propose more than the buying power allows.",
     "input_schema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"type": "custom", "name": "propose_trade",
     "description": "Record a concrete trade PROPOSAL for the human to review and "
                    "approve. You do NOT execute — proposing logs it; the human "
                    "approves and the system executes. Size within risk settings. "
                    "Every proposal must be falsifiable: state what would prove you "
                    "wrong (kill_criteria) and a full exit_plan up front.",
     "input_schema": {
         "type": "object",
         "properties": {
             "thesis": {"type": "string", "description": "Why, in 1-3 sentences."},
             "conviction": {"type": "number", "description": "0..1"},
             "regime": {"type": "string", "description": "e.g. bullish_trend, chop, high_vol"},
             "strategy": {"type": "string", "description": f"one of: {STRATEGIES}"},
             "side": {"type": "string", "description": "buy"},
             "symbol": {"type": "string", "description": "SPY"},
             "quantity": {"type": "number", "description": "shares"},
             "entry_style": {"type": "string", "description": "limit or market"},
             "limit_price": {"type": "number", "description": "if limit"},
             "kill_criteria": {"type": "string", "description": "Pre-registered: what "
                    "specific price action, level, or event would prove this thesis "
                    "wrong? Be concrete, not vague."},
             "exit_plan": {
                 "type": "object",
                 "description": "Even a good thesis needs a planned exit.",
                 "properties": {
                     "target": {"type": "number", "description": "take-profit price"},
                     "stop": {"type": "number", "description": "stop-loss price"},
                     "time_stop": {"type": "string", "description": "ISO date to exit "
                            "by regardless, e.g. 2026-07-10"},
                 },
                 "required": ["target", "stop", "time_stop"],
                 "additionalProperties": False,
             },
         },
         "required": ["thesis", "conviction", "side", "symbol", "quantity", "entry_style",
                      "kill_criteria", "exit_plan"],
         "additionalProperties": False,
     }},
]

TOOLS = [
    {"type": "mcp_toolset", "mcp_server_name": "robinhood",
     "default_config": {"enabled": False, "permission_policy": {"type": "always_allow"}},
     "configs": [{"name": n, "enabled": True} for n in READ_TOOLS]},
    {"type": "agent_toolset_20260401", "default_config": {"enabled": False},
     "configs": [{"name": "web_search", "enabled": True}, {"name": "web_fetch", "enabled": True}]},
    *CUSTOM_TOOLS,
]
MCP_SERVERS = [{"type": "url", "name": "robinhood", "url": ROBINHOOD_MCP_URL}]

SYSTEM = (
    "You are the user's SPY trading advisor — a sharp, honest desk strategist, not "
    "a rules engine. You reason about the engine's signals, live account + market, "
    "current sentiment (web_search), the user's own track record "
    "(get_journal_summary), AND the distilled lessons from past trades "
    "(get_lessons) to form a THESIS with a calibrated CONVICTION (0..1).\n"
    "ALWAYS check get_account_standing AND get_risk_settings before proposing. Size "
    "every proposal to fit the user's actual BUYING POWER — never propose an order "
    "that costs more than they can afford. If buying power is too small for a "
    "meaningful position (e.g. less than one share), propose a small FRACTIONAL "
    "market order sized to the cash, or recommend funding the account / standing "
    "aside — be honest about it. When you recommend a trade, call propose_trade with "
    "a clear thesis, conviction, the regime, a named strategy (one of: " + STRATEGIES +
    "), an affordable size, kill_criteria (what would prove you wrong — be concrete), "
    "and a full exit_plan (target, stop, time_stop). propose_trade will reject "
    "proposals missing any of these — fix and retry. Favor setups your journal shows "
    "edge in; be cautious where it shows losses; prefer stand_aside in low-conviction "
    "chop.\n"
    "You do NOT execute trades and have no order tools. After you propose, the human "
    "reviews, may tweak, and approves with a command; the system then executes the "
    "exact approved order. Discuss and refine when asked. Be concise, quantify your "
    "conviction, and say when you're unsure. The human makes the call."
)


# ------------------------------ custom-tool handlers -------------------------
def _read(path: Path, limit: int = 6000) -> str:
    return path.read_text()[:limit] if path.exists() else f"(not found: {path.name})"


def h_engine(_i): return _read(REPO_ROOT / "spy_decision_engine" / "reports" / "final_decision.json")
def h_summary(_i): return json.dumps(J.summarize(), indent=2)
def h_recent(_i): return json.dumps(J.recent(8), indent=2)
def h_lessons(_i): return lessons_store.read_lessons()


def h_standing(_i) -> str:
    try:
        s = account_standing(ACCOUNT)
    except Exception as ex:  # noqa: BLE001
        return f"Could not fetch standing: {ex}"
    return (f"buying_power=${s['buying_power']:.2f}, cash=${s['cash']:.2f}, "
            f"account_value=${s['total_value']:.2f}, equity=${s['equity_value']:.2f} "
            f"{s['currency']}. Do not propose orders whose cost exceeds buying_power.")


def h_risk(_i):
    c = load_risk_config()
    return (f"max_shares={c.max_quantity:g}, notional_cap=${c.max_notional_per_order:g}, "
            f"kill_switch={c.kill_switch}, equity_only={c.equity_only} (locked), "
            f"symbols={list(c.symbol_whitelist)}, sides={list(c.allowed_sides)}")


HANDLERS = {
    "get_engine_analysis": h_engine,
    "get_journal_summary": h_summary,
    "get_recent_trades": h_recent,
    "get_lessons": h_lessons,
    "get_risk_settings": h_risk,
    "get_account_standing": h_standing,
    "propose_trade": h_propose,
}


# ------------------------------ commands (deterministic) ---------------------
def _pick(entry_id: str | None):
    if entry_id:
        return J.get(entry_id)
    pend = J.pending_proposals()
    return pend[-1] if pend else None


def handle_command(line: str) -> None:
    parts = line.split()
    cmd = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else None

    if cmd == "/pending":
        pend = J.pending_proposals()
        if not pend:
            print("  (no pending proposals)")
        for e in pend:
            lim = f" @ ${e['limit_price']:g}" if e.get("limit_price") else ""
            print(f"  {e['id']}: {e['side']} {e['quantity']:g} {e['symbol']} "
                  f"{e['entry_style']}{lim} | conv {e['conviction']:.2f} | {e['strategy']}")

    elif cmd == "/approve":
        e = _pick(arg)
        if not e or e["status"] not in ("proposed", "approved"):
            print("  no matching pending/approved proposal."); return
        J.approve(e["id"], note="approved via desk")
        e = J.get(e["id"])
        print(f"  approving {e['id']} …")
        print("  " + execute_approved(e))

    elif cmd == "/reject":
        e = _pick(arg)
        if not e:
            print("  no matching proposal."); return
        note = " ".join(parts[2:]) if len(parts) > 2 else ""
        J.reject(e["id"], note=note)
        print(f"  rejected {e['id']}.")

    elif cmd == "/tweak":
        e = _pick(arg)
        if not e:
            print("  no matching proposal."); return
        changes = {}
        for tok in parts[2:]:
            if tok.startswith("qty="):
                changes["quantity"] = float(tok[4:])
            elif tok.startswith("limit="):
                changes["limit_price"] = float(tok[6:])
        if changes:
            J._update(e["id"], **changes)
            print(f"  tweaked {e['id']}: {changes}. ( /approve {e['id']} when ready )")
        else:
            print("  usage: /tweak <id> qty=1 limit=687")

    elif cmd == "/resolve":
        outcome_tok = parts[2].lower() if len(parts) > 2 else None
        if not arg or outcome_tok not in ("true", "false"):
            print("  usage: /resolve <pred_id> true|false"); return
        from predictions import PredictionStore
        p = PredictionStore().resolve(arg, outcome=(outcome_tok == "true"),
                                      note="human override via advisor CLI")
        if p:
            print(f"  resolved {arg}: outcome={p['outcome']} brier={p['brier']}")
        else:
            print(f"  no prediction {arg}")

    elif cmd in ("/help", "help"):
        print_help()
    else:
        print(f"  unknown command {cmd}. /help for options.")


def print_help() -> None:
    print("  commands: /pending | /approve [id] | /tweak <id> qty=.. limit=.. | "
          "/reject [id] [note] | /resolve <pred_id> true|false | /help | exit")
    print("  anything else is a message to your advisor.")


# ------------------------------ chat turn + loop -----------------------------
def run_turn(session_id: str, user_text: str) -> bool:
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
            elif t in ("agent.mcp_tool_use", "agent.tool_use"):
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
                        out = fn(getattr(ev, "input", {}) or {}) if fn else f"unknown {ev.name}"
                        results.append({"type": "user.custom_tool_result",
                                        "custom_tool_use_id": ev.id,
                                        "content": [{"type": "text", "text": str(out)}]})
                    pending = []
                    if results:
                        c.beta.sessions.events.send(session_id=session_id, events=results)
                    continue
                print()
                return True
    return True


def deploy_advisor() -> str:
    state = load_state()
    agent_id = state.get(AGENT_ID_KEY)
    if agent_id:
        if state.get(AGENT_SPEC_KEY) != SPEC_VERSION:
            cur = client().beta.agents.retrieve(agent_id)
            client().beta.agents.update(agent_id, version=cur.version, model=MODEL,
                                        system=SYSTEM, tools=TOOLS, mcp_servers=MCP_SERVERS)
            state[AGENT_SPEC_KEY] = SPEC_VERSION; save_state(state)
            print(f"[deploy] updated advisor {agent_id} -> spec v{SPEC_VERSION}")
        else:
            print(f"[deploy] advisor already hosted: {agent_id}")
        return agent_id
    agent = client().beta.agents.create(name="SPY Trading Advisor", model=MODEL,
                                        system=SYSTEM, mcp_servers=MCP_SERVERS, tools=TOOLS)
    state[AGENT_ID_KEY] = agent.id; state[AGENT_SPEC_KEY] = SPEC_VERSION; save_state(state)
    print(f"[deploy] hosted new advisor on CMA: {agent.id} (v{agent.version})")
    return agent.id


def main() -> None:
    agent_id = deploy_advisor()
    if len(sys.argv) > 1 and sys.argv[1] == "deploy":
        print("[advisor] deploy-only."); return

    env_id = get_or_create_environment()
    vault_id = get_or_create_vault()
    ensure_robinhood_credential(vault_id)
    session = client().beta.sessions.create(agent=agent_id, environment_id=env_id,
                                            vault_ids=[vault_id], title="advisor desk")
    if LIVE_EXECUTION:
        acct = f"••••{ACCOUNT[-4:]}" if ACCOUNT else "(no account!)"
        mode = f"LIVE — REAL ORDERS, max {LIVE_MAX_SHARES} sh, acct {acct}, typed-confirm each"
    else:
        mode = "SIMULATED (no real orders; set SPY_LIVE=1 to arm live)"
    print(f"\nSPY Advisor Desk. execution = {mode}.\n  Session {session.id}")
    print(f"Watch live: {console_url(session.id)}")
    print_help(); print()

    while True:
        try:
            user = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print(); break
        if not user:
            continue
        if user.lower() in ("exit", "quit", "q"):
            break
        if user.startswith("/") or user.lower() == "help":
            handle_command(user); continue
        print("\nadvisor> ", end="", flush=True)
        if not run_turn(session.id, user):
            print("[session ended]"); break
        print()

    report_cost(session.id, model=MODEL)


if __name__ == "__main__":
    main()
