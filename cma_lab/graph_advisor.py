"""
graph_advisor.py — the SAME propose -> risk-check -> human-approve -> execute
flow as advisor.py, wrapped in an explicit LangGraph state machine instead of
an imperative while-loop. This is the "V1" step of the learning roadmap in
newdesign.txt: State -> Nodes -> Edges -> Conditional routing -> Persistence
-> Resume, against logic you already trust (advisor.py keeps working as the
comparison point — nothing in it, execution.py, risk_gate.py, or journal.py
is modified).

Graph:

    load_context -> propose -> risk_check -+-> auto_reject -> END
                                            |
                                            +-> human_review -+-> execute -> END
                                                               +-> reject_end -> END

`human_review` is a real LangGraph interrupt() -- the process can exit between
proposing and approving, and /approve later RESUMES the same graph run from a
SQLite checkpoint (cma_lab/graph_state.db). That's the actual difference from
advisor.py's same-process while-loop.

Because LangGraph needs a thread_id at the START of a run (before the journal
entry that identifies the proposal even exists), each run gets a fresh
thread_id and, once propose() discovers the journal entry it created, the
(entry_id -> thread_id) pairing is recorded in cma_lab/graph_threads.json so
/approve <entry_id> can find its way back to the paused graph.

Run:
    .venv/bin/python cma_lab/graph_advisor.py deploy
    .venv/bin/python cma_lab/graph_advisor.py
"""
from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path
from typing import Optional, TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

import execution
from advisor import (
    MODEL,
    deploy_advisor,
    h_engine,
    h_lessons,
    h_risk,
    h_standing,
    h_summary,
    run_turn,
)
from execution import J
from lab import (
    client,
    console_url,
    ensure_robinhood_credential,
    get_or_create_environment,
    get_or_create_vault,
    report_cost,
)

THREADS_PATH = Path(__file__).parent / "graph_threads.json"
DB_PATH = Path(__file__).parent / "graph_state.db"

KICKOFF = (
    "Analyze the current setup (engine, account, market, your track record, "
    "lessons) and either propose a sized trade via propose_trade, or say "
    "explicitly that you'd stand aside right now and why."
)


# ------------------------------ state -----------------------------------
class AdvisorState(TypedDict, total=False):
    kickoff_text: str
    session_id: str
    context: dict
    entry_id: Optional[str]
    risk_reason: Optional[str]        # None => allowed
    human_decision: Optional[dict]    # {"decision": "approve"|"reject", "note": str}
    execution_result: Optional[str]


# ------------------------------ thread <-> journal mapping ----------------
def _load_threads() -> dict:
    if THREADS_PATH.exists():
        return json.loads(THREADS_PATH.read_text())
    return {}


def _save_thread(entry_id: str, thread_id: str) -> None:
    threads = _load_threads()
    threads[entry_id] = thread_id
    THREADS_PATH.write_text(json.dumps(threads, indent=2))


def _thread_for(entry_id: str) -> Optional[str]:
    return _load_threads().get(entry_id)


# ------------------------------ nodes -------------------------------------
def load_context(state: AdvisorState) -> dict:
    """Read-only snapshot of engine/journal/lessons/risk, no LLM call. Purely
    for state visibility -- the hosted advisor also fetches these itself, via
    the same get_engine_analysis/get_journal_summary/... tools, during
    propose(). This node exists so the graph's own state has the snapshot the
    decision was made against."""
    ctx = {
        "engine": h_engine({})[:2000],
        "journal_summary": h_summary({}),
        "lessons": h_lessons({})[:1000],
        "risk": h_risk({}),
    }
    print("[load_context] snapshot loaded (engine/journal/lessons/risk)")
    return {"context": ctx}


