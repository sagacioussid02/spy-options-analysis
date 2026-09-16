# Spec Delta: exploration-budget

## ADDED Requirements

### Requirement: Exploration quota
`cma_lab/exploration.py` SHALL maintain a rolling exploration budget over the
last 20 sim proposals with target epsilon 0.25 (configurable in
risk_overrides.json, hard range 0.10–0.40). A proposal counts as exploration
when `origin: "exploration"`, defined as: against the engine lean, OR from a
playbook hypothesis in `trial` status, OR a declared gut call (`basis: "hunch"`
with a written hunch). The PM's session context SHALL always include current
budget status ("4/20 recent = 20%, target 25% — you may explore").

#### Scenario: Under budget nudges exploration
- **WHEN** exploration share is below epsilon at committee time
- **THEN** the PM context says exploration is underweight and invites a "let's try this way" proposal from the playbook or a hunch

#### Scenario: Over budget nudges discipline
- **WHEN** exploration share exceeds epsilon by more than 0.10
- **THEN** the PM context says to prefer evidence-backed proposals this session

### Requirement: Exploration is sim-first and size-capped live
Exploration trades SHALL be unrestricted in the sim lane (beyond risk_gate).
A LIVE proposal tagged exploration SHALL additionally require conviction high
and SHALL be size-capped to the conservative preset regardless of current risk
appetite. (Human approval still applies to all live trades.)

#### Scenario: Live gut call gets minimum size
- **WHEN** the PM proposes a live exploration trade at 5 shares while conservative preset caps at 2
- **THEN** the proposal is automatically resized to 2 shares before entering the approval queue, with the resize noted on the entry

### Requirement: Exploration edge is reported separately
`summarize()` and reflection SHALL report P&L and thesis grades for exploration
vs non-exploration cohorts separately, with sample counts, answering "do our
off-book calls have edge?" numerically.

#### Scenario: Gut calls turn out bad
- **WHEN** after 15 exploration trades the cohort P&L is clearly negative while on-book is positive
- **THEN** reflection lessons state this with counts, and MAY suggest lowering epsilon (bounded suggestion, human-applied like risk suggestions today)
