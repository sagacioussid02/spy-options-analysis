# Spec Delta: hypothesis-playbook

## ADDED Requirements

### Requirement: Hypothesis registration ("let's try this way")
Any persona (and reflect) SHALL be able to register a strategy hypothesis via a
`register_hypothesis` custom tool: {name, rule (plain-english entry/exit),
rationale, min_trials (default 10)}. `cma_lab/playbook.py` SHALL store it in
`playbook.json` with status `trial`, deduped by normalized name. The playbook
(names, rules, status, trial stats) SHALL be injected into bull/bear/PM context
every committee session.

#### Scenario: Bear invents a strategy
- **WHEN** the bear, while rebutting, calls register_hypothesis("fade-friday-strength", "short-bias entries Friday after +0.8% morning move, exit at close", ...)
- **THEN** it appears in playbook.json as `trial` and in the next session's context for all personas

### Requirement: Trial tracking and deterministic graduation
Every journal entry created from a hypothesis SHALL carry its `hypothesis_id`.
On close, playbook.py SHALL update that hypothesis's {n, wins, pnl}. Status
transitions SHALL be deterministic (code, not LLM): `trial -> active` when
n >= min_trials AND pnl > 0 AND wins/n >= 0.5; `trial|active -> retired` when
n >= min_trials AND (pnl < 0 for the trailing min_trials trades). Reflection MAY
recommend transitions early, but only the deterministic rule or an explicit
human command applies them.

#### Scenario: Hypothesis graduates
- **WHEN** "second-red-day-bounce" reaches 10 sim trials with 6 wins and positive P&L
- **THEN** playbook.py flips it to `active` during the daily sweep and the change is visible in the web UI and next committee context

#### Scenario: Hypothesis retires on evidence
- **WHEN** an active hypothesis goes negative over its trailing 10 trades
- **THEN** it flips to `retired` with the stats preserved; personas can still see retired entries (as cautionary lessons) in a collapsed section

### Requirement: Active hypotheses may trade live
Proposals from `active` hypotheses SHALL be eligible for the live lane at normal
sizing; proposals from `trial` hypotheses SHALL be sim-only unless the human
explicitly approves an exception at approval time.

#### Scenario: Trial hypothesis stays in sim
- **WHEN** the PM tries to propose live from a `trial` hypothesis
- **THEN** the proposal is created as `mode: "sim"` with a note explaining trial hypotheses must earn live status
