# Project Context

## Purpose
SPY options/equity trading decision engine + Claude Managed Agents (CMA) that trade
through the official Robinhood Trading MCP. The human (Sidd) is the ONLY gate before
any live order. Agents do all thinking: analysis, debate, proposals, experiments,
predictions, reflection, and learning.

## Tech Stack
- Python 3.11+, venv at `.venv/` (run scripts as `.venv/bin/python <script>`)
- Anthropic SDK (beta CMA / sessions API) — see `cma_lab/lab.py` for client, vault,
  agent deploy, session driving, and `mcp_call_tool()` (host-side Robinhood MCP calls
  with auto token refresh)
- Robinhood Trading MCP: `https://agent.robinhood.com/mcp/trading` (equity tools only;
  options rollout pending). Agentic account: env `ROBINHOOD_ACCOUNT_NUMBER`.
- Local analysis engine: `spy_decision_engine/` (8 engines -> 6 component scores ->
  weighted avg in `spy_decision_engine/utils/scoring.py`)
- Local approval UI: `cma_lab/web/app.py` (FastAPI) + `cma_lab/web/static/index.html`
- Storage: flat JSON files in `cma_lab/` (journal.json, radar.json, risk_overrides.json,
  cma_state.json), all gitignored where they contain account data

## Existing agent system (cma_lab/) — build ON this, do not rewrite
- `lab.py` — shared plumbing: `client()`, `get_or_create_environment/vault/agent`,
  `drive_session_with_approval`, `mcp_call_tool`, `account_standing()`, cost reporting
- `advisor.py` — hosted advisor agent; custom tool `propose_trade` writes a 'proposed'
  journal entry; CLI loop with /pending /tweak /approve /reject; `execute_approved()`
  runs `risk_gate` then executes (simulated fills unless env `SPY_LIVE=1`)
- `journal.py` — `TradeJournal` -> `journal.json`; thesis/conviction/regime/strategy/
  outcome/reflection; `summarize()` returns edge by strategy/regime/conviction with
  sample counts
- `reflect.py` — hosted reflection agent; reads journal summary -> writes
  `cma_lab/lessons.md` + bounded risk suggestions (`lessons.py` store)
- `risk_gate.py` — deterministic `RiskConfig` (kill_switch, equity_only, SPY whitelist,
  long-only, max_shares hard cap 10, HARD_MAX_NOTIONAL $5000); runs BEFORE human
  approval; overrides persist in `risk_overrides.json` via `load_risk_config()`
- `scout.py` — hosted "Sector Radar Scout"; catalyst-chain sweep -> `radar.json` +
  Robinhood "Radar" watchlist
- `copilot.py`, `decision_view.py`, `chunk*.py` — chat, cross-check, learning scaffold

## Conventions
- Hosted agents are versioned by a `SPEC_VERSION` int + `*_agent_spec` key in
  `cma_state.json`; bump the version to redeploy (see `advisor.py:deploy_advisor`)
- Custom tools = host-side Python handlers registered per-session (see advisor.py
  `CUSTOM_TOOLS` + `h_*` handler functions pattern)
- Money-touching code is DETERMINISTIC host-side Python; LLMs never hold the trigger
- New JSON stores: small module with a class wrapping load/save (see `journal.py`)
- Keep files under ~500 lines; prefer new module over growing an existing one

## Non-negotiable guardrails (NEVER weaken in any change)
- `risk_gate` runs before every execution, sim or live
- Live orders require: env `SPY_LIVE=1` + human approval + terminal typed "LIVE" confirm
- Policy-locked: equity_only, SPY-only live whitelist, long-only, hard caps
- Kill switch honored everywhere
- Freedom/experimentation happens UPSTREAM of the gate (sim lane, debate, research)
