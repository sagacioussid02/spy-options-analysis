"""
graph_committee.py — the SAME Bull -> Bear -> PM debate as committee.py,
wrapped in an explicit LangGraph state machine instead of run_once()'s
straight-line script. This is the "V2" step of the learning roadmap in
newdesign.txt: multi-agent specialization, agent-to-agent communication,
and shared state — now made explicit as graph state instead of local
variables threaded by hand through three sequential function calls.

Graph:

    setup -> bull -> bear -> pm -+-> live_pending -+-> record_debate -> END
                                  +----------------/

`bull`/`bear`/`pm` are still THREE SEPARATE hosted CMA sessions (via
committee._run_session, reused unchanged) — same reason committee.py keeps
them separate: the Bear must rebut a case it didn't write.

Unlike V1 (graph_advisor.py), this graph has no interrupt/checkpointer: the
debate is inherently sequential and runs start-to-finish in one process,
same as committee.py today. A live-mode PM proposal doesn't pause this
graph for approval — it just sits in the journal as status='proposed',
exactly as committee.py's docstring already documents ("queues for human
approval via advisor.py"). journal.pending_proposals() doesn't filter by
origin, so /approve in advisor.py OR graph_advisor.py already handles it;
duplicating V1's human_review subgraph here would just be redundant.

Run:
    .venv/bin/python cma_lab/graph_committee.py deploy
    .venv/bin/python cma_lab/graph_committee.py
"""
from __future__ import annotations

import json
import sys
import uuid
from datetime import datetime, timezone
from typing import Optional, TypedDict

from langgraph.graph import END, START, StateGraph

import exploration
from committee import (
    DEBATES_DIR,
    READ_HANDLERS,
    _activity_status,
    _calibration_text,
    _debate_track_record,
    _read_beliefs,
    _run_session,
    deploy_bear,
    deploy_bull,
    deploy_pm,
    h_engine,
    h_regret,
    make_h_log_prediction,
    make_h_pass,
    make_h_pm_propose,
    make_h_register_hypothesis,
)
from execution import J
from futurist import theses_index_text
from lab import TICKER, ensure_robinhood_credential, get_or_create_environment, get_or_create_vault
from playbook import Playbook
from shadow import ShadowStore


# ------------------------------ state -----------------------------------
class CommitteeState(TypedDict, total=False):
    debate_id: str
    env_id: str
    vault_id: str
    bull_id: str
    bear_id: str
    pm_id: str
    context: dict
    bull_case: dict
    bear_case: dict
    pm_decision: dict


# ------------------------------ nodes -------------------------------------
def setup(state: CommitteeState) -> dict:
    """One-time setup: mint debate_id, ensure env/vault/credential, deploy
    the three hosted personas, gather the shared context every persona's
    kickoff draws from (was recomputed inline in run_once(); here it's
    graph state, shared by reference instead of recomputed per node)."""
    debate_id = "deb_" + uuid.uuid4().hex[:10]
    env_id = get_or_create_environment()
    vault_id = get_or_create_vault()
    ensure_robinhood_credential(vault_id)
    bull_id = deploy_bull(); bear_id = deploy_bear(); pm_id = deploy_pm()

    context = {
        "engine_snapshot": h_engine({}),
        "activity": _activity_status(),
        "regret": h_regret({}),
        "playbook_view": Playbook().context_view(),
        "theses_view": theses_index_text(),
        "debate_track_record": _debate_track_record(),
        "calibration": _calibration_text(),
        "exploration_status": exploration.status_text(),
    }
    print(f"\n=== graph committee debate {debate_id} ===")
    return {"debate_id": debate_id, "env_id": env_id, "vault_id": vault_id,
            "bull_id": bull_id, "bear_id": bear_id, "pm_id": pm_id, "context": context}


def bull(state: CommitteeState) -> dict:
    ctx = state["context"]
    print("\n--- BULL ---")
    kickoff = (
        f"Open today's {TICKER} committee debate as the Bull. Your accumulated beliefs "
        f"(weigh them, don't just recite):\n{_read_beliefs('bull')}\n\n"
        f"The current hypothesis playbook (trial/active/retired ideas the desk "
        f"is tracking):\n{ctx['playbook_view']}\n\n"
        f"{ctx['theses_view']}\n\n"
        "Gather context with your tools, then call submit_case with a concrete, "
        "falsifiable case."
    )
    _, captured = _run_session(
        state["bull_id"], state["env_id"], state["vault_id"], title=f"{state['debate_id']}-bull",
        kickoff_text=kickoff,
        handlers={**READ_HANDLERS, "submit_case": lambda i: "Case recorded.",
                 "register_hypothesis": make_h_register_hypothesis("bull"),
                 "log_prediction": make_h_log_prediction("bull", state["debate_id"])},
        capture={"submit_case"})
    return {"bull_case": captured.get("submit_case", {})}


