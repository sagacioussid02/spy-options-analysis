# SPY Trading — CMA + Robinhood MCP

This repo runs SPY trade analysis and execution through **Claude Managed Agents (CMA)** calling the official **Robinhood Trading MCP**, with a human approving every order.

## Layout

- `spy_decision_engine/` — the analysis engine (8 engines → weighted score → `reports/final_decision.json`). Required dependency of `cma_lab/`; run via `spy_decision_engine/main.py`.
- `cma_lab/` — the CMA/Robinhood MCP layer: hosted agents (`advisor.py`, `copilot.py`, `committee.py`, `reflect.py`, `scout.py`), the Robinhood MCP client + OAuth (`lab.py`), risk gating (`risk_gate.py`), the trade journal (`journal.py`), and the local approval UI (`web/app.py`).
- `openspec/` — spec proposal for the next iteration of the agentic trader (`agentic-trader-v2`).
- `docs/guides/ROBINHOOD_MCP_MIGRATION_RECOMMENDATION.md`, `docs/workflows/CLAUDE_CODE_ROBINHOOD_MCP_MIGRATION_PROMPT.md` — migration notes for the Robinhood MCP integration.

## Flow

1. `spy_decision_engine/main.py` produces `reports/final_decision.json`.
2. A hosted CMA agent (`cma_lab/advisor.py`) reads it and proposes a trade to the journal — it never holds the trigger.
3. The user reviews via `cma_lab/copilot.py`, the web UI (`cma_lab/web/app.py`), or CLI (`/pending`, `/tweak`, `/approve`, `/reject`).
4. On approval, `execute_approved()` runs the deterministic risk gate and places the order through the Robinhood Trading MCP (`lab.mcp_call_tool`).

Live execution is gated behind `SPY_LIVE=1` with a hard share ramp cap; equity-only (Robinhood hasn't enabled agentic options ordering for this account yet).
