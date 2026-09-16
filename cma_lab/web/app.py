"""
Local advisor UI backend (FastAPI).

Runs on YOUR machine (localhost) so execution + the Robinhood token stay local —
the same security posture as the terminal advisor, just with a real Approve
button. Reuses advisor.py's brains (journal, HANDLERS, execute_approved); this is
only presentation + HTTP.

Run (from the cma_lab/ dir so sibling modules import cleanly):
    cd cma_lab && ../.venv/bin/python -m uvicorn web.app:app --port 8787
    # then open http://localhost:8787
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse

import advisor  # noqa: E402  (its module-level setup: J, HANDLERS, execute_approved)
from lab import (
    client,
    ensure_robinhood_credential,
    get_or_create_environment,
    get_or_create_vault,
)
from risk_gate import load_risk_config

app = FastAPI(title="SPY Advisor")
STATIC = Path(__file__).parent / "static"
STATE: dict = {}


def ensure_session() -> str:
    """Lazily deploy the advisor + open one session the UI talks to."""
    if "session_id" not in STATE:
        agent_id = advisor.deploy_advisor()
        env_id = get_or_create_environment()
        vault_id = get_or_create_vault()
        ensure_robinhood_credential(vault_id)
        s = client().beta.sessions.create(agent=agent_id, environment_id=env_id,
                                          vault_ids=[vault_id], title="advisor UI")
        STATE["session_id"] = s.id
    return STATE["session_id"]


def web_turn(message: str) -> str:
    """Run one advisor turn, handling custom tools server-side; return the text."""
    c = client()
    sid = ensure_session()
    chunks: list[str] = []
    pending: list = []
    with c.beta.sessions.events.stream(session_id=sid) as stream:
        c.beta.sessions.events.send(session_id=sid, events=[{
            "type": "user.message", "content": [{"type": "text", "text": message}]}])
        for event in stream:
            t = event.type
            if t == "agent.message":
                for b in event.content:
                    if b.type == "text":
                        chunks.append(b.text)
            elif t == "agent.custom_tool_use":
                pending.append(event)
            elif t == "session.status_terminated":
                break
            elif t == "session.status_idle":
                stop = getattr(getattr(event, "stop_reason", None), "type", None)
                if stop == "requires_action":
                    results = []
                    for ev in pending:
                        fn = advisor.HANDLERS.get(ev.name)
                        out = fn(getattr(ev, "input", {}) or {}) if fn else f"unknown {ev.name}"
                        results.append({"type": "user.custom_tool_result",
                                        "custom_tool_use_id": ev.id,
                                        "content": [{"type": "text", "text": str(out)}]})
                    pending = []
                    if results:
                        c.beta.sessions.events.send(session_id=sid, events=results)
                    continue
                break
    return "".join(chunks).strip() or "(no reply)"


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.post("/api/chat")
async def chat(req: Request):
    body = await req.json()
    return {"reply": web_turn(str(body.get("message", "")))}


@app.get("/api/proposals")
def proposals():
    return advisor.J.pending_proposals()


@app.post("/api/approve")
async def approve(req: Request):
    body = await req.json()
    eid = body.get("id")
    pend = advisor.J.pending_proposals()
    e = advisor.J.get(eid) if eid else (pend[-1] if pend else None)
    if not e or e["status"] not in ("proposed", "approved"):
        return {"result": "no matching proposal"}
    # Live orders require a typed terminal confirmation — don't run that path
    # from the web (it would block on input()). UI drives simulated execution.
    if advisor.LIVE_EXECUTION:
        return {"result": "LIVE mode: approve live orders from the terminal advisor "
                          "(typed confirmation required). UI is for simulated runs."}
    advisor.J.approve(e["id"], note="approved via UI")
    return {"result": advisor.execute_approved(advisor.J.get(e["id"]))}


@app.post("/api/reject")
async def reject(req: Request):
    body = await req.json()
    advisor.J.reject(body["id"], note=body.get("note", ""))
    return {"ok": True}


@app.post("/api/tweak")
async def tweak(req: Request):
    body = await req.json()
    changes = {}
    if body.get("quantity") not in (None, ""):
        changes["quantity"] = float(body["quantity"])
    if body.get("limit_price") not in (None, ""):
        changes["limit_price"] = float(body["limit_price"])
    if changes:
        advisor.J._update(body["id"], **changes)
    return {"ok": True, "changes": changes}


@app.get("/api/journal")
def journal():
    return advisor.J.recent(25)


@app.get("/api/risk")
def risk():
    c = load_risk_config()
    return {
        "max_shares": c.max_quantity,
        "notional_cap": c.max_notional_per_order,
        "kill_switch": c.kill_switch,
        "equity_only": c.equity_only,
        "live": advisor.LIVE_EXECUTION,
    }
