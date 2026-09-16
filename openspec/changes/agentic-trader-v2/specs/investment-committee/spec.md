# Spec Delta: investment-committee

## ADDED Requirements

### Requirement: Three-persona committee in separate sessions
`cma_lab/committee.py` SHALL orchestrate three hosted CMA personas in SEPARATE
sessions, sequentially: Bull analyst -> Bear analyst -> Portfolio Manager (PM).
Each persona is a distinct hosted agent (own spec version key in cma_state.json,
pattern from advisor.py `deploy_advisor`). Only the PM has `propose_trade` and
`pass_with_reason` tools. Bull and Bear submit structured cases via a
`submit_case` custom tool (JSON: stance, thesis, key_evidence[], suggested_trade
{side, qty, limit, exit_plan}, confidence 0-1).

#### Scenario: Bear sees the bull case
- **WHEN** the bear session starts
- **THEN** its kickoff includes the bull's full submitted case, and its instructions require attacking the strongest points, citing evidence (engine components, journal base rates, shadow stats, web)

#### Scenario: PM is the only proposer
- **WHEN** the bull or bear session attempts to propose a trade
- **THEN** no propose tool exists in their session; proposals can only originate from the PM session

### Requirement: Personas think like traders, not checklists
Persona system prompts SHALL instruct: the engine score is evidence, not
permission; disagreement with the engine is allowed with a written thesis;
uncertainty is handled by sizing down, not by defaulting to no-trade; "no trade"
must be argued for like a position. The PM prompt SHALL include its current
exploration-budget status, calibration table, and desk activity status.

#### Scenario: Against-the-engine proposal
- **WHEN** the engine lean is neutral/bearish but the PM is persuaded by the bull case
- **THEN** the PM can propose (tagged `origin: "exploration"` if against the engine lean), and nothing in the pipeline blocks it except risk_gate (and human approval if live)

### Requirement: Debate persistence and linkage
Every committee run SHALL write `cma_lab/debates/<debate_id>.json` containing:
timestamp, engine snapshot used, bull case, bear case, PM decision + rationale,
and resulting journal/shadow id. Journal and shadow entries SHALL carry
`debate_id`. The web UI proposal card SHALL show the debate (bull/bear/PM
sections) for any proposal that has one.

#### Scenario: Traceable decision
- **WHEN** a sim trade closes as a loss
- **THEN** reflection can load its debate by `debate_id` and check whether the bear predicted the failure mode

### Requirement: Persona beliefs files
Each persona (bull, bear, pm, futurist) SHALL have a persistent
`cma_lab/beliefs/<persona>.md` injected into its session context. Reflection MAY
propose belief updates; updates are appended with a dated header so drift is
reviewable; each file is truncated to the most recent ~3000 words.

#### Scenario: Beliefs evolve from graded debates
- **WHEN** weekly reflection finds the bear was right in 4 of 5 recent debates in a high-volatility regime
- **THEN** it appends a dated note to beliefs/pm.md advising more weight on the bear in that regime, and the next PM session includes it

### Requirement: Debate grading
Weekly reflection SHALL grade resolved debates: which persona's case better
matched what happened (bull_right | bear_right | both_wrong | unclear) and
maintain per-persona debate records that feed the PM's calibration context.

#### Scenario: Grading a resolved debate
- **WHEN** reflection runs and a debate's linked trade/shadow entry has resolved
- **THEN** the debate file gains a `grade` field and the persona records are updated
