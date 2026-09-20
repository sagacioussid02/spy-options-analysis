"""
Investment committee — bull, bear, and PM as SEPARATE hosted CMA sessions.

The point of separate sessions (not one agent role-playing three parts): the
bear must argue against a case it didn't write, in a context that doesn't
already agree with it. That's what makes disagreement real instead of
self-confirming.

Flow: Bull gathers evidence and submits a case -> Bear receives the FULL bull
case and rebuts (or proposes an alternative) -> PM receives both cases plus
desk-activity and regret stats, and either proposes a trade (sim lane
auto-executes; live lane queues for human approval via advisor.py) or passes
(which is itself recorded and later graded, so timidity is measurable).

Every run is persisted to cma_lab/debates/<id>.json. Journal/shadow entries
carry the debate_id so reflection can later ask "did the bear call this?".

Stance carried through from openspec/changes/agentic-trader-v2/design.md: the
engine's score is EVIDENCE the personas weigh, never a checklist they must
satisfy. Uncertainty should shrink size, not force a pass.

Run:
    .venv/bin/python cma_lab/committee.py           # one debate
    .venv/bin/python cma_lab/committee.py --once    # same (explicit)
    .venv/bin/python cma_lab/committee.py deploy    # (re)deploy the 3 personas only
"""
from __future__ import annotations

import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from advisor import (
    STRATEGIES,
    h_engine,
    h_lessons,
    h_recent,
    h_risk,
    h_standing,
    h_summary,
)
from chunk6_read_agent import READ_TOOLS
import exploration
from execution import J, execute_autonomous, execute_sim, h_propose
from futurist import theses_index_text
from playbook import Playbook
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
from shadow import ShadowStore
from store import store

REPO_ROOT = Path(__file__).resolve().parent.parent
MODEL = "claude-haiku-4-5"          # personas run cheap; reflect/futurist run Sonnet later

# ------------------------------ beliefs (persistent, per-persona) ------------
SEED_BELIEFS = {
    "bull": "# Bull beliefs\n\nStart neutral: uptrends tend to persist longer than "
            "the tape 'feels' safe to buy into, and sentiment tends to lag price. "
            "No regime-specific priors yet — this file should only be updated from "
            "graded evidence (see reflect.py), not vibes.\n",
    "bear": "# Bear beliefs\n\nStart neutral: mean reversion is underrated right "
            "after a sharp rip, and conviction is often highest just before it's "
            "wrong. No regime-specific priors yet — update only from graded "
            "evidence.\n",
    "pm": "# PM beliefs\n\nStart neutral: weigh bull vs bear by track record, not "
          "by who argues more confidently. Size to conviction; uncertainty means "
          "smaller, not zero. No regime-specific priors yet.\n",
}


def _read_beliefs(persona: str) -> str:
    beliefs = store().load("beliefs", {}) or {}
    if persona not in beliefs:
        beliefs[persona] = SEED_BELIEFS.get(persona, f"# {persona} beliefs\n\n(no notes yet)\n")
        store().save("beliefs", beliefs)
    text = beliefs[persona]
    words = text.split()
    return text if len(words) <= 3000 else " ".join(words[-3000:])


# ------------------------------ debates (collection "debates") ---------------
def load_debates() -> list[dict]:
    """All recorded debates, oldest first (by created_at)."""
    docs = store().load("debates", {}) or {}
    return sorted(docs.values(), key=lambda d: d.get("created_at", ""))


def save_debate(debate: dict) -> None:
    docs = store().load("debates", {}) or {}
    docs[debate["id"]] = debate
    store().save("debates", docs)


# ------------------------------ desk-activity nudge (task 3.5) ---------------
def _activity_status() -> str:
    recent = load_debates()[-5:]
    proposed = sum(1 for d in recent
                   if (d.get("pm_decision") or {}).get("decision") == "propose")
    if len(recent) >= 3 and proposed < 3:
        return (f"UNDER-TRADING: only {proposed} of the last {len(recent)} committee "
                f"sessions proposed a trade. A pass must be argued for like a "
                f"position — prefer a small, sized-down entry over silence when the "
                f"case is merely uncertain rather than bad.")
    return f"Desk activity: {proposed} of the last {len(recent)} sessions proposed a trade."


