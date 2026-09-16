"""
Sector Radar Scout — researches catalyst chains across sectors and surfaces a
horizon-classified shortlist onto your Robinhood "Radar" watchlist.

Focus (your framing): CATALYST CHAINS with induced effects —
  - government policy / regulation -> affected sectors
  - geopolitics / war -> affected sectors (energy, defense, shipping…)
  - large investments / capex announcements
  - notable insider / institutional activity
…traced to specific tickers, each with a thesis and a horizon (short swing vs
3–12 month position).

This is a RADAR (idea generation), NOT buy signals. The scout researches + writes
candidates; you review; the advisor can later form a sized thesis on any name.
Trading non-SPY names stays a separate, deliberate step (whitelist + funding).

Run:
    .venv/bin/python cma_lab/scout.py
    .venv/bin/python cma_lab/scout.py deploy
"""
from __future__ import annotations

import json
import sys
from datetime import date

from lab import (
    client,
    console_url,
    ensure_robinhood_credential,
    get_or_create_environment,
    get_or_create_vault,
    load_state,
    mcp_call_tool,
    report_cost,
    save_state,
)
from futurist import theses_index_text
from radar import Radar

MODEL = "claude-sonnet-4-6"
AGENT_ID_KEY = "scout_agent_id"
AGENT_SPEC_KEY = "scout_agent_spec"
SPEC_VERSION = 1
WATCHLIST_NAME = "Radar"

R = Radar()

# Read tools the scout may use (resolve tickers, confirm tradable, quotes).
SCOUT_READ_TOOLS = ["search", "get_equity_quotes", "get_equity_tradability"]

CUSTOM_TOOLS = [
    {"type": "custom", "name": "add_candidate",
     "description": "Record one researched candidate onto the radar. Call once per "
                    "stock you want to surface.",
     "input_schema": {
         "type": "object",
         "properties": {
             "symbol": {"type": "string"},
             "sector": {"type": "string"},
             "catalyst_type": {"type": "string",
                               "description": "policy | geopolitics | investment | insider | other"},
             "catalyst": {"type": "string", "description": "the news/event driving it"},
             "thesis": {"type": "string"},
             "horizon": {"type": "string", "description": "short (days-weeks) or long (3-12 months)"},
             "conviction": {"type": "number", "description": "0..1"},
         },
         "required": ["symbol", "sector", "catalyst", "thesis", "horizon"],
         "additionalProperties": False,
     }},
]

TOOLS = [
    {"type": "mcp_toolset", "mcp_server_name": "robinhood",
     "default_config": {"enabled": False, "permission_policy": {"type": "always_allow"}},
     "configs": [{"name": n, "enabled": True} for n in SCOUT_READ_TOOLS]},
    {"type": "agent_toolset_20260401", "default_config": {"enabled": False},
     "configs": [{"name": "web_search", "enabled": True}, {"name": "web_fetch", "enabled": True}]},
    *CUSTOM_TOOLS,
]
MCP_SERVERS = [{"type": "url", "name": "robinhood", "url": "https://agent.robinhood.com/mcp/trading"}]

SYSTEM = (
    "You are a sector radar scout. You sweep the major market sectors and surface a "
    "shortlist of stocks worth watching — driven by CATALYST CHAINS, i.e. events "
    "with an induced ripple effect:\n"
    "  • government policy / regulation / subsidies -> which sectors benefit or suffer\n"
    "  • geopolitics / war / sanctions -> energy, defense, shipping, commodities, etc.\n"
    "  • large investments / capex / M&A announcements\n"
    "  • notable insider buying/selling or big institutional moves\n"
    "For each strong, CURRENT catalyst, identify the affected sector and 1–3 specific "
    "tickers. Use web_search/web_fetch for current news (cite sources). Use the "
    "Robinhood `search` tool to resolve tickers and `get_equity_tradability` to "
    "confirm they're tradable. For each pick, call add_candidate with: symbol, sector, "
    "catalyst_type, the catalyst, a 1–2 sentence thesis, a horizon (short = a swing "
    "over days/weeks on the catalyst; long = a 3–12 month structural position), and a "
    "calibrated conviction (0..1).\n"
    "Aim for ~8–15 high-quality candidates across DIFFERENT sectors — quality over "
    "quantity. This is a RADAR of ideas to investigate, NOT buy recommendations: be "
    "explicit about uncertainty and that the human must validate. Do not propose or "
    "place any orders."
)


# ------------------------------ handlers + sync ------------------------------
def h_add_candidate(inp: dict) -> str:
    c = R.add(**inp)
    print(f"  + radar: {c.symbol:<6} [{c.horizon}] {c.sector} — {c.catalyst_type} "
          f"(conv {c.conviction:.2f})")
    return f"Added {c.symbol} to radar ({c.horizon}, conviction {c.conviction:.2f})."


HANDLERS = {"add_candidate": h_add_candidate}


