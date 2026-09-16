# Design — agentic-trader-v2

## Core stance: evidence, not permission
The single biggest behavior change: the engine score and any checklist are
EVIDENCE the agents weigh, never a gate they must pass. The PM may propose against
the engine with a written thesis. The deterministic `risk_gate` (size/whitelist/
caps/kill-switch) remains the only hard gate before execution, and the human
remains the only gate before LIVE.

Why this fixes "agents almost never trade": binary threshold gates compound —
8 engines each needing to agree ≈ no trades. Humans instead size DOWN under
uncertainty rather than not acting. So: conviction maps to size (already in
risk presets), uncertainty maps to smaller size or sim-only, and only risk_gate
maps to "no".

## Two lanes
- **SIM lane** (`mode: "sim"`): committee runs end-to-end autonomously —
  debate -> proposal -> risk_gate -> simulated fill -> journal. No human.
  This is where volume, experiments, and exploration happen.
- **LIVE lane** (`mode: "live"`): identical pipeline, but stops at 'proposed';
  human approves via CLI/web UI; typed "LIVE" confirm; env SPY_LIVE=1. Unchanged
  from today's advisor.py flow.
Reflection weights live outcomes 3x sim outcomes when computing edge.

## Committee as separate sessions, one orchestrator
`committee.py` drives three hosted agents SEQUENTIALLY in separate sessions
(separate context prevents self-agreement):
1. Bull gets: engine component scores, radar, playbook, own beliefs file, lessons.
   Produces a structured thesis (JSON via a `submit_case` custom tool).
2. Bear gets: the bull's case + same evidence + shadow/regret stats. Produces a
   rebuttal + its own alternative (possibly "short-term no trade, but…").
3. PM gets: both cases + account standing + calibration scores of bull/bear +
   exploration-budget status. PM either calls `propose_trade` (same handler as
   advisor.py — extract it into a shared module) or `pass_with_reason`.
Everything is appended to `debates/<debate_id>.json`. Journal entries carry
`debate_id`. A pass creates a shadow entry (see below).

Cost control: run personas on Haiku by default (model set in agent spec);
one committee run should stay in the $0.05–0.25 range like decision_view.

## Exploration budget (not-by-the-book, safely)
`exploration.py` tracks a rolling budget, e.g. `epsilon = 0.25`: at least 25% of
sim proposals per rolling 20 must be tagged `origin: "exploration"` — defined as
EITHER against the engine lean OR from an unproven playbook hypothesis OR a pure
gut call with a written hunch. The PM is TOLD its current budget status each
session ("you are under-exploring: 2/20 recent trades were exploratory").
Exploration trades still pass risk_gate; in LIVE they additionally require
conviction >= threshold and are size-capped to the minimum preset.
Reflection reports exploration edge separately — the question "do our gut calls
make money?" gets a number instead of a vibe.

## Regret tracking (shadow trades)
`shadow.py`: when the PM passes, record {ts, symbol, hypothetical entry (live
quote), the direction it WOULD have taken per the bull case, debate_id}.
A scheduled sweep (piggyback on the 8:45 launchd job) marks shadow entries to
maturity (time-stop from the bull's exit plan) and scores them. Reflection then
reports: "of the last 12 passes, 7 would have profited; the desk is too timid
in <regime>" — the counterweight to only learning from taken trades.

## Learning loop (extended)
journal + shadow + predictions + debates
  -> reflect.py (weekly + on demand)
  -> lessons.md (as today)
  -> beliefs/bull.md, beliefs/bear.md, beliefs/pm.md, beliefs/futurist.md
     (each persona's evolving worldview; bounded edits, human-reviewable diff)
  -> playbook.json status changes (trial -> active -> retired) — suggested by
     reflect, applied deterministically by playbook.py rules (see spec)
  -> calibration table (Brier by persona/horizon) injected into PM context

## Predictions vs trades
Predictions are cheap and plentiful; trades are expensive and rare. Personas log
predictions during ANY session via a `log_prediction` custom tool:
{claim, probability, horizon_date, category: price|macro|industry|stock, basis}.
`predictions.py` resolves matured predictions (price claims auto-resolved from
quotes where possible; others resolved by the reflection agent with web_search,
human can override). Brier score per persona per category = the calibration
input to the PM. This gives "prediction involved" and trains judgment even in
flat weeks with no trades.

## Futurist
`futurist.py`: monthly hosted session (web_search/web_fetch + radar reads).
Writes `theses/<slug>.md` — a 3–12mo view on an industry or single name with
2–4 falsifiable predictions logged in the prediction ledger. Bull/bear receive
the CURRENT theses index as context. Futurist revisits its own past theses each
run and marks them strengthening/weakening. Radar scout stays the short-horizon
catalyst finder; futurist is the long-horizon thinker. (Trading stays SPY-only
until the whitelist is deliberately widened — theses inform SPY macro view and
build the research muscle.)

## Shared proposal handler (refactor)
Extract `h_propose`/`execute_approved`/`_order_args` from advisor.py into
`cma_lab/execution.py`, imported by both advisor.py and committee.py, so there is
exactly ONE code path that touches orders. advisor.py keeps its CLI; committee
becomes the scheduled brain.

## Data shapes (authoritative)
journal entry v2 (superset of today's):
```json
{
  "id": "j-...", "mode": "sim|live", "origin": "committee|advisor|exploration",
  "debate_id": null, "hypothesis_id": null,
  "symbol": "SPY", "side": "buy", "qty": "1", "limit": "620.10",
  "thesis": "...", "kill_criteria": "...",
  "exit_plan": {"target": 0.0, "stop": 0.0, "time_stop": "2026-07-10"},
  "conviction": "low|medium|high", "regime": "...", "strategy": "...",
  "status": "proposed|approved|rejected|open|closed",
  "outcome": {"pnl": 0.0, "thesis_grade": "right_win|right_loss|wrong_win|wrong_loss"},
  "reflection": "..."
}
```
playbook.json entry:
```json
{"id": "h-...", "name": "second-red-day-bounce", "rule": "plain-english entry/exit",
 "proposed_by": "bear", "status": "trial|active|retired",
 "trials": {"n": 0, "wins": 0, "pnl": 0.0}, "min_trials": 10, "notes": "..."}
```
prediction entry:
```json
{"id": "p-...", "persona": "bull", "claim": "...", "probability": 0.7,
 "category": "price|macro|industry|stock", "made_at": "...", "horizon": "...",
 "resolved": null, "outcome": null, "brier": null, "basis": "..."}
```

## Decisions / trade-offs
- Flat JSON over SQLite: matches existing cma_lab pattern; volumes are tiny.
- Sequential debate over parallel: bear must SEE the bull case to attack it.
- Deterministic playbook graduation rules (not LLM judgment) to keep the
  "what is allowed to size up" decision auditable.
- Personas on Haiku, reflect/futurist on Sonnet (deeper synthesis, low frequency).
- No new external services; everything runs local + CMA like today.