def _debate_track_record() -> str:
    """Per-persona grading tally from reflect.py's grade_debate — feeds the PM's
    calibration context on who to trust under disagreement."""
    tally = {"bull_right": 0, "bear_right": 0, "both_wrong": 0, "unclear": 0}
    n = 0
    for d in load_debates():
        g = d.get("grade")
        if g in tally:
            tally[g] += 1
            n += 1
    if n == 0:
        return "Debate track record: no graded debates yet."
    return (f"Debate track record (n={n} graded): bull_right={tally['bull_right']}, "
            f"bear_right={tally['bear_right']}, both_wrong={tally['both_wrong']}, "
            f"unclear={tally['unclear']}.")


# ------------------------------ shared read tools/handlers --------------------
def h_components(_i) -> str:
    """Individual engine component scores + raw market conditions — deliberately
    WITHOUT the blended final_score/decision, so personas reason over the
    components instead of anchoring on the verdict label."""
    path = REPO_ROOT / "spy_decision_engine" / "reports" / "final_decision.json"
    if not path.exists():
        return "(no engine report found)"
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError:
        return "(engine report unreadable)"
    view = {
        "component_scores": data.get("component_scores"),
        "market_conditions": data.get("market_conditions"),
        "entry_strategy": data.get("entry_strategy"),
    }
    return json.dumps(view, indent=2)


def h_regret(_i) -> str:
    return json.dumps(ShadowStore().summarize())


READ_CUSTOM_TOOLS = [
    {"type": "custom", "name": "get_engine_analysis",
     "description": "The decision engine's latest full analysis (final_decision.json) "
                    "for whichever ticker this session's kickoff message names.",
     "input_schema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"type": "custom", "name": "get_engine_components",
     "description": "The decision engine's INDIVIDUAL component scores and raw market "
                    "conditions for this session's ticker, without the blended verdict. "
                    "Reason from these, not from a single headline number.",
     "input_schema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"type": "custom", "name": "get_journal_summary",
     "description": "The desk's track record: win-rate and P&L by strategy, "
                    "regime, and conviction bucket, with sample counts.",
     "input_schema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"type": "custom", "name": "get_recent_trades",
     "description": "The most recent journal entries (theses, outcomes, reflections).",
     "input_schema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"type": "custom", "name": "get_lessons",
     "description": "Distilled lessons from past trades, written by reflection.",
     "input_schema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"type": "custom", "name": "get_risk_settings",
     "description": "Current effective risk settings + hard caps.",
     "input_schema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"type": "custom", "name": "get_account_standing",
     "description": "Live buying power, cash, and account value.",
     "input_schema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"type": "custom", "name": "get_regret_stats",
     "description": "Hit-rate of past committee PASSes — of the trades we didn't "
                    "take, how many would have profited. Use this to calibrate "
                    "whether the desk is too timid.",
     "input_schema": {"type": "object", "properties": {}, "additionalProperties": False}},
]

READ_HANDLERS = {
    "get_engine_analysis": h_engine,
    "get_engine_components": h_components,
    "get_journal_summary": h_summary,
    "get_recent_trades": h_recent,
    "get_lessons": h_lessons,
    "get_risk_settings": h_risk,
    "get_account_standing": h_standing,
    "get_regret_stats": h_regret,
}

_EXIT_PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "target": {"type": "number", "description": "take-profit price"},
        "stop": {"type": "number", "description": "stop-loss price"},
        "time_stop": {"type": "string", "description": "ISO date to exit by regardless"},
    },
    "required": ["target", "stop", "time_stop"],
    "additionalProperties": False,
}