def propose(state: AdvisorState) -> dict:
    """Run one turn against the hosted CMA advisor agent (same agent
    advisor.py uses) and detect the journal entry it created via
    propose_trade. No changes to advisor.py -- deploy_advisor()/run_turn()
    are imported and reused as-is."""
    agent_id = deploy_advisor()
    env_id = get_or_create_environment()
    vault_id = get_or_create_vault()
    ensure_robinhood_credential(vault_id)
    session = client().beta.sessions.create(
        agent=agent_id, environment_id=env_id, vault_ids=[vault_id],
        title="graph advisor run",
    )
    print(f"[propose] session {session.id} ({console_url(session.id)})")

    before = {e["id"] for e in J.pending_proposals()}
    print("advisor> ", end="", flush=True)
    run_turn(session.id, state.get("kickoff_text") or KICKOFF)
    print()
    report_cost(session.id, model=MODEL)

    after = J.pending_proposals()
    new_ids = [e["id"] for e in after if e["id"] not in before]
    entry_id = new_ids[-1] if new_ids else None
    if not entry_id:
        print("[propose] no propose_trade call this turn (advisor stood aside).")
    return {"session_id": session.id, "entry_id": entry_id}


def risk_check(state: AdvisorState) -> dict:
    """Deterministic: gate the EXACT proposed order (same check
    execute_approved re-runs at execution time -- this just surfaces it
    earlier, before the human is even asked). Reuses
    execution._gate_and_afford, the one shared gate+affordability check."""
    entry_id = state.get("entry_id")
    if not entry_id:
        return {"risk_reason": "no proposal to check"}
    entry = J.get(entry_id)
    reason, _px = execution._gate_and_afford(entry)
    if reason:
        print(f"[risk_check] DENY: {reason}")
    else:
        print("[risk_check] ALLOW — passes risk gate + affordability")
    return {"risk_reason": reason}


def route_after_risk(state: AdvisorState) -> str:
    if not state.get("entry_id"):
        return "end"
    return "auto_reject" if state.get("risk_reason") else "human_review"


def auto_reject(state: AdvisorState) -> dict:
    entry_id = state.get("entry_id")
    if entry_id:
        J.reject(entry_id, note=f"auto-rejected by risk gate: {state.get('risk_reason')}")
        print(f"[auto_reject] {entry_id} rejected without human review.")
    return {}


def human_review(state: AdvisorState) -> dict:
    """The actual interrupt: pauses here, persisted to graph_state.db, until
    /approve or /reject resumes this thread (possibly in a later process)."""
    decision = interrupt({
        "entry_id": state["entry_id"],
        "risk": "allowed",
    })
    return {"human_decision": decision}


def route_after_human(state: AdvisorState) -> str:
    decision = (state.get("human_decision") or {}).get("decision")
    return "execute" if decision == "approve" else "reject_end"


def execute(state: AdvisorState) -> dict:
    entry = J.get(state["entry_id"])  # re-read: may have been /tweak-ed
    if entry.get("status") == "rejected":
        return {"execution_result": "already rejected — nothing to execute"}
    J.approve(entry["id"], note=(state.get("human_decision") or {}).get("note", "approved via graph"))
    entry = J.get(entry["id"])
    result = execution.execute_approved(entry)
    print(f"[execute] {result}")
    return {"execution_result": result}


def reject_end(state: AdvisorState) -> dict:
    entry_id = state.get("entry_id")
    note = (state.get("human_decision") or {}).get("note", "")
    if entry_id:
        J.reject(entry_id, note=note)
        print(f"[reject_end] {entry_id} rejected.")
    return {}


# ------------------------------ graph --------------------------------------
def build_graph() -> StateGraph:
    g = StateGraph(AdvisorState)
    g.add_node("load_context", load_context)
    g.add_node("propose", propose)
    g.add_node("risk_check", risk_check)
    g.add_node("auto_reject", auto_reject)
    g.add_node("human_review", human_review)
    g.add_node("execute", execute)
    g.add_node("reject_end", reject_end)

    g.add_edge(START, "load_context")
    g.add_edge("load_context", "propose")
    g.add_edge("propose", "risk_check")
    g.add_conditional_edges("risk_check", route_after_risk,
                            {"auto_reject": "auto_reject", "human_review": "human_review",
                             "end": END})
    g.add_edge("auto_reject", END)
    g.add_conditional_edges("human_review", route_after_human,
                            {"execute": "execute", "reject_end": "reject_end"})
    g.add_edge("execute", END)
    g.add_edge("reject_end", END)
    return g