def sync_watchlist(symbols: list[str]) -> str:
    """Deterministically add the radar symbols to a Robinhood 'Radar' watchlist
    (create it if missing). LLM does NOT do this write — host-side code does."""
    if not symbols:
        return "no symbols to sync"
    try:
        lists = json.loads(mcp_call_tool("get_watchlists", {}))["data"]["watchlists"]
        rid = next((w["id"] for w in lists if w["display_name"] == WATCHLIST_NAME), None)
        if not rid:
            mcp_call_tool("create_watchlist", {"display_name": WATCHLIST_NAME, "icon_emoji": "📡"})
            lists = json.loads(mcp_call_tool("get_watchlists", {}))["data"]["watchlists"]
            rid = next((w["id"] for w in lists if w["display_name"] == WATCHLIST_NAME), None)
        if not rid:
            return "could not find/create the Radar watchlist"
        mcp_call_tool("add_to_watchlist", {"list_id": rid, "symbols": symbols})
        return f"synced {len(symbols)} symbols to the '{WATCHLIST_NAME}' watchlist"
    except Exception as ex:  # noqa: BLE001
        return f"watchlist sync skipped ({ex}); candidates are saved in radar.json"


# ------------------------------ deploy + run ---------------------------------
def deploy_scout() -> str:
    state = load_state()
    agent_id = state.get(AGENT_ID_KEY)
    if agent_id:
        if state.get(AGENT_SPEC_KEY) != SPEC_VERSION:
            cur = client().beta.agents.retrieve(agent_id)
            client().beta.agents.update(agent_id, version=cur.version, model=MODEL,
                                        system=SYSTEM, tools=TOOLS, mcp_servers=MCP_SERVERS)
            state[AGENT_SPEC_KEY] = SPEC_VERSION; save_state(state)
            print(f"[deploy] updated scout {agent_id}")
        else:
            print(f"[deploy] scout already hosted: {agent_id}")
        return agent_id
    agent = client().beta.agents.create(name="Sector Radar Scout", model=MODEL,
                                        system=SYSTEM, mcp_servers=MCP_SERVERS, tools=TOOLS)
    state[AGENT_ID_KEY] = agent.id; state[AGENT_SPEC_KEY] = SPEC_VERSION; save_state(state)
    print(f"[deploy] hosted new scout on CMA: {agent.id} (v{agent.version})")
    return agent.id


def run_sweep(agent_id: str) -> None:
    env_id = get_or_create_environment()
    vault_id = get_or_create_vault()
    ensure_robinhood_credential(vault_id)
    session = client().beta.sessions.create(agent=agent_id, environment_id=env_id,
                                            vault_ids=[vault_id], title="radar sweep")
    print(f"[scout] session {session.id}")
    print(f"[scout] watch live: {console_url(session.id)}\n")

    c = client()
    pending: list = []
    with c.beta.sessions.events.stream(session_id=session.id) as stream:
        c.beta.sessions.events.send(session_id=session.id, events=[{
            "type": "user.message",
            "content": [{"type": "text", "text":
                f"Run a sector radar sweep now. Today is {date.today().isoformat()}. "
                "Cover the major sectors, prioritizing the strongest current catalyst "
                "chains (policy, geopolitics, big investments, insider/institutional). "
                "Surface 8–15 candidates across different sectors via add_candidate.\n\n"
                f"{theses_index_text()}"}],
        }])
        for event in stream:
            t = event.type
            if t == "agent.message":
                for b in event.content:
                    if b.type == "text":
                        print(b.text, end="", flush=True)
            elif t == "agent.custom_tool_use":
                pending.append(event)
            elif t in ("agent.mcp_tool_use", "agent.tool_use"):
                print(f"\n  · {getattr(event,'name','?')}…", flush=True)
            elif t == "session.status_terminated":
                break
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
                        c.beta.sessions.events.send(session_id=session.id, events=results)
                    continue
                break

    # Deterministic, host-side: push the radar onto your Robinhood watchlist.
    syms = R.symbols()
    print(f"\n\n[scout] {len(syms)} candidates: {syms}")
    print("[scout] " + sync_watchlist(syms))
    print("\n--- RADAR (by horizon) ---")
    bh = R.by_horizon()
    for hz in ("short", "long"):
        print(f"\n{hz.upper()} TERM:")
        for c_ in bh.get(hz, []):
            print(f"  {c_['symbol']:<6} {c_['sector']:<22} conv {c_['conviction']:.2f} "
                  f"[{c_['catalyst_type']}] {c_['thesis'][:90]}")
    report_cost(session.id, model=MODEL)


def main() -> None:
    agent_id = deploy_scout()
    if len(sys.argv) > 1 and sys.argv[1] == "deploy":
        print("[scout] deploy-only."); return
    run_sweep(agent_id)


if __name__ == "__main__":
    main()