SUBMIT_CASE_TOOL = {
    "type": "custom", "name": "submit_case",
    "description": "Submit your structured case once you've gathered context. "
                   "Call this exactly once, as your final action.",
    "input_schema": {
        "type": "object",
        "properties": {
            "stance": {"type": "string", "description": "'bull' or 'bear'"},
            "thesis": {"type": "string", "description": "1-3 sentences, concrete "
                       "and falsifiable — not a vibe."},
            "key_evidence": {"type": "array", "items": {"type": "string"},
                             "description": "2-4 specific data points that matter most."},
            "suggested_trade": {
                "type": "object",
                "description": "The trade that fits your read — even a bear case "
                               "should specify one (it can be a stand-aside/no "
                               "position with side='none').",
                "properties": {
                    "side": {"type": "string", "description": "buy | none"},
                    "symbol": {"type": "string"},
                    "quantity": {"type": "number"},
                    "entry_style": {"type": "string", "description": "limit or market"},
                    "limit_price": {"type": "number"},
                    "exit_plan": _EXIT_PLAN_SCHEMA,
                },
                "required": ["side", "symbol", "quantity", "entry_style", "exit_plan"],
                "additionalProperties": False,
            },
            "confidence": {"type": "number", "description": "0..1, calibrated — "
                          "don't inflate it to sound persuasive."},
        },
        "required": ["stance", "thesis", "key_evidence", "suggested_trade", "confidence"],
        "additionalProperties": False,
    },
}

PROPOSE_TOOL = {
    "type": "custom", "name": "propose_trade",
    "description": "Record a trade proposal. mode='sim' executes immediately in "
                   "the autonomous simulation lane (no human step); mode='live' "
                   "queues it for human approval via advisor.py. Every proposal "
                   "must be falsifiable: kill_criteria + a full exit_plan.",
    "input_schema": {
        "type": "object",
        "properties": {
            "thesis": {"type": "string"},
            "conviction": {"type": "number", "description": "0..1"},
            "regime": {"type": "string"},
            "strategy": {"type": "string", "description": f"one of: {STRATEGIES}"},
            "side": {"type": "string"},
            "symbol": {"type": "string"},
            "quantity": {"type": "number"},
            "entry_style": {"type": "string"},
            "limit_price": {"type": "number"},
            "kill_criteria": {"type": "string", "description": "What specific price "
                              "action or event would prove this thesis wrong?"},
            "exit_plan": _EXIT_PLAN_SCHEMA,
            "mode": {"type": "string", "description": "'sim' (default, autonomous) "
                     "or 'live' (queues for human approval)"},
            "hypothesis_id": {"type": "string", "description": "If this trade comes "
                     "from a registered playbook hypothesis, its id — links the "
                     "outcome back to that hypothesis's trial stats. Trial-status "
                     "hypotheses are sim-only regardless of the mode you set here."},
            "origin_reason": {"type": "string", "description": "Why this proposal, "
                      "honestly: 'engine_aligned' (evidence lines up with the "
                      "engine's blended lean), 'against_engine' (you're going "
                      "against it), 'hunch' (a gut call not fully backed by either "
                      "case), or 'untested_playbook' (from a trial-status "
                      "hypothesis). This is how the desk learns whether off-book "
                      "instinct has edge — don't mark engine_aligned just to look "
                      "more rigorous than you are."},
        },
        "required": ["thesis", "conviction", "side", "symbol", "quantity", "entry_style",
                     "kill_criteria", "exit_plan", "origin_reason"],
        "additionalProperties": False,
    },
}

REGISTER_HYPOTHESIS_TOOL = {
    "type": "custom", "name": "register_hypothesis",
    "description": "Register a new named strategy idea to trial in the sim lane "
                   "— \"let's try this way!\" Deduped by name: registering an "
                   "existing idea returns it unchanged instead of duplicating it. "
                   "It starts in 'trial' status (sim-only) and graduates to "
                   "'active' (live-eligible) or 'retired' automatically, by a "
                   "fixed rule, once it has enough trials — never by a model's "
                   "say-so.",
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Short name, e.g. 'fade-friday-strength'."},
            "rule": {"type": "string", "description": "Plain-English entry/exit rule."},
            "rationale": {"type": "string", "description": "Why you think this has edge."},
            "min_trials": {"type": "number", "description": "Trials needed before "
                          "graduation/retirement is evaluated (default 10)."},
        },
        "required": ["name", "rule", "rationale"],
        "additionalProperties": False,
    },
}


