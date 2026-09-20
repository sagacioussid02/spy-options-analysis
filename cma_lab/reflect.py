"""
Reflection (step 3) — the system learns from its trades and adjusts, slowly.

A reflection agent reads your journal's track record (edge by strategy / regime /
conviction, with sample counts), your recent reflections, and current lessons,
then:
  1. rewrites lessons.md — distilled, honest insight the advisor reads next time;
  2. ONLY IF there's enough evidence, suggests ONE small bounded risk change
     (via propose_risk_change), which you apply yourself via the copilot.

Guardrails (host-side, not the model's discretion):
  - won't suggest changes until there are >= MIN_SAMPLE closed trades;
  - risk_appetite may move at most ONE notch (no jumps);
  - everything still clamps to the hard caps; equity_only / kill switch are off-limits;
  - suggestions are recorded for human approval, never auto-applied.

Run on demand (or schedule weekly later):
    .venv/bin/python cma_lab/reflect.py
    .venv/bin/python cma_lab/reflect.py deploy
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import lessons as lessons_store
from journal import TradeJournal
from lab import (
    client,
    console_url,
    ensure_robinhood_credential,
    get_or_create_environment,
    get_or_create_vault,
    load_state,
    report_cost,
    save_state,
)
from risk_gate import APPETITE_PRESETS, load_overrides, load_risk_config
from committee import load_debates, save_debate
from store import store

MODEL = "claude-sonnet-4-6"
AGENT_ID_KEY = "reflect_agent_id"
AGENT_SPEC_KEY = "reflect_agent_spec"
SPEC_VERSION = 3  # +thesis/debate grading, exploration review, beliefs updates

MIN_SAMPLE = 8           # don't adjust risk on fewer closed trades than this
APPETITE_ORDER = ["conservative", "moderate", "aggressive"]

_THESIS_GRADES = {"right_win", "right_loss", "wrong_win", "wrong_loss"}
_DEBATE_GRADES = {"bull_right", "bear_right", "both_wrong", "unclear"}

J = TradeJournal()

CUSTOM_TOOLS = [
    {"type": "custom", "name": "get_journal_summary",
     "description": "Track record: win-rate + P&L by strategy/regime/conviction with sample counts.",
     "input_schema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"type": "custom", "name": "get_recent_trades",
     "description": "Recent journal entries with theses, outcomes, and reflections.",
     "input_schema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"type": "custom", "name": "get_risk_settings",
     "description": "Current effective risk settings + hard caps.",
     "input_schema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"type": "custom", "name": "get_lessons",
     "description": "The current lessons.md (prior distilled insights).",
     "input_schema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"type": "custom", "name": "set_lessons",
     "description": "Replace lessons.md with updated, distilled, dated insight. Keep "
                    "it concise and honest about small samples.",
     "input_schema": {"type": "object", "properties": {"text": {"type": "string"}},
                      "required": ["text"], "additionalProperties": False}},
    {"type": "custom", "name": "propose_risk_change",
     "description": "Suggest ONE small risk change for the human to apply. "
                    "parameter ∈ {risk_appetite, max_shares, exploration_epsilon}. "
                    "Suggestions are "
                    "sample-gated and bounded; out-of-policy ones are rejected.",
     "input_schema": {"type": "object",
                      "properties": {"parameter": {"type": "string"},
                                     "value": {"type": "string"},
                                     "rationale": {"type": "string"}},
                      "required": ["parameter", "value", "rationale"],
                      "additionalProperties": False}},
    {"type": "custom", "name": "get_ungraded_trades",
     "description": "Closed journal entries that haven't been graded yet. For "
                    "each, judge whether the ORIGINAL THESIS played out (using "
                    "its thesis, kill_criteria, exit_plan, and outcome) "
                    "independent of whether it made money, then call grade_trade.",
     "input_schema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"type": "custom", "name": "grade_trade",
     "description": "Grade a closed trade on the thesis x outcome 2x2: "
                    "right_win (thesis played out, profitable), right_loss "
                    "(thesis played out, still lost — a sizing/execution lesson, "
                    "not a thesis failure), wrong_win (thesis was wrong but it "
                    "made money — LUCK, don't treat as edge), wrong_loss (thesis "
                    "wrong, lost — as expected).",
     "input_schema": {"type": "object",
                      "properties": {"entry_id": {"type": "string"},
                                     "thesis_grade": {"type": "string",
                                                      "description": "right_win | right_loss | wrong_win | wrong_loss"},
                                     "rationale": {"type": "string"}},
                      "required": ["entry_id", "thesis_grade", "rationale"],
                      "additionalProperties": False}},
    {"type": "custom", "name": "get_ungraded_debates",
     "description": "Committee debates whose outcome has RESOLVED (the linked "
                    "trade closed, or the linked shadow-pass matured) but haven't "
                    "been graded yet. For each, judge whether the bull's case or "
                    "the bear's case better matched what actually happened, then "
                    "call grade_debate.",
     "input_schema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"type": "custom", "name": "grade_debate",
     "description": "Grade a resolved committee debate: bull_right (the bull's "
                    "read matched what happened), bear_right, both_wrong, or "
                    "unclear. This feeds the PM's calibration context in future "
                    "debates.",
     "input_schema": {"type": "object",
                      "properties": {"debate_id": {"type": "string"},
                                     "grade": {"type": "string",
                                               "description": "bull_right | bear_right | both_wrong | unclear"},
                                     "rationale": {"type": "string"}},
                      "required": ["debate_id", "grade", "rationale"],
                      "additionalProperties": False}},
    {"type": "custom", "name": "get_shadow_stats",
     "description": "Hit-rate of past committee PASSes — of the trades not "
                    "taken, how many would have profited. Use this to comment on "
                    "whether the desk is too timid.",
     "input_schema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"type": "custom", "name": "update_beliefs",
     "description": "Append a dated note to a persona's beliefs file (bull, bear, "
                    "or pm) — based on GRADED evidence (debate grades, thesis "
                    "grades over several instances), never a single anecdote or "
                    "a vibe. Keep it short and specific; it's read verbatim next "
                    "session.",
     "input_schema": {"type": "object",
                      "properties": {"persona": {"type": "string", "description": "bull | bear | pm"},
                                     "note": {"type": "string"}},
                      "required": ["persona", "note"], "additionalProperties": False}},
    {"type": "custom", "name": "get_pending_predictions",
     "description": "Non-price predictions (macro/industry/stock) that have "
                    "matured (past their horizon_date) and still need resolving. "
                    "Research each with web_search, then call resolve_prediction.",
     "input_schema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"type": "custom", "name": "resolve_prediction",
     "description": "Resolve a matured non-price prediction to true or false, "
                    "with a one-line justification citing what you found. Price "
                    "predictions auto-resolve from quotes in the daily sweep and "
                    "cannot be overridden here.",
     "input_schema": {"type": "object",
                      "properties": {"prediction_id": {"type": "string"},
                                     "outcome": {"type": "boolean"},
                                     "justification": {"type": "string"}},
                      "required": ["prediction_id", "outcome", "justification"],
                      "additionalProperties": False}},
]

WEB_TOOLSET = {"type": "agent_toolset_20260401", "default_config": {"enabled": False},
              "configs": [{"name": "web_search", "enabled": True},
                          {"name": "web_fetch", "enabled": True}]}
TOOLS = [WEB_TOOLSET, *CUSTOM_TOOLS]

SYSTEM = (
    "You are a disciplined trading-performance reviewer. You read the user's trade "
    "journal and distill what actually has edge — by strategy, regime, and "
    "conviction — and update their lessons accordingly. You are deeply skeptical of "
    "small samples: a handful of trades is NOISE, not edge; prefer 'no change' and "
    "say so when the data is thin. Steps: read get_journal_summary, "
    "get_recent_trades, get_lessons, get_risk_settings. Then call set_lessons with "
    "a concise, dated, honest update (what's working, what isn't, what to do more/"
    "less of). Only if the evidence is genuinely sufficient, call propose_risk_change "
    "with ONE small adjustment and a clear rationale — otherwise explicitly "
    "recommend no change. You never place trades.\n\n"
    "Also check get_pending_predictions: for each matured non-price prediction "
    "(macro/industry/stock — price predictions auto-resolve from quotes and "
    "aren't your job), research it with web_search and call resolve_prediction "
    "with a one-line justification citing what you found. Don't guess without "
    "checking; if you genuinely can't determine the outcome, skip it rather "
    "than resolve it carelessly.\n\n"
    "Then close the learning loop on the committee: call get_ungraded_trades "
    "and grade_trade each one on the thesis x outcome 2x2 (a losing trade whose "
    "thesis played out is a SIZING lesson, not a thesis failure; a winning "
    "trade whose thesis was wrong is LUCK, not edge — say so explicitly in "
    "lessons). Call get_ungraded_debates and grade_debate each one (did the "
    "bull's read or the bear's read better match what happened?) — this is "
    "what lets the PM learn who to trust under disagreement.\n\n"
    "Check get_shadow_stats (the hit-rate of past PASSes) and comment in "
    "lessons on whether the desk is too timid or about right — with the "
    "sample count, never without it. Check get_journal_summary's by_origin "
    "cohort (exploration vs on_book) and report both cohorts' edge separately "
    "with sample counts; if there's a real, well-sampled difference, you MAY "
    "call propose_risk_change with parameter=exploration_epsilon (still "
    "sample-gated and bounded [0.10, 0.40] like every other suggestion) — "
    "otherwise say the sample is too thin to touch it.\n\n"
    "Finally, if — and only if — several GRADED debates or trades point the "
    "same direction (not one anecdote), call update_beliefs for the relevant "
    "persona(s) with a short, specific, dated note. Most runs should make zero "
    "or one belief update; if you're tempted to update all three every time, "
    "you're overfitting to noise."
)


def _current_appetite() -> str:
    return load_overrides().get("risk_appetite", "moderate")


# ------------------------------ handlers -------------------------------------
def h_summary(_i): return json.dumps(J.summarize(), indent=2)
def h_recent(_i): return json.dumps(J.recent(10), indent=2)
def h_lessons(_i): return lessons_store.read_lessons()


def h_risk(_i):
    c = load_risk_config()
    return (f"appetite={_current_appetite()}, max_shares={c.max_quantity:g}, "
            f"notional_cap=${c.max_notional_per_order:g}, kill_switch={c.kill_switch}, "
            f"equity_only={c.equity_only} (locked)")


def h_set_lessons(inp: dict) -> str:
    text = str(inp.get("text", "")).strip()[:6000]
    if not text:
        return "Rejected: empty lessons."
    lessons_store.set_lessons(text)
    return "Lessons updated."


def h_propose_risk_change(inp: dict) -> str:
    param = str(inp.get("parameter", "")).strip().lower()
    raw = str(inp.get("value", "")).strip()
    rationale = str(inp.get("rationale", "")).strip()

    closed = J.summarize().get("closed_trades", 0)
    if closed < MIN_SAMPLE:
        return (f"Not recorded: only {closed} closed trades (need >= {MIN_SAMPLE}). "
                f"Too small a sample to adjust risk — recommend no change.")

    if param in ("risk_appetite", "appetite"):
        v = raw.lower()
        if v not in APPETITE_PRESETS:
            return f"Rejected: appetite must be one of {list(APPETITE_PRESETS)}."
        cur = _current_appetite()
        if abs(APPETITE_ORDER.index(v) - APPETITE_ORDER.index(cur)) > 1:
            return (f"Rejected: appetite may move at most one notch (current={cur}). "
                    f"Suggest the adjacent level instead.")
        s = lessons_store.add_suggestion("risk_appetite", v, rationale)
        return f"Suggestion recorded for human approval: risk_appetite -> {v}. ({s['at']})"

    if param in ("max_shares", "max_quantity"):
        try:
            n = float(raw)
        except ValueError:
            return "Rejected: max_shares must be a number."
        s = lessons_store.add_suggestion("max_shares", str(n), rationale)
        return (f"Suggestion recorded for human approval: max_shares -> {n:g} "
                f"(will be clamped to the hard cap on apply).")

    if param in ("exploration_epsilon", "epsilon"):
        try:
            v = float(raw)
        except ValueError:
            return "Rejected: exploration_epsilon must be a number."
        v = max(0.10, min(v, 0.40))
        s = lessons_store.add_suggestion("exploration_epsilon", f"{v:.2f}", rationale)
        return (f"Suggestion recorded for human approval: exploration_epsilon -> "
                f"{v:.2f}. ({s['at']})")

    return "Rejected: only risk_appetite, max_shares, or exploration_epsilon may be suggested."


def h_ungraded_trades(_i) -> str:
    entries = [e for e in J._load() if e.get("status") == "closed" and not e.get("thesis_grade")]
    if not entries:
        return "(no ungraded closed trades)"
    view = [{"id": e["id"], "thesis": e.get("thesis"), "kill_criteria": e.get("kill_criteria"),
            "exit_plan": e.get("exit_plan"), "pnl": e.get("pnl"), "regime": e.get("regime"),
            "mode": e.get("mode"), "origin": e.get("origin"), "debate_id": e.get("debate_id")}
           for e in entries]
    return json.dumps(view, indent=2)


def h_grade_trade(inp: dict) -> str:
    entry_id = str(inp.get("entry_id", "")).strip()
    grade = str(inp.get("thesis_grade", "")).strip().lower()
    rationale = str(inp.get("rationale", "")).strip()
    if grade not in _THESIS_GRADES:
        return f"Rejected: thesis_grade must be one of {sorted(_THESIS_GRADES)}."
    e = J.get(entry_id)
    if not e:
        return f"Rejected: no entry {entry_id}."
    if e.get("status") != "closed":
        return f"Rejected: entry {entry_id} is not closed yet."
    note = (e.get("reflection") or "").strip()
    if rationale:
        note = (note + " | " if note else "") + f"[grade={grade}] {rationale}"
    J._update(entry_id, thesis_grade=grade, reflection=note)
    return f"Graded {entry_id}: {grade}."


def _debate_resolution(d: dict) -> dict | None:
    """None if not yet resolved; otherwise a small summary dict."""
    pm = d.get("pm_decision") or {}
    decision = pm.get("decision")
    if decision == "propose":
        e = J.get(pm.get("journal_id"))
        if e and e.get("status") == "closed":
            return {"kind": "trade", "pnl": e.get("pnl"), "thesis_grade": e.get("thesis_grade")}
    elif decision == "pass":
        from shadow import ShadowStore
        se = ShadowStore().get(pm.get("shadow_id"))
        if se and se.get("status") == "resolved":
            return {"kind": "shadow", "pnl_per_share": se.get("pnl")}
    return None


def h_ungraded_debates(_i) -> str:
    out = []
    for d in load_debates():
        if d.get("grade"):
            continue
        resolution = _debate_resolution(d)
        if resolution is None:
            continue
        out.append({"debate_id": d["id"], "bull_case": d.get("bull_case"),
                    "bear_case": d.get("bear_case"), "pm_decision": d.get("pm_decision"),
                    "resolution": resolution})
    return json.dumps(out, indent=2) if out else "(no ungraded resolved debates)"


def h_grade_debate(inp: dict) -> str:
    debate_id = str(inp.get("debate_id", "")).strip()
    grade = str(inp.get("grade", "")).strip().lower()
    rationale = str(inp.get("rationale", "")).strip()
    if grade not in _DEBATE_GRADES:
        return f"Rejected: grade must be one of {sorted(_DEBATE_GRADES)}."
    d = next((x for x in load_debates() if x.get("id") == debate_id), None)
    if d is None:
        return f"Rejected: no debate record for {debate_id}."
    d["grade"] = grade
    d["grade_rationale"] = rationale
    save_debate(d)
    return f"Graded debate {debate_id}: {grade}."


def h_shadow_stats(_i) -> str:
    from shadow import ShadowStore
    return json.dumps(ShadowStore().summarize())


def h_update_beliefs(inp: dict) -> str:
    persona = str(inp.get("persona", "")).strip().lower()
    note = str(inp.get("note", "")).strip()
    if persona not in ("bull", "bear", "pm"):
        return "Rejected: persona must be one of bull, bear, pm."
    if not note:
        return "Rejected: note required."
    beliefs = store().load("beliefs", {}) or {}
    existing = beliefs.get(persona) or f"# {persona} beliefs\n"
    today = datetime.now(timezone.utc).date().isoformat()
    beliefs[persona] = existing + f"\n\n## {today}\n{note}\n"
    store().save("beliefs", beliefs)
    return f"Beliefs updated for {persona}."


def h_pending_predictions(_i) -> str:
    from predictions import PredictionStore
    matured_non_price = [e for e in PredictionStore().matured() if e["category"] != "price"]
    return json.dumps(matured_non_price, indent=2) if matured_non_price else "(none matured)"


def h_resolve_prediction(inp: dict) -> str:
    from predictions import PredictionStore
    pred_id = str(inp.get("prediction_id", "")).strip()
    justification = str(inp.get("justification", "")).strip()
    if not justification:
        return "Rejected: justification required (one line, cite what you found)."
    store = PredictionStore()
    p = store.get(pred_id)
    if not p:
        return f"Rejected: no prediction {pred_id}."
    if p["category"] == "price":
        return "Rejected: price predictions auto-resolve from quotes; don't override here."
    if p["resolved"]:
        return f"Already resolved: {pred_id}."
    resolved = store.resolve(pred_id, outcome=bool(inp.get("outcome")), note=justification)
    return f"Resolved {pred_id}: outcome={resolved['outcome']} brier={resolved['brier']}. {justification}"


HANDLERS = {
    "get_journal_summary": h_summary,
    "get_recent_trades": h_recent,
    "get_risk_settings": h_risk,
    "get_lessons": h_lessons,
    "set_lessons": h_set_lessons,
    "propose_risk_change": h_propose_risk_change,
    "get_pending_predictions": h_pending_predictions,
    "resolve_prediction": h_resolve_prediction,
    "get_ungraded_trades": h_ungraded_trades,
    "grade_trade": h_grade_trade,
    "get_ungraded_debates": h_ungraded_debates,
    "grade_debate": h_grade_debate,
    "get_shadow_stats": h_shadow_stats,
    "update_beliefs": h_update_beliefs,
}


# ------------------------------ deploy + run ---------------------------------
def deploy_reflect() -> str:
    state = load_state()
    agent_id = state.get(AGENT_ID_KEY)
    if agent_id:
        if state.get(AGENT_SPEC_KEY) != SPEC_VERSION:
            cur = client().beta.agents.retrieve(agent_id)
            client().beta.agents.update(agent_id, version=cur.version, model=MODEL,
                                        system=SYSTEM, tools=TOOLS)
            state[AGENT_SPEC_KEY] = SPEC_VERSION
            save_state(state)
            print(f"[deploy] updated reflect agent {agent_id}")
        else:
            print(f"[deploy] reflect agent already hosted: {agent_id}")
        return agent_id
    agent = client().beta.agents.create(name="SPY Reflection Reviewer", model=MODEL,
                                        system=SYSTEM, tools=TOOLS)
    state[AGENT_ID_KEY] = agent.id
    state[AGENT_SPEC_KEY] = SPEC_VERSION
    save_state(state)
    print(f"[deploy] hosted new reflect agent on CMA: {agent.id} (v{agent.version})")
    return agent.id


def run_reflection(agent_id: str) -> None:
    env_id = get_or_create_environment()
    vault_id = get_or_create_vault()
    ensure_robinhood_credential(vault_id)
    session = client().beta.sessions.create(agent=agent_id, environment_id=env_id,
                                            vault_ids=[vault_id], title="reflection")
    print(f"[reflect] session {session.id}")
    print(f"[reflect] watch live: {console_url(session.id)}\n")

    c = client()
    pending: list = []
    with c.beta.sessions.events.stream(session_id=session.id) as stream:
        c.beta.sessions.events.send(session_id=session.id, events=[{
            "type": "user.message",
            "content": [{"type": "text", "text":
                "Reflect on my trading journal now. Update my lessons honestly, and "
                "only if the evidence is sufficient, propose one small bounded risk "
                "change (otherwise recommend no change and say why). Then check "
                "get_pending_predictions and resolve any matured non-price "
                "predictions with web_search + resolve_prediction."}],
        }])
        for event in stream:
            t = event.type
            if t == "agent.message":
                for b in event.content:
                    if b.type == "text":
                        print(b.text, end="", flush=True)
            elif t == "agent.custom_tool_use":
                pending.append(event)
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

    print("\n\n--- updated lessons ---")
    print(lessons_store.read_lessons())
    sugg = lessons_store.list_suggestions()
    if sugg:
        print("\n--- pending risk suggestions (apply via copilot if you agree) ---")
        for s in sugg:
            if s.get("status") == "suggested":
                print(f"  {s['parameter']} -> {s['value']}  ({s['rationale']})")
    report_cost(session.id, model=MODEL, label="reflection")


def main() -> None:
    agent_id = deploy_reflect()
    if len(sys.argv) > 1 and sys.argv[1] == "deploy":
        print("[reflect] deploy-only."); return
    run_reflection(agent_id)


if __name__ == "__main__":
    main()
