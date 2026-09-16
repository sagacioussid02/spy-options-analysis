# Spec Delta: falsifiable-proposals

## ADDED Requirements

### Requirement: Proposal schema v2
Every trade proposal (from advisor or committee, sim or live) SHALL include:
`thesis` (one/two sentences), `kill_criteria` (pre-registered "what proves me
wrong"), `exit_plan` with `target`, `stop`, and `time_stop` (ISO date), and
`conviction` (low|medium|high). `TradeJournal` SHALL reject proposals missing
any of these fields, returning an error string the agent can read and fix.

#### Scenario: Agent omits kill criteria
- **WHEN** `propose_trade` is called without `kill_criteria`
- **THEN** the tool result is an error naming the missing field, no journal entry is created, and the agent can retry in the same session

#### Scenario: Backward compatibility
- **WHEN** `journal.json` contains v1 entries without the new fields
- **THEN** all journal reads (`recent`, `summarize`, web UI) work without crashing, treating missing fields as null

### Requirement: Thesis grading on close
When a trade closes, the system SHALL grade it on a 2x2:
`right_win | right_loss | wrong_win | wrong_loss`, where right/wrong is whether
the thesis played out (assessed by the reflection agent from `thesis`,
`kill_criteria`, and price history) and win/loss is realized P&L sign.
`summarize()` SHALL report counts per grade, and lessons SHALL treat
`wrong_win` as luck (not edge) and `right_loss` as execution/sizing feedback
(not thesis failure).

#### Scenario: Wrong thesis, made money
- **WHEN** a closed trade's kill criteria triggered but P&L is positive
- **THEN** the entry is graded `wrong_win` and reflection output explicitly labels it as luck, not confirmation of the strategy

### Requirement: Shadow trades on pass (regret tracking)
When the committee PM explicitly passes on trading, the system SHALL record a
shadow entry in `cma_lab/shadow.json` with the hypothetical entry price (live
quote at pass time), direction and exit plan from the bull case, and the
`debate_id`. A deterministic sweep SHALL resolve shadow entries at their
time-stop using quote data and store hypothetical P&L.

#### Scenario: Pass becomes a scored shadow
- **WHEN** the PM calls `pass_with_reason` after a debate whose bull case proposed "buy SPY, target +1%, time-stop 5 trading days"
- **THEN** a shadow entry is created immediately, and after the time-stop the sweep marks it resolved with the hypothetical P&L

#### Scenario: Reflection reports timidity
- **WHEN** reflection runs and >=8 shadow entries are resolved
- **THEN** lessons include the pass hit-rate (e.g., "7 of 12 passes would have profited") broken down by regime