def make_h_register_hypothesis(persona: str):
    def _h(inp: dict) -> str:
        h = Playbook().register(
            name=str(inp.get("name", "")).strip(),
            rule=str(inp.get("rule", "")).strip(),
            rationale=str(inp.get("rationale", "")).strip(),
            proposed_by=persona,
            min_trials=int(inp.get("min_trials", 10) or 10),
        )
        return f"Hypothesis registered: {h['name']} (id={h['id']}, status={h['status']})."
    return _h


LOG_PREDICTION_TOOL = {
    "type": "custom", "name": "log_prediction",
    "description": "Log a falsifiable probabilistic forecast — cheap, and it "
                   "builds your calibration track record even in sessions with "
                   "no trade. Must be measurable and resolvable by horizon_date; "
                   "vague claims are rejected. Log at least one per session.",
    "input_schema": {
        "type": "object",
        "properties": {
            "claim": {"type": "string", "description": "A specific, falsifiable statement."},
            "probability": {"type": "number", "description": "0.05-0.95, calibrated "
                            "— don't default to 0.5 or 0.9 out of habit."},
            "category": {"type": "string", "description": "price | macro | industry | stock"},
            "horizon_date": {"type": "string", "description": "ISO date this "
                            "resolves by, e.g. 2026-07-31"},
            "basis": {"type": "string", "description": "Why you believe this."},
            "symbol": {"type": "string", "description": "REQUIRED for category="
                      "price — the ticker, so it can auto-resolve from quotes."},
            "level": {"type": "number", "description": "REQUIRED for category=price "
                     "— the price level."},
            "direction": {"type": "string", "description": "REQUIRED for category="
                         "price — 'above' or 'below' the level."},
        },
        "required": ["claim", "probability", "category", "horizon_date", "basis"],
        "additionalProperties": False,
    },
}


def make_h_log_prediction(persona: str, debate_id: Optional[str] = None):
    def _h(inp: dict) -> str:
        from predictions import PredictionStore, PredictionValidationError
        try:
            p = PredictionStore().log(persona=persona, debate_id=debate_id, **inp)
        except PredictionValidationError as ex:
            return f"Prediction rejected: {ex} Fix it and call log_prediction again."
        return (f"Prediction logged: {p['id']} ({p['category']}, "
                f"p={p['probability']:.2f}, resolves {p['horizon_date']}).")
    return _h


def _calibration_text() -> str:
    from predictions import PredictionStore
    table = PredictionStore().calibration_table()
    if not table:
        return ("Calibration table: no resolved predictions yet — not meaningful "
                "until several predictions mature and resolve.")
    lines = ["Calibration (mean Brier score per persona x category, lower is "
            "better; treat with caution until n is meaningful):"]
    for persona, cats in table.items():
        parts = ", ".join(f"{cat} {stats['mean_brier']} (n={stats['n']})"
                          for cat, stats in cats.items())
        lines.append(f"  {persona}: {parts}")
    return "\n".join(lines)


PASS_TOOL = {
    "type": "custom", "name": "pass_with_reason",
    "description": "Decide NOT to trade this session. Must be argued for like a "
                   "position: say specifically what makes THIS case neutral right "
                   "now, not just 'not sure'. This is still recorded and graded "
                   "later against what actually happened.",
    "input_schema": {
        "type": "object",
        "properties": {"reason": {"type": "string"}},
        "required": ["reason"],
        "additionalProperties": False,
    },
}

MCP_SERVERS = [{"type": "url", "name": "robinhood", "url": ROBINHOOD_MCP_URL}]


