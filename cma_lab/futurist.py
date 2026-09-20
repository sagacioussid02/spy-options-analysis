"""
Futurist — the desk's long-horizon (3-12mo) research persona.

Monthly (or on demand): FIRST reviews every existing thesis against its own
past predictions and current news (verdict: strengthening/intact/weakening/
invalidated — invalidated ones move to theses/archive/), THEN researches ONE
new industry or single-stock view and writes it to cma_lab/theses/<slug>.md,
logging 2-4 falsifiable predictions to the shared prediction ledger.

Radar scout stays the short-horizon catalyst finder; this is the long-horizon
thinker. Bull/bear/PM (committee.py) and scout.py both get a compact index of
current theses via theses_index_text() — that's how a "strengthening" macro
view can get cited in a same-day SPY debate.

Trading stays SPY-only regardless of what this researches — widening the
tradable universe is a separate, deliberate change (whitelist + funding), not
something this persona can affect.

Run:
    .venv/bin/python cma_lab/futurist.py
    .venv/bin/python cma_lab/futurist.py deploy
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

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
from playbook import _slug
from radar import Radar

MODEL = "claude-sonnet-4-6"
AGENT_ID_KEY = "futurist_agent_id"
AGENT_SPEC_KEY = "futurist_agent_spec"
SPEC_VERSION = 1

from store import store
_VERDICTS = {"strengthening", "intact", "weakening", "invalidated"}

READ_TOOLS = ["search", "get_equity_quotes", "get_equity_tradability"]

CUSTOM_TOOLS = [
    {"type": "custom", "name": "get_theses_full",
     "description": "Full text of every existing thesis (for review). Empty if none yet.",
     "input_schema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"type": "custom", "name": "get_futurist_predictions",
     "description": "All predictions you've logged in past runs, with resolution "
                    "status — use to judge whether your past theses are playing out.",
     "input_schema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"type": "custom", "name": "get_radar_candidates",
     "description": "The short-horizon scout's current candidate list — raw "
                    "material, not a substitute for your own research.",
     "input_schema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"type": "custom", "name": "review_thesis",
     "description": "Record this run's review verdict for an EXISTING thesis: "
                    "strengthening | intact | weakening | invalidated, with a "
                    "dated note citing what you found (resolved predictions, "
                    "news). Invalidated theses are archived automatically. Do "
                    "this for EVERY existing thesis before writing a new one.",
     "input_schema": {
         "type": "object",
         "properties": {
             "slug": {"type": "string"},
             "verdict": {"type": "string", "description": "strengthening | intact | weakening | invalidated"},
             "note": {"type": "string"},
         },
         "required": ["slug", "verdict", "note"],
         "additionalProperties": False,
     }},
    {"type": "custom", "name": "write_thesis",
     "description": "Write (or fully rewrite the content of) a 3-12 month thesis "
                    "on an industry or single stock. Log 2-4 falsifiable "
                    "predictions via log_prediction (category industry or stock) "
                    "for this thesis, tagged with this same slug.",
     "input_schema": {
         "type": "object",
         "properties": {
             "slug": {"type": "string", "description": "kebab-case id, e.g. 'power-datacenter-buildout'."},
             "title": {"type": "string"},
             "subject": {"type": "string", "description": "'industry' or 'stock'"},
             "view": {"type": "string", "description": "The 3-12mo thesis: where this is heading and why."},
             "winners_losers": {"type": "string"},
             "catalysts": {"type": "string", "description": "Key events / timeline."},
             "what_would_change_my_mind": {"type": "string"},
         },
         "required": ["slug", "title", "subject", "view", "catalysts",
                      "what_would_change_my_mind"],
         "additionalProperties": False,
     }},
    {"type": "custom", "name": "log_prediction",
     "description": "Log a falsifiable prediction tied to a thesis slug. Must be "
                    "measurable and resolvable by horizon_date; vague claims are "
                    "rejected. Log 2-4 per new/updated thesis.",
     "input_schema": {
         "type": "object",
         "properties": {
             "slug": {"type": "string", "description": "The thesis slug this prediction supports."},
             "claim": {"type": "string"},
             "probability": {"type": "number", "description": "0.05-0.95"},
             "category": {"type": "string", "description": "industry | stock (or price/macro if applicable)"},
             "horizon_date": {"type": "string", "description": "ISO date, e.g. 2027-01-31"},
             "basis": {"type": "string"},
             "symbol": {"type": "string", "description": "only if category=price"},
             "level": {"type": "number", "description": "only if category=price"},
             "direction": {"type": "string", "description": "only if category=price"},
         },
         "required": ["slug", "claim", "probability", "category", "horizon_date", "basis"],
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
    "You are the desk's long-horizon Futurist — you think in quarters and years, "
    "not days. Each run has two phases, IN ORDER:\n"
    "1) REVIEW: call get_theses_full and get_futurist_predictions. For EVERY "
    "existing thesis, check whether its predictions resolved as expected and "
    "search for recent news (web_search), then call review_thesis with an "
    "honest verdict (strengthening/intact/weakening/invalidated) and a specific "
    "dated reason. Don't skip this even if it's tedious — stale theses left "
    "unreviewed are worse than no thesis.\n"
    "2) RESEARCH: pick ONE new industry or single-stock 3-12 month view "
    "(get_radar_candidates for raw material, web_search/web_fetch for depth, "
    "Robinhood read tools to check tradability/quotes). Call write_thesis with "
    "a concrete view, winners/losers, catalysts/timeline, and what would change "
    "your mind — then log_prediction 2-4 times for it (category industry or "
    "stock), each a specific, falsifiable, dated claim, not a vague lean.\n"
    f"Trading stays {TICKER}-only regardless of what you research — you're building "
    f"the desk's research capability and its {TICKER} macro view, not proposing "
    "trades in these names."
)


# ------------------------------ handlers -------------------------------------
def _theses() -> dict:
    """{slug: markdown} — collection "theses" (theses/<slug>.md locally)."""
    return store().load("theses", {}) or {}


def h_theses_full(_i) -> str:
    theses = _theses()
    if not theses:
        return "(no theses yet)"
    return "\n\n---\n\n".join(theses[k] for k in sorted(theses))


def h_futurist_predictions(_i) -> str:
    from predictions import PredictionStore
    entries = [e for e in PredictionStore()._load() if e.get("persona") == "futurist"]
    return json.dumps(entries, indent=2) if entries else "(no futurist predictions yet)"


def h_radar_candidates(_i) -> str:
    return json.dumps(Radar().list(), indent=2)


def h_review_thesis(inp: dict) -> str:
    slug = _slug(str(inp.get("slug", "")).strip())
    verdict = str(inp.get("verdict", "")).strip().lower()
    note = str(inp.get("note", "")).strip()
    if verdict not in _VERDICTS:
        return f"Rejected: verdict must be one of {sorted(_VERDICTS)}."
    if not note:
        return "Rejected: note required."
    theses = _theses()
    if slug not in theses:
        return f"Rejected: no thesis {slug} — write_thesis first."
    text = theses[slug]
    today = datetime.now(timezone.utc).date().isoformat()
    text = re.sub(r"^status: .*$", f"status: {verdict}", text, count=1, flags=re.MULTILINE)
    text += f"\n### {today} — {verdict}\n{note}\n"
    if verdict == "invalidated":
        archive = store().load("theses_archive", {}) or {}
        archive[slug] = text
        store().save("theses_archive", archive)
        del theses[slug]
        store().save("theses", theses)
        return f"Thesis {slug} marked invalidated and archived."
    theses[slug] = text
    store().save("theses", theses)
    return f"Thesis {slug} reviewed: {verdict}."


def h_write_thesis(inp: dict) -> str:
    slug = _slug(str(inp.get("slug", "")).strip())
    if not slug:
        return "Rejected: slug required."
    today = datetime.now(timezone.utc).date().isoformat()
    body = (
        f"# {str(inp.get('title', '')).strip()}\n\n"
        f"slug: {slug}\n"
        f"subject: {str(inp.get('subject', '')).strip()}\n"
        f"last_updated: {today}\n"
        f"status: active\n\n"
        f"## View\n{str(inp.get('view', '')).strip()}\n\n"
        f"## Winners / Losers\n{str(inp.get('winners_losers', '')).strip()}\n\n"
        f"## Catalysts / Timeline\n{str(inp.get('catalysts', '')).strip()}\n\n"
        f"## What Would Change My Mind\n{str(inp.get('what_would_change_my_mind', '')).strip()}\n\n"
        f"## Review Log\n(none yet)\n"
    )
    theses = _theses()
    theses[slug] = body
    store().save("theses", theses)
    return f"Thesis written: {slug}"


def h_log_prediction(inp: dict) -> str:
    from predictions import PredictionStore, PredictionValidationError
    slug = _slug(str(inp.pop("slug", "")).strip())
    try:
        p = PredictionStore().log(persona="futurist", debate_id=f"thesis:{slug}", **inp)
    except PredictionValidationError as ex:
        return f"Prediction rejected: {ex} Fix it and call log_prediction again."
    return (f"Prediction logged: {p['id']} ({p['category']}, p={p['probability']:.2f}, "
            f"resolves {p['horizon_date']}) for thesis '{slug}'.")


HANDLERS = {
    "get_theses_full": h_theses_full,
    "get_futurist_predictions": h_futurist_predictions,
    "get_radar_candidates": h_radar_candidates,
    "review_thesis": h_review_thesis,
    "write_thesis": h_write_thesis,
    "log_prediction": h_log_prediction,
}


# ------------------------------ shared index (for committee.py / scout.py) ---
def theses_index_text() -> str:
    """Compact index for injection into other personas' context: slug, one-line
    view, status, next catalyst hint. Never raises — worst case, says none yet."""
    theses = _theses()
    if not theses:
        return "Theses index: none yet."
    lines = ["Theses index (long-horizon research from the Futurist):"]
    for slug in sorted(theses):
        text = theses[slug]
        title = text.splitlines()[0].lstrip("#").strip() if text else slug
        m = re.search(r"^status: (.+)$", text, re.MULTILINE)
        status = m.group(1).strip() if m else "?"
        lines.append(f"  - {slug} [{status}]: {title}")
    return "\n".join(lines)


# ------------------------------ deploy + run ----------------------------------
def deploy_futurist() -> str:
    state = load_state()
    agent_id = state.get(AGENT_ID_KEY)
    if agent_id:
        if state.get(AGENT_SPEC_KEY) != SPEC_VERSION:
            cur = client().beta.agents.retrieve(agent_id)
            client().beta.agents.update(agent_id, version=cur.version, model=MODEL,
                                        system=SYSTEM, tools=TOOLS, mcp_servers=MCP_SERVERS)
            state[AGENT_SPEC_KEY] = SPEC_VERSION
            save_state(state)
            print(f"[deploy] updated futurist {agent_id} -> spec v{SPEC_VERSION}")
        else:
            print(f"[deploy] futurist already hosted: {agent_id}")
        return agent_id
    agent = client().beta.agents.create(name=f"{TICKER} Desk Futurist", model=MODEL,
                                        system=SYSTEM, mcp_servers=MCP_SERVERS, tools=TOOLS)
    state[AGENT_ID_KEY] = agent.id
    state[AGENT_SPEC_KEY] = SPEC_VERSION
    save_state(state)
    print(f"[deploy] hosted new futurist on CMA: {agent.id} (v{agent.version})")
    return agent.id


def run_futurist(agent_id: str) -> None:
    env_id = get_or_create_environment()
    vault_id = get_or_create_vault()
    ensure_robinhood_credential(vault_id)
    session = client().beta.sessions.create(agent=agent_id, environment_id=env_id,
                                            vault_ids=[vault_id], title="futurist run")
    print(f"[futurist] session {session.id}")
    print(f"[futurist] watch live: {console_url(session.id)}\n")

    c = client()
    pending: list = []
    with c.beta.sessions.events.stream(session_id=session.id) as stream:
        c.beta.sessions.events.send(session_id=session.id, events=[{
            "type": "user.message",
            "content": [{"type": "text", "text":
                "Run your monthly cycle now: review every existing thesis first "
                "(review_thesis for each), then research and write ONE new "
                "industry or single-stock 3-12 month thesis with its "
                "predictions."}],
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
                print(f"\n  · {getattr(event, 'name', '?')}…", flush=True)
            elif t == "session.error":
                print(f"\n[session error] {getattr(event, 'error', event)}")
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
                print()
                break

    print("\n--- theses index ---")
    print(theses_index_text())
    report_cost(session.id, model=MODEL, label=f"{TICKER}:futurist run")


def main() -> None:
    agent_id = deploy_futurist()
    if len(sys.argv) > 1 and sys.argv[1] == "deploy":
        print("[futurist] deploy-only.")
        return
    run_futurist(agent_id)


if __name__ == "__main__":
    main()
