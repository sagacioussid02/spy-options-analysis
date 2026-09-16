"""
Chunk 4 — guardrailed trading agent (two layers + a lab safety switch).

This puts the chunk-3 MCP agent and the chunk-4 risk gate together into the
shape you'd actually run:

    agent wants to call an order tool
        -> LAYER 1: deterministic risk gate (risk_gate.evaluate)
              violates a hard limit?  -> AUTO-DENY, you are never asked
        -> LAB SAFETY: real place_* order?  -> AUTO-DENY (lab can't place)
        -> LAYER 2: human approval (your y/N) for anything order-like that passed
        -> reads (get_*) just run

So a runaway/confused agent literally cannot get a limit-busting or live order in
front of you, and even a fat-fingered 'y' can't place a real order while
LAB_BLOCK_PLACEMENT is True.

Run it (safe — places nothing):
    .venv/bin/python cma_lab/chunk4_trade.py

The kickoff deliberately makes the agent attempt a bad order (blocked by the
gate) and a compliant dry-run review (passes gate -> you approve -> simulated).
"""
from __future__ import annotations

from lab import (
    ROBINHOOD_MCP_URL,
    client,
    console_url,
    drive_session_with_approval,
    ensure_robinhood_credential,
    get_or_create_environment,
    get_or_create_vault,
    load_state,
    save_state,
)
from risk_gate import PLACE_TOOLS, CANCEL_TOOLS, SIMULATE_TOOLS, evaluate, load_risk_config

MODEL = "claude-haiku-4-5"
AGENT_STATE_KEY = "rh_trade_agent_id"
AGENT_MODEL_KEY = "rh_trade_agent_model"

# ---- LAB SAFETY: hard switch. While True, NO real order can be placed, full ----
# stop, regardless of risk gate or your approval. Flip to False only when you
# genuinely intend to let live orders through (and even then the gate + your
# approval still apply).
LAB_BLOCK_PLACEMENT = True

# Your hard limits (the deterministic layer). Loaded from risk_overrides.json so
# copilot tweaks ("increase my risk appetite") take effect here — clamped to the
# hard ceilings, with equity-only/SPY/long-only policy-locked.
RISK = load_risk_config()

ORDER_LIKE = PLACE_TOOLS | CANCEL_TOOLS | SIMULATE_TOOLS

SYSTEM = (
    "You manage a SPY-only, long-only STOCK (equity) strategy through the "
    "Robinhood MCP. You trade SPY SHARES, not options — do not use any option "
    "tools. Hard rules: trade only SPY; buy shares only, never sell/short; keep "
    "size small. Prefer review_equity_order (simulation) over place_equity_order "
    "in this environment. When a tool call is denied, do not retry it — report "
    "the denial reason and move on."
)


def get_or_create_agent() -> str:
    state = load_state()
    agent_id = state.get(AGENT_STATE_KEY)
    if agent_id:
        if state.get(AGENT_MODEL_KEY) != MODEL:
            current = client().beta.agents.retrieve(agent_id)
            client().beta.agents.update(agent_id, version=current.version, model=MODEL)
            state[AGENT_MODEL_KEY] = MODEL
            save_state(state)
        return agent_id

    agent = client().beta.agents.create(
        name="Robinhood Trading Agent (lab)",
        model=MODEL,
        system=SYSTEM,
        mcp_servers=[{"type": "url", "name": "robinhood", "url": ROBINHOOD_MCP_URL}],
        # Whole toolset gated for approval; our approve_fn adds the risk gate on
        # top and auto-handles the read/order distinction.
        tools=[{
            "type": "mcp_toolset",
            "mcp_server_name": "robinhood",
            "default_config": {"permission_policy": {"type": "always_ask"}},
        }],
    )
    state[AGENT_STATE_KEY] = agent.id
    state[AGENT_MODEL_KEY] = MODEL
    save_state(state)
    print(f"[chunk4] created agent {agent.id} (v{agent.version})")
    return agent.id


def guarded_approve(name: str, tool_input: dict):
    """
    The two-layer gate, as a single approve_fn for drive_session_with_approval.
    Returns (allow: bool, deny_message: str | None).
    """
    # LAYER 1 — deterministic risk gate.
    decision = evaluate(name, tool_input, RISK)
    print(f"\n  [gate] {name} {tool_input}")
    print(f"  [gate] {decision}")
    if not decision.allowed:
        return False, f"Risk gate denied: {'; '.join(decision.reasons)}"

    # LAB SAFETY — never place a real order in the lab.
    if name in PLACE_TOOLS and LAB_BLOCK_PLACEMENT:
        print("  [lab] LAB_BLOCK_PLACEMENT is True -> auto-deny live placement")
        return False, ("Lab safe mode: live order placement is disabled. Use "
                       "review_equity_order to simulate instead.")

    # Pure reads (get_*) that passed the gate: just run them, no prompt.
    if name not in ORDER_LIKE:
        return True, None

    # LAYER 2 — human approval for order-like calls that cleared the gate.
    answer = input(f"  [you] approve {name}? [y/N]: ").strip().lower()
    if answer.startswith("y"):
        return True, None
    return False, "Operator denied at approval step."


def main() -> None:
    env_id = get_or_create_environment()
    vault_id = get_or_create_vault()
    ensure_robinhood_credential(vault_id)
    agent_id = get_or_create_agent()

    session = client().beta.sessions.create(
        agent=agent_id,
        environment_id=env_id,
        vault_ids=[vault_id],
        title="chunk4 guarded trade",
    )
    print(f"[chunk4] session {session.id}")
    print(f"[chunk4] LAB_BLOCK_PLACEMENT={LAB_BLOCK_PLACEMENT}  RISK={RISK}")
    print(f"[chunk4] watch live: {console_url(session.id)}\n")

    drive_session_with_approval(
        session.id,
        kickoff_text=(
            "Do these two things in order and report what happened for each:\n"
            "1) Attempt to place an order to BUY 50 shares of TSLA. (I expect "
            "this to be blocked — that's fine, just report the reason.)\n"
            "2) Then SIMULATE buying 1 share of SPY using review_equity_order "
            "(look up the account first if needed). Report the simulated result."
        ),
        approve_fn=guarded_approve,
    )

    print("\n[chunk4] done. The TSLA order should have been auto-denied by the "
          "risk gate (never reaching your prompt); the SPY review should have "
          "passed the gate, asked your approval, and simulated with no money moved.")


if __name__ == "__main__":
    main()
