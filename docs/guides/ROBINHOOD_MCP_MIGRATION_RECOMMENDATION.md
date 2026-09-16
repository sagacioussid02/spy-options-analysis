# Robinhood MCP Migration Recommendation

Date: 2026-06-07

## Executive Summary

You should move to a broker-execution architecture where Robinhood MCP is the only execution path, while your existing SPY analysis engines continue to generate signals, sizing, and risk controls.

Key recommendation:
- Keep analysis and scoring in your local engine.
- Replace manual trade recording and any paper-trading assumptions with broker-sourced order and fill events via Robinhood MCP.
- Introduce dedicated agents for order intent, risk validation, execution, and reconciliation.
- Cut over in phases with hard safety gates and a rollback path.

This gives you real execution without losing the strengths of your current modular design.

## Current State (From This Repo)

Your project is currently human-in-the-loop and analysis-first:
- Decision orchestration is in spy_decision_engine/main.py.
- Final recommendation logic is in spy_decision_engine/engines/final_decision.py.
- Trades are manually recorded through trade_cmd.py and persisted in local JSON/SQLite.
- Monitoring and analytics are local (trade_monitor.py, db_query.py, DecisionDatabase).

There is no direct Alpaca integration currently in this codebase, so this is effectively a migration from manual/paper workflow to live broker execution through MCP.

## Target Architecture

Use Robinhood MCP as a broker adapter layer and keep strategy logic broker-agnostic.

Flow:
1. Strategy engine produces a TradeIntent.
2. Risk agent validates limits and account state.
3. Execution agent sends orders through Robinhood MCP tools.
4. Reconciliation agent ingests fills/positions from Robinhood MCP and updates local database.
5. Monitoring agent tracks open risk, stop conditions, and exit signals.

Core principle:
- Your engine decides what to trade.
- Robinhood MCP is the only component that decides how to place/cancel/replace at broker level.

## Recommended Agent Topology

Create these dedicated agents:

1. Signal Agent
- Inputs: context reports, momentum, sentiment, volatility, options what-if.
- Output: normalized TradeIntent object.
- No broker calls.

2. Risk Gate Agent
- Inputs: TradeIntent + account/position state from Robinhood MCP.
- Enforces limits: max daily loss, max contracts, max open positions, symbol whitelist, allowed DTE window.
- Emits Approve or Reject with explicit reason.

3. Execution Agent (Robinhood-only)
- Converts approved TradeIntent to Robinhood MCP order requests.
- Places, amends, cancels orders.
- Handles retries/idempotency with client_order_id keys.

4. Reconciliation Agent
- Pulls orders, fills, positions, buying power from Robinhood MCP.
- Upserts broker truth into local DB.
- Resolves drift between local state and broker state.

5. Exit/Protection Agent
- Continuously evaluates stop, take-profit, time-based exits.
- Places protective exits through Robinhood MCP.

6. Audit Agent
- Creates immutable action log records with intent, risk checks, submitted order payload, broker response, and final fill summary.

## Domain Model Changes

Introduce a canonical TradeIntent and BrokerOrder model before wiring MCP tools.

TradeIntent fields:
- intent_id
- strategy_name
- underlying
- side
- option_type
- strike
- expiry
- quantity
- entry_style (market/limit)
- limit_price (optional)
- stop_policy
- tp_policy
- confidence
- generated_at

BrokerOrder fields:
- intent_id
- broker
- broker_order_id
- status
- submitted_at
- avg_fill_price
- filled_quantity
- fees
- raw_broker_payload

Why this matters:
- Keeps your strategy independent of any one broker.
- Makes future multi-broker support possible without rewriting engines.

## Phased Migration Plan

### Phase 0: Capability Discovery (1 day)
- Enumerate Robinhood MCP tool capabilities and limits (orders, options chains, positions, account, order status, cancel/replace).
- Map each needed operation to a concrete MCP tool call.
- Identify gaps early.

Exit criteria:
- A capability matrix exists and all critical actions have a mapped MCP tool.

