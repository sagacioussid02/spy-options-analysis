# SPY Trading — CMA + Robinhood MCP

This repo runs multi-ticker analysis through **Claude Managed Agents (CMA)** and the official **Robinhood Trading MCP**. The scheduled prototype is simulation-only; live execution is a separate, explicitly gated capability.

## Layout

- `spy_decision_engine/` — the analysis engine (8 engines → weighted score → `reports/final_decision.json`). Required dependency of `cma_lab/`; run via `spy_decision_engine/main.py`.
- `cma_lab/` — the CMA/Robinhood MCP layer: hosted agents (`advisor.py`, `copilot.py`, `committee.py`, `reflect.py`, `scout.py`), the Robinhood MCP client + OAuth (`lab.py`), risk gating (`risk_gate.py`), the trade journal (`journal.py`), and the local approval UI (`web/app.py`).
- `openspec/` — spec proposal for the next iteration of the agentic trader (`agentic-trader-v2`).
- `docs/guides/ROBINHOOD_MCP_MIGRATION_RECOMMENDATION.md`, `docs/workflows/CLAUDE_CODE_ROBINHOOD_MCP_MIGRATION_PROMPT.md` — migration notes for the Robinhood MCP integration.

## Flow

1. `spy_decision_engine/main.py` produces `reports/final_decision.json`.
2. A hosted CMA agent (`cma_lab/advisor.py`) reads it and proposes a trade to the journal — it never holds the trigger.
3. The committee records a proposal or pass. Scheduled runs force proposals into the simulation lane and never submit live orders.
4. In the interactive live path, approval and `SPY_LIVE=1` are required; execution runs the deterministic risk gate before calling Robinhood MCP.

## Scheduled Prototype

`cma_lab/run_basket.sh` refreshes analysis, runs one committee debate per basket ticker, and sweeps simulated positions. The LaunchAgent is `cma_lab/launchd/com.sidd.spy.basket.plist`; it runs weekdays at 07:40 local time when installed and the Mac is awake. It sets `SPY_SIM_ONLY=1`, which downgrades live-tagged proposals to simulation and skips live positions in the sweep.

This is suitable for demonstrating the decision loop, not for unattended real-money execution. Before enabling live automation, broker order acceptance/fill reconciliation and alerting must be implemented; a successful place-order response is not proof of a fill. Equity-only; options orders remain disabled.

## Sutra MCP Server

This repository includes a local stdio MCP server at `cma_lab/mcp_server.py`.
It exposes read-only desk and broker status, plus a staged
`analyze_trade_request` → `get_trade_analysis_details` → `execute_confirmed_trade`
workflow. Analysis and backtest results are cached; the initial wait is capped
at two minutes. The analyst never places an order. Execution is a separate,
explicitly confirmed action guarded by existing risk checks; it is sim-only when
`SPY_LIVE` is not armed. Raw broker order tools are not exposed. See
[docs/guides/SPY_DESK_MCP.md](docs/guides/SPY_DESK_MCP.md) for Sutra setup and
the complete tool contract.