def _read_toolset():
    return {"type": "mcp_toolset", "mcp_server_name": "robinhood",
            "default_config": {"enabled": False, "permission_policy": {"type": "always_allow"}},
            "configs": [{"name": n, "enabled": True} for n in READ_TOOLS]}


def _web_toolset():
    return {"type": "agent_toolset_20260401", "default_config": {"enabled": False},
            "configs": [{"name": "web_search", "enabled": True}, {"name": "web_fetch", "enabled": True}]}


BULL_TOOLS = [_read_toolset(), _web_toolset(), *READ_CUSTOM_TOOLS,
             SUBMIT_CASE_TOOL, REGISTER_HYPOTHESIS_TOOL, LOG_PREDICTION_TOOL]
BEAR_TOOLS = [_read_toolset(), _web_toolset(), *READ_CUSTOM_TOOLS,
             SUBMIT_CASE_TOOL, REGISTER_HYPOTHESIS_TOOL, LOG_PREDICTION_TOOL]
PM_TOOLS = [_read_toolset(), _web_toolset(), *READ_CUSTOM_TOOLS,
           PROPOSE_TOOL, PASS_TOOL, REGISTER_HYPOTHESIS_TOOL, LOG_PREDICTION_TOOL]

BULL_SYSTEM = (
    "You are the Bull analyst on this trading desk's committee. The desk "
    "trades a basket of names across sectors, not one fixed ticker — the "
    "specific ticker for this session is stated in your kickoff message, "
    "not baked into these instructions; always work off that one. Build the "
    "strongest HONEST case FOR a trade. The engine's blended verdict is "
    "EVIDENCE you weigh, never a checklist you must satisfy — you may build a "
    "case even where it's neutral or bearish, as long as you say why, using "
    "get_engine_components (the individual scores, not just the headline "
    "number), get_journal_summary, get_recent_trades, get_lessons, "
    "get_account_standing, get_risk_settings, get_regret_stats, and "
    "web_search/web_fetch for current context. Be concrete, not hedgy — a "
    "trader risking real size wouldn't submit a mushy case. If you have a "
    "genuinely new angle that isn't just 'buy the dip again', consider "
    "register_hypothesis so it can be trialed and tracked over time. Log at "
    "least one falsifiable prediction with log_prediction before you finish — "
    "predictions are cheap and build your calibration record even when the "
    "trade case is thin. When you're done, call submit_case exactly once."
)

BEAR_SYSTEM = (
    "You are the Bear analyst on this trading desk's committee. The desk "
    "trades a basket of names across sectors, not one fixed ticker — the "
    "specific ticker for this session is named in the Bull's case and the "
    "kickoff message, not baked into these instructions. You will be "
    "given the Bull's full case in your first message. Attack its strongest "
    "points with evidence (engine components, journal base rates, regret "
    "stats, web_search) — cite specifics, don't just express skepticism. If "
    "you think the Bull is largely right but sized wrong, say so. If you see a "
    "genuinely better alternative trade (including a short-term stand-aside), "
    "propose it. If you see a strategy pattern worth tracking over time, "
    "consider register_hypothesis. Log at least one falsifiable prediction "
    "with log_prediction before you finish. Gather your own evidence with "
    "your tools, then call submit_case exactly once with YOUR stance."
)