def bear(state: CommitteeState) -> dict:
    ctx = state["context"]
    print("\n--- BEAR ---")
    kickoff = (
        f"Your beliefs (weigh, don't just recite):\n{_read_beliefs('bear')}\n\n"
        f"The current hypothesis playbook:\n{ctx['playbook_view']}\n\n"
        f"{ctx['theses_view']}\n\n"
        # This is the agent-to-agent handoff: the Bull's finished case,
        # passed as graph state instead of a hand-threaded function arg.
        f"Here is the Bull's full case:\n{json.dumps(state['bull_case'], indent=2)}\n\n"
        "Attack its strongest points using your own evidence, or propose an "
        "alternative read. Then call submit_case with YOUR stance."
    )
    _, captured = _run_session(
        state["bear_id"], state["env_id"], state["vault_id"], title=f"{state['debate_id']}-bear",
        kickoff_text=kickoff,
        handlers={**READ_HANDLERS, "submit_case": lambda i: "Case recorded.",
                 "register_hypothesis": make_h_register_hypothesis("bear"),
                 "log_prediction": make_h_log_prediction("bear", state["debate_id"])},
        capture={"submit_case"})
    return {"bear_case": captured.get("submit_case", {})}


def pm(state: CommitteeState) -> dict:
    ctx = state["context"]
    debate_id = state["debate_id"]
    print("\n--- PM ---")
    kickoff = (
        f"Your beliefs (weigh, don't just recite):\n{_read_beliefs('pm')}\n\n"
        f"The current hypothesis playbook:\n{ctx['playbook_view']}\n\n"
        f"{ctx['theses_view']}\n\n"
        f"Bull case:\n{json.dumps(state['bull_case'], indent=2)}\n\n"
        f"Bear case:\n{json.dumps(state['bear_case'], indent=2)}\n\n"
        f"{ctx['activity']}\n"
        f"{ctx['debate_track_record']}\n"
        f"Regret stats (past passes graded against what happened): {ctx['regret']}\n"
        f"{ctx['calibration']}\n"
        f"{ctx['exploration_status']}\n\n"
        "Decide: propose_trade or pass_with_reason."
    )
    handlers = {**READ_HANDLERS,
               "propose_trade": make_h_pm_propose(debate_id),
               "pass_with_reason": make_h_pass(debate_id, state["bull_case"]),
               "register_hypothesis": make_h_register_hypothesis("pm"),
               "log_prediction": make_h_log_prediction("pm", debate_id)}
    _run_session(state["pm_id"], state["env_id"], state["vault_id"], title=f"{debate_id}-pm",
                kickoff_text=kickoff, handlers=handlers, capture=set())

    # Resolve from what was actually WRITTEN, not the model's claimed intent —
    # journal.json / shadow.json are the source of truth (same as run_once()).
    journal_entries = [e for e in J._load() if e.get("debate_id") == debate_id]
    shadow_entries = [e for e in ShadowStore()._load() if e.get("debate_id") == debate_id]
    if journal_entries:
        pm_decision = {"decision": "propose", "journal_id": journal_entries[-1]["id"],
                      "mode": journal_entries[-1].get("mode")}
    elif shadow_entries:
        pm_decision = {"decision": "pass", "shadow_id": shadow_entries[-1]["id"]}
    else:
        pm_decision = {"decision": "unclear",
                      "note": "PM produced neither a proposal nor a pass"}
    return {"pm_decision": pm_decision}


def route_after_pm(state: CommitteeState) -> str:
    """The one new conditional edge V2 adds: sim proposals already
    auto-executed inline (inside make_h_pm_propose's execute_sim call) — a
    live proposal did NOT, and stays pending for a human. Both paths
    record the debate; this just makes that distinction visible in the
    graph instead of letting it pass silently."""
    d = state.get("pm_decision") or {}
    if d.get("decision") == "propose" and d.get("mode") == "live":
        return "live_pending"
    return "record_debate"


def live_pending(state: CommitteeState) -> dict:
    jid = (state.get("pm_decision") or {}).get("journal_id")
    print(f"\n[live_pending] proposal {jid} is LIVE and awaiting human review — "
          f"not auto-executed. Use advisor.py's or graph_advisor.py's /approve "
          f"{jid} when ready.")
    return {}


def record_debate(state: CommitteeState) -> dict:
    debate_id = state["debate_id"]
    debate = {
        "id": debate_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "engine_snapshot": state["context"]["engine_snapshot"],
        "bull_case": state.get("bull_case", {}),
        "bear_case": state.get("bear_case", {}),
        "pm_decision": state.get("pm_decision", {}),
    }
    DEBATES_DIR.mkdir(exist_ok=True)
    (DEBATES_DIR / f"{debate_id}.json").write_text(json.dumps(debate, indent=2))
    print(f"\n=== debate {debate_id} recorded: {debate['pm_decision'].get('decision')} ===")
    return {}


# ------------------------------ graph --------------------------------------
def build_graph() -> StateGraph:
    g = StateGraph(CommitteeState)
    g.add_node("setup", setup)
    g.add_node("bull", bull)
    g.add_node("bear", bear)
    g.add_node("pm", pm)
    g.add_node("live_pending", live_pending)
    g.add_node("record_debate", record_debate)

    g.add_edge(START, "setup")
    g.add_edge("setup", "bull")
    g.add_edge("bull", "bear")
    g.add_edge("bear", "pm")
    g.add_conditional_edges("pm", route_after_pm,
                            {"live_pending": "live_pending", "record_debate": "record_debate"})
    g.add_edge("live_pending", "record_debate")
    g.add_edge("record_debate", END)
    return g


def run_debate() -> dict:
    graph = build_graph().compile()
    return graph.invoke({})


def main() -> None:
    args = sys.argv[1:]
    if args and args[0] == "deploy":
        deploy_bull(); deploy_bear(); deploy_pm()
        print("[graph_committee] deploy-only.")
        return
    run_debate()


if __name__ == "__main__":
    main()
