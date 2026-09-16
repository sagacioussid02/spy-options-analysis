# Claude Code Prompt: Robinhood MCP Migration (Live Trading)

Date: 2026-06-07
Project: SPY decision engine

## Goal
Migrate this repo from manual or paper-like trade recording to real broker execution using Robinhood MCP as the only execution path.

Important architecture rule:
- Strategy and signal generation stay broker-agnostic.
- Robinhood MCP handles all order placement, cancel, replace, and broker state retrieval.

## Current Codebase Context
Use these files as the current baseline:
- spy_decision_engine/main.py
- spy_decision_engine/engines/final_decision.py
- trade_cmd.py
- trade_monitor.py
- spy_decision_engine/database.py

Notes:
- There is no active Alpaca integration in this repo.
- The system is currently analysis-first with manual trade recording.

## What To Build

### 1) Domain Models
Add canonical models:
- spy_decision_engine/models/trade_intent.py
- spy_decision_engine/models/broker_order.py

TradeIntent fields:
- intent_id
- strategy_name
- underlying
- side
- option_type
- strike
- expiry
- quantity
- entry_style
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

### 2) Broker Adapter Layer
Add:
- spy_decision_engine/broker/robinhood_mcp_adapter.py

Requirements:
- Single interface for submit_order, cancel_order, replace_order, get_order, list_open_orders, list_positions, get_account.
- Support dry_run mode for safe shadow testing.
- Every submission must use idempotency keys.
- Normalize Robinhood MCP responses into BrokerOrder.

### 3) Dedicated Agents
Add:
- spy_decision_engine/agents/risk_gate_agent.py
- spy_decision_engine/agents/execution_agent.py
- spy_decision_engine/agents/reconciliation_agent.py
- spy_decision_engine/agents/exit_agent.py

Responsibilities:
- Risk gate validates limits and account constraints before execution.
- Execution agent translates approved TradeIntent to Robinhood MCP requests.
- Reconciliation agent syncs broker truth into local DB.
- Exit agent handles stop, target, and time-based exits.

### 4) Database Schema Upgrade
Extend spy_decision_engine/database.py with tables:
- broker_orders
- order_events

Minimum columns:
- broker_orders: intent_id, broker_order_id, status, submitted_at, avg_fill_price, filled_qty, raw_payload
- order_events: broker_order_id, event_type, event_time, payload

Also add helper methods:
- upsert_broker_order(...)
- append_order_event(...)
- get_broker_order_by_intent(...)
- reconcile_open_positions(...)

### 5) Main Orchestration Integration
Modify spy_decision_engine/main.py to:
1. Run existing analysis engines unchanged.
2. Build TradeIntent from final decision output.
3. Run RiskGateAgent.
4. If approved, run ExecutionAgent (Robinhood MCP only).
5. Run ReconciliationAgent.
6. Persist all states and events.

### 6) CLI and Monitoring Adjustments
Update:
- trade_cmd.py
- trade_monitor.py

Changes:
- trade_cmd.py should become operator tooling, not primary source of truth for fills.
- trade_monitor.py should use broker-synced positions and orders from DB.

## Safety Controls (Must-Have)
Implement all of these before enabling full live mode:
- Global kill switch.
- Max daily loss lockout.
- Max contracts per trade.
- Max open positions.
- Symbol whitelist.
- Required reconciliation pass before new order submit.
- Cooldown after repeated failures.

## Implementation Phases

### Phase 0: Capability Mapping
- Enumerate available Robinhood MCP tool calls needed for options and account operations.
- Produce a capability matrix and identify gaps.

### Phase 1: Shadow Mode
- End-to-end pipeline in dry_run mode.
- No live orders, but full intent-risk-execution-reconcile flow.

### Phase 2: Micro Live
- Enable live for minimum size only.
- Validate lifecycle coverage: submitted -> filled or canceled -> reconciled.

### Phase 3: Full Cutover
- Robinhood MCP is the only execution path.
- Manual trade add or close no longer drives canonical state.

## Acceptance Criteria
- Every trade attempt has intent, risk decision, execution record, and reconciliation record.
- No order submits when kill switch is active.
- Duplicate submits are prevented via idempotency keys.
- DB reflects broker truth after reconciliation.
- Existing analysis outputs and final decision reports remain unchanged.

## Deliverables
1. New models, adapter, and agents files.
2. Updated main orchestration.
3. Updated database schema and migration logic.
4. Updated CLI and monitoring behavior.
5. Integration test covering intent -> approval -> execution -> reconciliation.
6. Short migration notes in docs.

## Constraints
- Do not remove existing analysis engines.
- Keep changes incremental and testable.
- Prefer explicit logs for each state transition.
- Do not hardcode secrets.

## Nice-To-Have After Cutover
- Slippage and fill-latency analytics.
- Execution tactics by confidence bucket.
- Event-driven exits around macro catalysts.
- Portfolio-level risk controls across open positions.