PM_SYSTEM = (
    "You are the Portfolio Manager for this desk, which trades a basket of "
    "names across sectors, not one fixed ticker — the specific ticker for "
    "this session is named in the Bull/Bear cases and the kickoff message, "
    "not baked into these instructions. You will be given the Bull case, the Bear "
    "case, this session's desk-activity status, and regret stats (whether "
    "recent passes would have profited) in your first message. Decide: "
    "propose_trade OR pass_with_reason. The engine score and either persona's "
    "confidence are EVIDENCE, not permission — a good thesis with real "
    "uncertainty should be SIZED DOWN, not skipped. Passing must be argued for "
    "like a position: what SPECIFICALLY makes this neutral right now? Always "
    "check get_account_standing and get_risk_settings and size within them. "
    "Every propose_trade call requires an honest origin_reason (engine_aligned, "
    "against_engine, hunch, or untested_playbook) — that tagging is how the "
    "desk later learns whether off-book instinct has edge; don't mark "
    "engine_aligned just to look more rigorous than you are. You'll be told "
    "the current exploration-budget status — if it says the desk is "
    "underweight on exploration, that's an invitation, not a demand. If you "
    "size a proposal from a registered playbook hypothesis, pass its "
    "hypothesis_id — trial-status hypotheses trade sim-only no matter what "
    "mode you request, until they earn live eligibility by their own track "
    "record. You'll be shown a calibration table (mean Brier score per "
    "persona) AND a debate track record (how often bull_right vs bear_right "
    "graded historically) — weight bull vs bear by both under disagreement, "
    "not by who sounds more confident. You'll also see the Futurist's theses "
    "index; a strengthening long-horizon view can support a same-day case for "
    "this session's ticker. "
    "Log at least one falsifiable prediction with "
    "log_prediction before you finish, win or pass."
)


def _deploy(name: str, model: str, system: str, tools: list,
            agent_id_key: str, agent_spec_key: str, spec_version: int) -> str:
    state = load_state()
    agent_id = state.get(agent_id_key)
    if agent_id:
        if state.get(agent_spec_key) != spec_version:
            cur = client().beta.agents.retrieve(agent_id)
            client().beta.agents.update(agent_id, version=cur.version, model=model,
                                        system=system, tools=tools, mcp_servers=MCP_SERVERS)
            state[agent_spec_key] = spec_version
            save_state(state)
            print(f"[deploy] updated {name} {agent_id} -> spec v{spec_version}")
        return agent_id
    agent = client().beta.agents.create(name=name, model=model, system=system,
                                        mcp_servers=MCP_SERVERS, tools=tools)
    state[agent_id_key] = agent.id
    state[agent_spec_key] = spec_version
    save_state(state)
    print(f"[deploy] hosted new {name} on CMA: {agent.id} (v{agent.version})")
    return agent.id


def deploy_bull() -> str:
    return _deploy("Committee — Bull", MODEL, BULL_SYSTEM, BULL_TOOLS,
                   "bull_agent_id", "bull_agent_spec", 2)


def deploy_bear() -> str:
    return _deploy("Committee — Bear", MODEL, BEAR_SYSTEM, BEAR_TOOLS,
                   "bear_agent_id", "bear_agent_spec", 2)


def deploy_pm() -> str:
    return _deploy("Committee — PM", MODEL, PM_SYSTEM, PM_TOOLS,
                   "pm_agent_id", "pm_agent_spec", 2)


# ------------------------------ PM tool wrappers (inject debate_id) ----------
def make_h_pm_propose(debate_id: str):
    def _h(inp: dict) -> str:
        inp = dict(inp)
        inp["debate_id"] = debate_id
        inp.setdefault("mode", "sim")  # committee's default; execution.py may
                                        # still downgrade live->sim internally
                                        # (low-conviction exploration) — so the
                                        # ACTUAL mode is read back below, never
                                        # assumed from this input.
        result_msg = h_propose(inp)
        if result_msg.startswith("Proposal rejected"):
            return result_msg
        matches = [e for e in J._load()
                  if e.get("debate_id") == debate_id and e["status"] == "proposed"]
        if not matches:
            return result_msg
        entry = matches[-1]
        if entry.get("mode") == "sim":
            exec_msg = execute_sim(entry)
            return result_msg + " " + exec_msg
        # live: execute_autonomous decides for itself whether this qualifies
        # (armed + under the notional/share caps) — if not, it returns an
        # explanatory message and leaves the entry status='proposed', same
        # as the old always-queue behavior.
        exec_msg = execute_autonomous(entry)
        return result_msg + " " + exec_msg
    return _h