### Phase 1: Broker Adapter + Shadow Mode (2-3 days)
- Build a RobinhoodBrokerAdapter around MCP calls.
- Add dry_run=True mode that performs all risk/execution logic but does not submit live orders.
- Keep existing trade_cmd.py flow for actual state changes.

Exit criteria:
- For each TradeIntent, adapter can produce valid order payload previews.

### Phase 2: Paper-to-Live Bridge (2-4 days)
- Enable live submission for tiny size only (for example 1 contract).
- Reconciliation agent becomes source of truth for order lifecycle states.
- Keep manual emergency stop as a hard switch.

Exit criteria:
- End-to-end: intent -> approved -> submitted -> filled/canceled -> reconciled.

### Phase 3: Full Cutover (1-2 days)
- Disable manual add/close as primary execution path.
- trade_cmd.py becomes operator tooling for overrides and post-trade notes only.
- Dashboard and db_query read broker-synced records.

Exit criteria:
- 100 percent of new trades originate via Robinhood MCP.

### Phase 4: Optimization and Automation (ongoing)
- Add smart order tactics (staged limits, timed re-price, partial profit ladder).
- Add event-driven exits and session-aware risk behavior.
- Add richer attribution by strategy regime.

## Safety Controls Required Before Full Live Trading

Non-negotiable controls:
- Global kill switch (single env/config flag checked before every submit).
- Max daily loss lockout.
- Max open risk per symbol.
- Notional and quantity caps.
- Idempotency keys on every order submission.
- Cooldown window after reject/failure storms.
- Mandatory reconciliation before placing new orders.
- Alerting for rejected orders, stale open orders, and orphaned positions.

## Suggested File-Level Refactor in This Repo

Add new modules:
- spy_decision_engine/broker/robinhood_mcp_adapter.py
- spy_decision_engine/agents/risk_gate_agent.py
- spy_decision_engine/agents/execution_agent.py
- spy_decision_engine/agents/reconciliation_agent.py
- spy_decision_engine/agents/exit_agent.py
- spy_decision_engine/models/trade_intent.py
- spy_decision_engine/models/broker_order.py

Modify existing modules:
- spy_decision_engine/main.py: emit TradeIntent and route through risk/execution/reconciliation pipeline.
- spy_decision_engine/database.py: add broker_orders and order_events tables.
- trade_cmd.py: convert from primary recorder to operator control surface.
- trade_monitor.py: read broker-backed position/order truth.

## What Exciting Things You Can Do Now

Once Robinhood MCP is integrated, you can unlock:

1. True closed-loop trading
- Signal -> risk check -> order -> fill -> feedback, fully automated with guardrails.

2. Real execution quality analytics
- Measure slippage, fill latency, reject reasons, and outcome by order tactic.

3. Strategy-aware execution
- Different entry tactics by confidence regime (high confidence = faster fill, medium confidence = patient limits).

4. Adaptive position sizing
- Size by live buying power, current open risk, and recent realized volatility.

5. Portfolio-level intelligence
- Multi-position risk limits, correlation-aware exposure caps, and rolling drawdown protection.

6. Event-driven playbooks
- Automatically alter exit behavior around macro events and earnings windows.

7. Better post-trade learning
- Attribute PnL to signal quality vs execution quality vs market regime.

8. Semi-autonomous operator mode
- Agents propose, validate, and execute; you supervise with approval thresholds.

## Rollout Recommendation

Best rollout sequence:
1. Build adapter and risk gate first.
2. Run shadow mode for several sessions.
3. Turn on micro-size live trades only.
4. Promote to normal sizing after reconciliation stability and risk metrics pass.

If you do only one thing first, do this:
- Implement a strict Risk Gate Agent and broker reconciliation loop before scaling live order volume.

## Practical Next Build Steps

Immediate next implementation steps:
1. Add TradeIntent and BrokerOrder models.
2. Add RobinhoodBrokerAdapter interface and dry-run implementation.
3. Extend database schema for broker order lifecycle.
4. Wire main.py to produce intent and call risk/execution pipeline.
5. Add end-to-end integration test that simulates submit/fill/reconcile.

---

This architecture keeps your existing edge (signal generation and analytics) while safely upgrading to real broker execution through Robinhood MCP.
