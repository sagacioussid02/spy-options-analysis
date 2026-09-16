# Spec Delta: sim-autonomy

## ADDED Requirements

### Requirement: Autonomous SIM execution
Proposals tagged `mode: "sim"` SHALL execute WITHOUT human approval: risk_gate
check -> simulated fill at live quote (or limit) -> journal entry moves to
`open`. Proposals tagged `mode: "live"` SHALL keep the existing human-approval
flow unchanged (CLI /approve or web UI, typed "LIVE" confirm, env SPY_LIVE=1).

#### Scenario: Sim trade flows straight through
- **WHEN** the committee PM proposes with `mode: "sim"` and risk_gate passes
- **THEN** the trade is simulated-filled in the same run, journaled as `open` with `mode: "sim"`, and no approval prompt is created

#### Scenario: Risk gate still binds sim
- **WHEN** a sim proposal exceeds max_shares or names a non-whitelisted symbol or the kill switch is on
- **THEN** it is rejected with the risk_gate reason and journaled as `rejected`

#### Scenario: Live path untouched
- **WHEN** a proposal has `mode: "live"`
- **THEN** behavior is byte-for-byte today's advisor flow: status `proposed`, waits for human, typed confirm before any real order

### Requirement: Sim position lifecycle
The system SHALL close open sim positions deterministically: at `stop`/`target`
touch (checked against quotes during the daily sweep) or at `time_stop`,
whichever first, recording simulated P&L. Sim trades SHALL be excluded from any
report of real account state.

#### Scenario: Time-stop closes a sim trade
- **WHEN** the daily sweep runs and an open sim entry is past its time_stop
- **THEN** it is closed at the current quote, P&L computed, status `closed`, ready for thesis grading

### Requirement: Minimum desk activity
The committee SHALL run on a schedule (weekday, after the engine run) and the
system SHALL track sim proposal cadence. If fewer than 3 sim proposals were made
in the trailing 5 sessions, the PM's context SHALL include an explicit nudge that
the desk is under-trading and that acting-with-small-size is preferred to passing.

#### Scenario: Under-trading nudge
- **WHEN** the committee convenes and only 1 sim proposal exists in the last 5 sessions
- **THEN** the PM prompt includes the under-trading status and the pass rate from shadow tracking

### Requirement: Reflection weighting
`summarize()` and reflection SHALL compute edge with live trades weighted 3x
sim trades, and SHALL always display sim/live sample counts separately.

#### Scenario: Mixed sample summary
- **WHEN** the journal holds 20 sim and 2 live closed trades
- **THEN** the summary shows both counts and the weighted edge, and no lesson claims significance from live data alone