def make_h_pass(debate_id: str, bull_case: dict):
    def _h(inp: dict) -> str:
        reason = str(inp.get("reason", "")).strip() or "no reason given"
        trade = (bull_case or {}).get("suggested_trade") or {}
        symbol = str(trade.get("symbol") or TICKER)
        side = str(trade.get("side") or "buy")
        exit_plan = trade.get("exit_plan") or {}
        quote = _quote_for(symbol)
        if quote is None or side == "none":
            ShadowStore()  # ensure file exists even with nothing to record
            return f"Passed. Reason: {reason} (no shadow recorded — no bull long/short to grade)."
        entry = ShadowStore().record_pass(debate_id=debate_id, symbol=symbol, side=side,
                                          entry_price=quote, exit_plan=exit_plan, reason=reason)
        return f"Passed — recorded as shadow {entry.id} for later grading. Reason: {reason}"
    return _h


def _quote_for(symbol: str):
    from execution import _extract_price
    from lab import mcp_call_tool
    try:
        return _extract_price(mcp_call_tool("get_equity_quotes", {"symbols": [symbol]}))
    except Exception:  # noqa: BLE001
        return None


# ------------------------------ session driver (non-interactive) -------------
def _run_session(agent_id: str, env_id: str, vault_id: str, *, title: str,
                  kickoff_text: str, handlers: dict, capture: set[str]) -> tuple[str, dict]:
    c = client()
    session = c.beta.sessions.create(agent=agent_id, environment_id=env_id,
                                     vault_ids=[vault_id], title=title)
    print(f"  session {session.id} — watch live: {console_url(session.id)}")
    captured: dict = {}
    pending: list = []
    with c.beta.sessions.events.stream(session_id=session.id) as stream:
        c.beta.sessions.events.send(
            session_id=session.id,
            events=[{"type": "user.message", "content": [{"type": "text", "text": kickoff_text}]}],
        )
        for event in stream:
            t = event.type
            if t == "agent.message":
                for b in event.content:
                    if b.type == "text":
                        print(b.text, end="", flush=True)
            elif t == "agent.custom_tool_use":
                pending.append(event)
                if event.name in capture:
                    captured[event.name] = getattr(event, "input", {}) or {}
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
                        fn = handlers.get(ev.name)
                        out = fn(getattr(ev, "input", {}) or {}) if fn else f"unknown tool {ev.name}"
                        results.append({"type": "user.custom_tool_result",
                                        "custom_tool_use_id": ev.id,
                                        "content": [{"type": "text", "text": str(out)}]})
                    pending = []
                    if results:
                        c.beta.sessions.events.send(session_id=session.id, events=results)
                    continue
                print()
                break
    report_cost(session.id, model=MODEL)
    return session.id, captured


