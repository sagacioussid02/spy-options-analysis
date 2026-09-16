"""
Chunk 3, step 2 of 2 — READ-ONLY Robinhood MCP via CMA.

This is the real integration, minus any trading:
    - a VAULT holds the Robinhood OAuth credential (from step 1)
    - the AGENT declares the Robinhood MCP server + an mcp_toolset
    - the toolset is set to always_ask, so EVERY Robinhood tool call pauses for
      your approval (reusing the chunk-2 loop). You approve reads; you'd deny
      anything that looks like a write. Plus the system prompt forbids trading,
      plus Robinhood's agentic account is fund-isolated. Three layers, read-only.

Run it (after step 1 has populated cma_lab/.env):
    .venv/bin/python cma_lab/chunk3_robinhood_read.py

Watch the <event> stream: you'll see agent.mcp_tool_use events naming the actual
Robinhood tools (that's how you discover the catalog), each gated for approval.
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

MODEL = "claude-haiku-4-5"
AGENT_STATE_KEY = "rh_read_agent_id"
AGENT_MODEL_KEY = "rh_read_agent_model"

SYSTEM = (
    "You inspect a Robinhood agentic trading account through MCP tools. "
    "You are STRICTLY READ-ONLY: only call tools that READ data — account "
    "details, balances, positions, order history, and market data. You must "
    "NEVER place, modify, or cancel an order under any circumstances. If asked "
    "to trade, refuse and explain that this is a read-only session."
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
        name="Robinhood Read Agent",
        model=MODEL,
        system=SYSTEM,
        # Declare the MCP server by URL only — NO credentials here. Auth lives in
        # the vault and is matched to this server by URL at session time.
        mcp_servers=[{"type": "url", "name": "robinhood", "url": ROBINHOOD_MCP_URL}],
        # Gate the whole Robinhood toolset behind approval while we explore.
        tools=[{
            "type": "mcp_toolset",
            "mcp_server_name": "robinhood",
            "default_config": {"permission_policy": {"type": "always_ask"}},
        }],
    )
    state[AGENT_STATE_KEY] = agent.id
    state[AGENT_MODEL_KEY] = MODEL
    save_state(state)
    print(f"[chunk3] created agent {agent.id} (v{agent.version})")
    return agent.id


def approve(name: str, tool_input: dict):
    """Approve read calls; deny anything that smells like a write."""
    print(f"\n  >>> Robinhood MCP tool: {name}")
    print(f"      input: {tool_input}")
    answer = input("      approve this call? [y/N]: ").strip().lower()
    if answer.startswith("y"):
        return True, None
    return False, "Operator denied. This is a read-only session; do not trade."


def main() -> None:
    env_id = get_or_create_environment()
    vault_id = get_or_create_vault()
    ensure_robinhood_credential(vault_id)  # stores tokens from .env, once
    agent_id = get_or_create_agent()

    session = client().beta.sessions.create(
        agent=agent_id,
        environment_id=env_id,
        vault_ids=[vault_id],  # <-- attaches the Robinhood credential to this run
        title="chunk3 robinhood read",
    )
    print(f"[chunk3] session {session.id}")
    print(f"[chunk3] watch live: {console_url(session.id)}\n")

    drive_session_with_approval(
        session.id,
        kickoff_text=(
            "Using the Robinhood MCP tools, show me my agentic account: cash "
            "balance, buying power, and any open positions. READ-ONLY — do not "
            "place, modify, or cancel any orders."
        ),
        approve_fn=approve,
    )

    print("\n[chunk3] done. The tool names you approved above ARE the Robinhood "
          "MCP catalog — we'll pick the order-placement tool to gate in chunk 4.")


if __name__ == "__main__":
    main()
