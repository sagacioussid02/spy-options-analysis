"""
Chunk 6 — a hosted, READ-ONLY decision-support agent on CMA.

Goal: deploy a persistent CMA agent that uses Robinhood's READ tools to make your
decisions account-aware — live SPY quote, buying power, current positions, recent
orders — and produces a short briefing for YOU. It cannot trade: its Robinhood
toolset is allowlisted to read tools only (place/cancel are not even enabled).

Two phases:
  - deploy_agent(): create the agent ONCE on CMA, store its ID. This is the
    "hosting" step — the agent config now lives on CMA, versioned, reusable.
  - a read session: open a session against that agent and ask for a briefing.

Run (deploy + one read briefing):
    .venv/bin/python cma_lab/chunk6_read_agent.py

Deploy only (just host/refresh the agent, no session):
    .venv/bin/python cma_lab/chunk6_read_agent.py deploy
"""
from __future__ import annotations

import sys

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
AGENT_ID_KEY = "read_agent_id"
AGENT_SPEC_KEY = "read_agent_spec"
# Bump this whenever SYSTEM/TOOLS below change, to push a new agent version.
SPEC_VERSION = 1

# The ONLY Robinhood tools this agent may use. No place_*/cancel_* — so even if
# the model tried, the tool isn't enabled and the call cannot happen.
READ_TOOLS = [
    "get_accounts",
    "get_portfolio",
    "get_equity_positions",
    "get_equity_orders",
    "get_equity_quotes",
    "get_equity_tradability",
    "search",
]

# Allowlist pattern: default disabled, enable only the read tools, auto-run them
# (always_allow) so the agent can gather context without pestering you.
TOOLS = [{
    "type": "mcp_toolset",
    "mcp_server_name": "robinhood",
    "default_config": {"enabled": False, "permission_policy": {"type": "always_allow"}},
    "configs": [{"name": name, "enabled": True} for name in READ_TOOLS],
}]

MCP_SERVERS = [{"type": "url", "name": "robinhood", "url": ROBINHOOD_MCP_URL}]

SYSTEM = (
    "You are a READ-ONLY decision-support analyst for a SPY trading workflow. "
    "You have Robinhood read tools (accounts, portfolio, positions, orders, "
    "quotes, tradability, search). Your job is to gather live account + market "
    "context and present a SHORT, plain-language briefing to a human who will "
    "make the trading decision themselves.\n"
    "You CANNOT and MUST NOT place, modify, or cancel any order — you have no "
    "order tools. Never imply you executed a trade. End every briefing with a "
    "neutral 'Your call.' — you advise, the human decides."
)


def deploy_agent() -> str:
    """Create the agent on CMA once; update it in place if the spec changed."""
    state = load_state()
    agent_id = state.get(AGENT_ID_KEY)

    if agent_id:
        if state.get(AGENT_SPEC_KEY) != SPEC_VERSION:
            current = client().beta.agents.retrieve(agent_id)
            updated = client().beta.agents.update(
                agent_id,
                version=current.version,
                model=MODEL,
                system=SYSTEM,
                tools=TOOLS,
                mcp_servers=MCP_SERVERS,
            )
            state[AGENT_SPEC_KEY] = SPEC_VERSION
            save_state(state)
            print(f"[deploy] updated read agent {agent_id} -> spec v{SPEC_VERSION} "
                  f"(agent v{updated.version})")
        else:
            print(f"[deploy] read agent already hosted: {agent_id}")
        return agent_id

    agent = client().beta.agents.create(
        name="SPY Read/Decision-Support Agent",
        model=MODEL,
        system=SYSTEM,
        mcp_servers=MCP_SERVERS,
        tools=TOOLS,
    )
    state[AGENT_ID_KEY] = agent.id
    state[AGENT_SPEC_KEY] = SPEC_VERSION
    save_state(state)
    print(f"[deploy] hosted new read agent on CMA: {agent.id} (v{agent.version})")
    return agent.id


def _deny(name: str, tool_input: dict):
    """Safety net: reads auto-run, so this should never fire. If anything asks
    for approval, refuse — this agent does not take actions."""
    return False, "Read-only agent: no actions permitted."


def run_briefing(agent_id: str) -> None:
    env_id = get_or_create_environment()
    vault_id = get_or_create_vault()
    ensure_robinhood_credential(vault_id)

    session = client().beta.sessions.create(
        agent=agent_id,
        environment_id=env_id,
        vault_ids=[vault_id],
        title="chunk6 read briefing",
    )
    print(f"[chunk6] session {session.id}")
    print(f"[chunk6] watch live: {console_url(session.id)}\n")

    drive_session_with_approval(
        session.id,
        kickoff_text=(
            "Give me a read-only account + market briefing for SPY:\n"
            "1) List my accounts and identify the agentic one.\n"
            "2) Show buying power and any current SPY position (qty, avg cost).\n"
            "3) Show the current SPY quote and whether SPY is tradable right now.\n"
            "4) Note how many equity orders I've placed recently.\n"
            "Summarize in a short briefing for a human decision-maker. Do not trade."
        ),
        approve_fn=_deny,
    )


def main() -> None:
    agent_id = deploy_agent()  # the "host on CMA" step
    if len(sys.argv) > 1 and sys.argv[1] == "deploy":
        print("[chunk6] deploy-only: agent is hosted; skipping session.")
        return
    run_briefing(agent_id)
    print("\n[chunk6] done. A read-only agent is now hosted on CMA and gave you an "
          "account-aware briefing. Next we can schedule it or feed its briefing "
          "alongside the engine's signal.")


if __name__ == "__main__":
    main()