# ------------------------------ orchestration ---------------------------------
def run_once() -> dict:
    debate_id = "deb_" + uuid.uuid4().hex[:10]
    env_id = get_or_create_environment()
    vault_id = get_or_create_vault()
    ensure_robinhood_credential(vault_id)

    bull_id = deploy_bull()
    bear_id = deploy_bear()
    pm_id = deploy_pm()

    engine_snapshot = h_engine({})
    activity = _activity_status()
    regret = h_regret({})
    playbook_view = Playbook().context_view()
    theses_view = theses_index_text()
    debate_track_record = _debate_track_record()

    print(f"\n=== committee debate {debate_id} ===")

    print("\n--- BULL ---")
    bull_kickoff = (
        f"Today's ticker: {TICKER}\n\n"
        f"Open today's {TICKER} committee debate as the Bull. Your accumulated beliefs "
        f"(weigh them, don't just recite):\n{_read_beliefs('bull')}\n\n"
        f"The current hypothesis playbook (trial/active/retired ideas the desk "
        f"is tracking):\n{playbook_view}\n\n"
        f"{theses_view}\n\n"
        "Gather context with your tools, then call submit_case with a concrete, "
        "falsifiable case."
    )
    _, bull_captured = _run_session(
        bull_id, env_id, vault_id, title=f"{debate_id}-bull", kickoff_text=bull_kickoff,
        handlers={**READ_HANDLERS, "submit_case": lambda i: "Case recorded.",
                 "register_hypothesis": make_h_register_hypothesis("bull"),
                 "log_prediction": make_h_log_prediction("bull", debate_id)},
        capture={"submit_case"})
    bull_case = bull_captured.get("submit_case", {})

    print("\n--- BEAR ---")
    bear_kickoff = (
        f"Today's ticker: {TICKER}\n\n"
        f"Your beliefs (weigh, don't just recite):\n{_read_beliefs('bear')}\n\n"
        f"The current hypothesis playbook:\n{playbook_view}\n\n"
        f"{theses_view}\n\n"
        f"Here is the Bull's full case:\n{json.dumps(bull_case, indent=2)}\n\n"
        "Attack its strongest points using your own evidence, or propose an "
        "alternative read. Then call submit_case with YOUR stance."
    )
    _, bear_captured = _run_session(
        bear_id, env_id, vault_id, title=f"{debate_id}-bear", kickoff_text=bear_kickoff,
        handlers={**READ_HANDLERS, "submit_case": lambda i: "Case recorded.",
                 "register_hypothesis": make_h_register_hypothesis("bear"),
                 "log_prediction": make_h_log_prediction("bear", debate_id)},
        capture={"submit_case"})
    bear_case = bear_captured.get("submit_case", {})

    print("\n--- PM ---")
    pm_kickoff = (
        f"Today's ticker: {TICKER}\n\n"
        f"Your beliefs (weigh, don't just recite):\n{_read_beliefs('pm')}\n\n"
        f"The current hypothesis playbook:\n{playbook_view}\n\n"
        f"{theses_view}\n\n"
        f"Bull case:\n{json.dumps(bull_case, indent=2)}\n\n"
        f"Bear case:\n{json.dumps(bear_case, indent=2)}\n\n"
        f"{activity}\n"
        f"{debate_track_record}\n"
        f"Regret stats (past passes graded against what happened): {regret}\n"
        f"{_calibration_text()}\n"
        f"{exploration.status_text()}\n\n"
        "Decide: propose_trade or pass_with_reason."
    )
    pm_handlers = {**READ_HANDLERS,
                  "propose_trade": make_h_pm_propose(debate_id),
                  "pass_with_reason": make_h_pass(debate_id, bull_case),
                  "register_hypothesis": make_h_register_hypothesis("pm"),
                  "log_prediction": make_h_log_prediction("pm", debate_id)}
    _run_session(pm_id, env_id, vault_id, title=f"{debate_id}-pm",
                kickoff_text=pm_kickoff, handlers=pm_handlers, capture=set())

    # Resolve the outcome from what was actually WRITTEN, not the model's
    # claimed intent — journal.json / shadow.json are the source of truth.
    journal_entries = [e for e in J._load() if e.get("debate_id") == debate_id]
    shadow_entries = [e for e in ShadowStore()._load() if e.get("debate_id") == debate_id]
    if journal_entries:
        pm_decision = {"decision": "propose", "journal_id": journal_entries[-1]["id"],
                      "mode": journal_entries[-1].get("mode"),
                      "status": journal_entries[-1].get("status")}
    elif shadow_entries:
        pm_decision = {"decision": "pass", "shadow_id": shadow_entries[-1]["id"]}
    else:
        pm_decision = {"decision": "unclear",
                      "note": "PM produced neither a proposal nor a pass"}

    debate = {
        "id": debate_id,
        "ticker": TICKER,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "engine_snapshot": engine_snapshot,
        "bull_case": bull_case,
        "bear_case": bear_case,
        "pm_decision": pm_decision,
    }
    save_debate(debate)
    print(f"\n=== debate {debate_id} recorded: {pm_decision['decision']} ===")
    return debate


def main() -> None:
    args = sys.argv[1:]
    if args and args[0] == "deploy":
        deploy_bull(); deploy_bear(); deploy_pm()
        print("[committee] deploy-only.")
        return
    run_once()


if __name__ == "__main__":
    main()