# ------------------------------ CLI -----------------------------------------
def start_proposal(saver, kickoff_text: str) -> None:
    graph = build_graph().compile(checkpointer=saver)
    thread_id = uuid.uuid4().hex
    cfg = {"configurable": {"thread_id": thread_id}}
    out = graph.invoke({"kickoff_text": kickoff_text}, config=cfg)

    entry_id = out.get("entry_id")
    if entry_id:
        _save_thread(entry_id, thread_id)
    if out.get("__interrupt__"):
        print(f"\n  paused for human_review — /approve {entry_id} | /reject {entry_id} "
              f"| /tweak {entry_id} qty=.. limit=..")
    elif not entry_id:
        pass  # advisor stood aside this turn; nothing to review
    else:
        print(f"\n  {entry_id} resolved without human review (auto-rejected by risk gate).")


def resume_proposal(saver, entry_id: str, decision: str, note: str = "") -> None:
    thread_id = _thread_for(entry_id)
    if not thread_id:
        print(f"  no graph thread for {entry_id} (was it proposed via graph_advisor.py?)")
        return
    graph = build_graph().compile(checkpointer=saver)
    cfg = {"configurable": {"thread_id": thread_id}}
    graph.invoke(Command(resume={"decision": decision, "note": note}), config=cfg)


def _pick_id(arg: Optional[str]) -> Optional[str]:
    if arg:
        return arg
    pend = J.pending_proposals()
    return pend[-1]["id"] if pend else None


def print_help() -> None:
    print("  commands: /pending | /approve [id] | /tweak <id> qty=.. limit=.. | "
          "/reject [id] [note] | /help | exit")
    print("  anything else starts a NEW proposal cycle (load_context -> propose "
          "-> risk_check -> human_review).")


def main() -> None:
    deploy_advisor()
    if len(sys.argv) > 1 and sys.argv[1] == "deploy":
        print("[graph_advisor] deploy-only."); return

    print("\nSPY Graph Advisor (LangGraph V1). state db: "
          f"{DB_PATH.name}\n")
    print_help(); print()

    with SqliteSaver.from_conn_string(str(DB_PATH)) as saver:
        while True:
            try:
                user = input("you> ").strip()
            except (EOFError, KeyboardInterrupt):
                print(); break
            if not user:
                continue
            if user.lower() in ("exit", "quit", "q"):
                break

            if user.startswith("/"):
                parts = user.split()
                cmd, arg = parts[0].lower(), (parts[1] if len(parts) > 1 else None)
                if cmd == "/pending":
                    pend = J.pending_proposals()
                    if not pend:
                        print("  (no pending proposals)")
                    for e in pend:
                        print(f"  {e['id']}: {e['side']} {e['quantity']:g} {e['symbol']} "
                              f"| conv {e['conviction']:.2f} | {e['strategy']}")
                elif cmd == "/approve":
                    eid = _pick_id(arg)
                    if not eid:
                        print("  no pending proposal.")
                    else:
                        resume_proposal(saver, eid, "approve")
                elif cmd == "/reject":
                    eid = _pick_id(arg)
                    note = " ".join(parts[2:]) if len(parts) > 2 else ""
                    if not eid:
                        print("  no pending proposal.")
                    else:
                        resume_proposal(saver, eid, "reject", note)
                elif cmd == "/tweak":
                    eid = _pick_id(arg)
                    if not eid:
                        print("  no pending proposal."); continue
                    changes = {}
                    for tok in parts[2:]:
                        if tok.startswith("qty="):
                            changes["quantity"] = float(tok[4:])
                        elif tok.startswith("limit="):
                            changes["limit_price"] = float(tok[6:])
                    if changes:
                        J._update(eid, **changes)
                        print(f"  tweaked {eid}: {changes}.")
                    else:
                        print("  usage: /tweak <id> qty=1 limit=687")
                elif cmd in ("/help", "help"):
                    print_help()
                else:
                    print(f"  unknown command {cmd}. /help for options.")
                continue

            start_proposal(saver, user)


if __name__ == "__main__":
    main()
