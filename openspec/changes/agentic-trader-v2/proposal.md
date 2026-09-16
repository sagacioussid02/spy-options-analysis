# Change: agentic-trader-v2 — a human-like, risk-taking, learning trading desk

## Why
The current system is one advisor agent that follows the engine's blended score and
proposes rarely. Past experience: rule-following agents trigger almost no trades
because every checklist item must align. We want agents that behave like human
traders: they debate, act under uncertainty, deliberately take calculated risks,
run experiments ("let's try this way!"), make explicit predictions, think about the
future of industries/stocks, and learn from wins AND losses — while the human stays
the only gate before any live order.

## What Changes
Seven capabilities, designed to be built in phases (see tasks.md):

1. **falsifiable-proposals** — every proposal must carry a thesis, a pre-registered
   "what proves me wrong", an exit plan (target/stop/time-stop), and conviction.
   Closed trades are graded on a 2x2 (thesis right/wrong x made/lost money).
2. **sim-autonomy** — a SIM lane where agents propose AND execute simulated trades
   autonomously (no human gate), bounded by risk_gate, with a minimum activity
   cadence so the desk always has live experiments running. LIVE lane unchanged.
3. **investment-committee** — bull analyst, bear analyst, and portfolio manager as
   separate sessions; PM alone can propose; full debate persisted and later graded.
4. **exploration-budget** — an explicit epsilon: a fraction of sim trades MUST go
   against the engine/checklist (gut calls, contrarian takes), tagged and tracked,
   so the system learns whether off-book instinct has edge. Engine score is
   evidence, never permission.
5. **hypothesis-playbook** — agents register named strategy hypotheses ("buy the
   second red day", "fade Friday gamma"), trial them in sim, and graduate/retire
   them on evidence.
6. **prediction-ledger** — agents log probabilistic forecasts (price levels, macro
   events, industry/stock futures) independent of trades; scored with Brier score;
   calibration feeds back into how much the PM trusts each persona.
7. **futurist-research** — a long-horizon research persona writing 3–12 month
   industry & single-stock theses (feeds radar + bull/bear debate), revisited
   monthly against its own predictions.

Plus **regret-tracking** inside falsifiable-proposals: every committee PASS is
recorded as a shadow trade and later scored, so "too timid" becomes measurable
and correctable.

## What Does NOT Change
- risk_gate semantics, hard caps, policy locks, kill switch
- Human approval + typed-confirm path for anything live
- Existing advisor.py CLI and web UI keep working (committee is additive)
- Robinhood MCP integration and token handling in lab.py

## Impact
- Affected specs: all new (this repo has no prior specs/)
- New code: `cma_lab/committee.py`, `cma_lab/playbook.py`, `cma_lab/predictions.py`,
  `cma_lab/futurist.py`, `cma_lab/shadow.py`, `cma_lab/exploration.py`
- Modified: `journal.py` (schema v2), `advisor.py` (shared propose handler),
  `reflect.py` (grading + calibration + playbook/exploration review),
  `web/app.py` + `static/index.html` (debate view, playbook & prediction panels)
- New data files (gitignored): `debates/*.json`, `playbook.json`, `predictions.json`,
  `shadow.json`, `beliefs/*.md`, `theses/*.md`
