# Tasks — agentic-trader-v2

Rules for the implementer:
- Read `openspec/project.md`, `proposal.md`, `design.md`, and the relevant
  `specs/*/spec.md` BEFORE each phase. The data shapes in design.md are
  authoritative.
- Build ON the existing `cma_lab/` code; copy the established patterns
  (agent deploy w/ SPEC_VERSION, custom tool handlers `h_*`, JSON store classes).
- NEVER touch: risk_gate hard caps/policy locks, the typed-"LIVE" confirm, env
  SPY_LIVE gating, kill-switch checks. If a task seems to require it, STOP and ask.
- All new JSON/md data files go in `cma_lab/` and must be added to `.gitignore`
  (they contain account/strategy data). Code files ARE committed.
- After each phase: run the listed verification, then commit with the phase name.
- Run python as `.venv/bin/python` from repo root.

## Phase 1 — Journal v2 + shared execution (spec: falsifiable-proposals) — DONE
- [x] 1.1 Extend `cma_lab/journal.py` to schema v2 (see design.md data shape):
      add mode/origin/debate_id/hypothesis_id/kill_criteria/exit_plan/
      thesis_grade. Validate required fields in the propose path and
      return readable error strings (JournalValidationError). Keep v1 entries
      readable (all new fields have defaults; reads use .get()).
- [x] 1.2 Created `cma_lab/execution.py`: moved `h_propose`, `execute_approved`,
      `_order_args`, `_extract_price`, `_live_spy_price`, `_qty_str`, `J`,
      `ACCOUNT`, `LIVE_EXECUTION`, `LIVE_MAX_SHARES` out of `advisor.py`;
      advisor.py imports them (behavior unchanged). `mode` flows through
      propose()/h_propose already (default "live"); Phase 2 adds execute_sim
      and wires the committee caller.
- [x] 1.3 Updated `advisor.py` propose_trade schema + system prompt to REQUIRE
      thesis, kill_criteria, exit_plan{target,stop,time_stop}, conviction.
      Bumped SPEC_VERSION 3 -> 4 (redeploys the hosted agent on next run).
- [x] 1.4 Verified: journal.py demo runs; propose() raises JournalValidationError
      naming missing fields with zero entries written, then succeeds once
      complete (tested via temp journal, not the real journal.json); execution.py
      and advisor.py both import cleanly standalone; propose_trade required list
      confirmed via advisor.CUSTOM_TOOLS. NOT verified: a live hosted-agent
      session end-to-end (needs ANTHROPIC/CMA credentials + a real run) — next
      time you run `.venv/bin/python cma_lab/advisor.py` it will redeploy to
      spec v4 and you can confirm the agent supplies kill_criteria/exit_plan.

## Phase 2 — Sim lane + daily sweep (spec: sim-autonomy) — DONE
- [x] 2.1 In `execution.py`: added `_gate_and_afford()` (shared risk_gate +
      affordability check, factored out of `execute_approved` so both lanes use
      the exact same gate) and `execute_sim(entry)` — gate -> simulated fill at
      live quote/limit -> `journal.open_sim()` (status "open"). No approval, no
      prompts. `execute_approved` behavior is unchanged (same checks, same
      LIVE_EXECUTION path).
- [x] 2.2 Created `cma_lab/sweep.py` (deterministic, no LLM): iterates
      `journal.open_positions()`, fetches a quote via `lab.mcp_call_tool`, closes
      at target/stop/time_stop via `_should_close()`, computes pnl through the
      existing `journal.close()`. Idempotent by construction — closed entries
      drop out of `open_positions()`. Playbook/shadow/prediction resolution are
      stub no-op functions with docstrings pointing at the phases that replace
      them (5/3/6).
- [x] 2.3 Wired into `cma_lab/run_decision_view.sh` — runs after
      `decision_view.py --run-engine`, appended to the same dated log.
- [x] 2.4 `journal.summarize()` now reports `closed_live`/`closed_sim` at the top
      level and, per bucket (strategy/regime/conviction), `n_sim`/`n_live` plus
      `weighted_pnl`/`weighted_win_rate` (live weighted 3x). Legacy v1 entries
      (no `mode` field) default to "live" for this weighting, matching how they
      were actually created (human-approved lane), not "sim".
- [x] 2.5 Verified end-to-end on a temp journal (not the real journal.json):
      proposed a sim entry with `time_stop` in the past -> `execute_sim` opened
      it with no approval step -> `sweep.run()` closed it via the time_stop
      reason with pnl computed -> running sweep again closed 0 (idempotent).
      Also confirmed the REAL (unmocked) risk_gate blocks an oversized sim
      order (qty 999 > max 5) and the entry stays "proposed", not silently
      opened. NOT run against the live Robinhood MCP quote endpoint in this
      session (quotes were mocked/stubbed for the test) — first real sweep run
      via the launchd job will exercise that path.

## Phase 3 — Committee (spec: investment-committee) — the big one — DONE
- [x] 3.1 Created `cma_lab/committee.py` with three hosted personas (bull, bear,
      pm), each with own AGENT_ID/SPEC keys in cma_state.json (bull_agent_id/
      spec, bear_..., pm_...), Haiku model, prompts per spec ("evidence not
      permission", size-down-not-pass, beliefs injection). Custom tools:
      submit_case (bull/bear), propose_trade + pass_with_reason (PM only),
      get_engine_components (all personas — reads final_decision.json but
      deliberately returns ONLY component_scores/market_conditions/
      entry_strategy, omitting final_score/decision so nothing anchors on the
      blended verdict). Read handlers (get_engine_analysis, get_journal_summary,
      get_recent_trades, get_lessons, get_risk_settings, get_account_standing)
      reused directly from `advisor.py` via import — one implementation, no
      copy-paste drift. Added get_regret_stats (all personas) reading
      shadow.py's summarize().
- [x] 3.2 Orchestration in `run_once()`: sequential sessions bull -> bear (gets
      full bull case in kickoff text) -> pm (gets both cases + activity status
      + regret stats; calibration/exploration-budget are explicit text stubs
      pointing at Phases 6/4). Debates persisted to
      `cma_lab/debates/<id>.json` (engine_snapshot, bull_case, bear_case,
      pm_decision) — decision is read back from journal.json/shadow.json
      (source of truth), not from the model's claimed intent. PM's
      propose_trade wrapper (`make_h_pm_propose`) injects debate_id, defaults
      mode="sim" -> auto-calls `execution.execute_sim`; mode="live" leaves the
      entry "proposed" for existing advisor.py /approve flow (live enqueues,
      as designed).
- [x] 3.3 Created `cma_lab/shadow.py`: `ShadowStore` (record_pass/open_entries/
      resolve/summarize). PM's `pass_with_reason` wrapper (`make_h_pass`)
      records a shadow entry from the BULL's suggested_trade (direction +
      exit_plan) at the current quote. `sweep.py`'s `_resolve_shadow()` stub
      replaced with the real resolver: matures shadow entries at time_stop
      (not on early stop/target touch — graded once), idempotent (resolved
      entries drop out of open_entries()).
- [x] 3.4 Beliefs: `cma_lab/beliefs/` seeded lazily on first read
      (`_read_beliefs()`) with 2-3 sentence neutral starting worldviews per
      persona; injected into each session's kickoff text; 3000-word
      truncation implemented.
- [x] 3.5 Under-trading nudge (`_activity_status()`): scans the last 5 debate
      files in `cma_lab/debates/`, counts how many resulted in a proposal;
      flags "UNDER-TRADING" in the PM prompt when proposed < 3 of >= 3 sessions
      on record (guarded against overreacting to a nearly-empty history).
- [x] 3.6 Wired into `run_decision_view.sh`: `committee.py --once` now runs
      between the engine refresh and the sweep. `main()` treats any arg other
      than "deploy" (including "--once", or no arg at all) as "run one debate";
      "deploy" redeploys the three personas without running a debate.
- [x] 3.7 Verified WITHOUT live hosted-agent sessions (no committee.py end-to-end
      run against real CMA in this session — that needs your ANTHROPIC/CMA
      credentials and costs real tokens): (a) all three agents' tool schemas
      and handler wiring import cleanly; (b) `get_engine_components` returns
      the real component_scores/market_conditions from your actual
      final_decision.json, correctly excluding final_score/decision; (c)
      beliefs seeding + activity-status logic verified against temp dirs; (d)
      `make_h_pm_propose` end-to-end on a temp journal (mocked risk_gate/quote):
      sim proposal auto-executes to "open" with mode/origin/debate_id set
      correctly; (e) `make_h_pass` end-to-end on a temp shadow store: records a
      shadow entry from the bull's suggested_trade; (f) sweep's real
      `_resolve_shadow()` matures a shadow entry at time_stop with correct
      per-share pnl and is idempotent on a second run. NEXT STEP FOR YOU: run
      `.venv/bin/python cma_lab/committee.py --once` for real to confirm the
      three hosted personas actually converse as intended and produce a
      genuine debate file — watch the console_url links it prints, and check
      cost via the printed report_cost output (budgeted ~$0.05-0.30 on Haiku).

## Phase 4 — Exploration budget (spec: exploration-budget) — DONE
- [x] 4.1 Created `cma_lab/exploration.py`: `get_epsilon()` reads
      risk_overrides.json key `exploration_epsilon` (default 0.25, clamped to
      [0.10, 0.40]); `status()`/`status_text()` compute the exploration share
      over the last 20 SIM proposals (mode=="sim") and produce the
      under/over/on-target nudge string. Wired into `committee.py`'s PM
      kickoff, replacing the Phase 3 stub text.
- [x] 4.2 `propose_trade`'s schema (committee.py) now REQUIRES `origin_reason`
      (engine_aligned | against_engine | hunch | untested_playbook) instead of
      a free-text origin field. `execution.py`'s new `_derive_origin()` maps
      against_engine/hunch/untested_playbook -> origin="exploration",
      engine_aligned -> "committee"; advisor.py (which never sends
      origin_reason) keeps its original default origin="advisor" unchanged.
- [x] 4.3 Live-exploration constraint implemented inside `execution.h_propose`:
      if mode="live" and the derived origin is "exploration" — conviction < 0.7
      auto-downgrades the entry to mode="sim" (noted in human_notes); otherwise
      quantity is resized down to the conservative preset cap
      (`APPETITE_PRESETS["conservative"]["max_quantity"]`, currently 1) if it
      exceeds it, also noted. `committee.py`'s `make_h_pm_propose` reads the
      ACTUAL persisted mode back from the journal after calling h_propose
      (rather than trusting its own pre-call guess) before deciding whether to
      auto-execute via execute_sim — this matters because execution.py can
      silently downgrade live->sim and the old code would have left such
      entries stuck as "proposed" forever.
- [x] 4.4 `journal.summarize()` gained `by_origin` (`exploration` vs `on_book`),
      using the same bucketize helper as the other cohorts (so it carries
      n_sim/n_live/weighted_pnl/weighted_win_rate too).
- [x] 4.5 Verified on a temp journal (mocked risk_gate/quote where needed):
      origin_reason -> origin derivation (against_engine/hunch/untested_playbook
      -> exploration, engine_aligned -> committee); live+low-conviction
      exploration auto-downgrades to sim with a note; live+high-conviction
      oversized exploration resizes to the conservative cap (5 -> 1) with a
      note and stays live; exploration.status()/status_text() correctly
      compute window/share/target and produced an "OVERWEIGHT" nudge on a
      2-of-3 exploration mix; by_origin cohort split populates correctly on
      closed trades with independent pnl/win_rate per cohort. Also
      reconfirmed the REAL (unmocked) risk_gate is still consulted at
      EXECUTION time regardless of origin (propose-time itself never bypasses
      it — risk_gate always runs in execute_sim/execute_approved, as before).

## Phase 5 — Playbook (spec: hypothesis-playbook) — DONE
- [x] 5.1 Created `cma_lab/playbook.py`: `Hypothesis` dataclass matches
      design.md's shape (id/name/rule/proposed_by/status/min_trials/trials
      {n,wins,pnl}), plus an internal `trailing_pnls` list (last min_trials
      closed pnls) needed to implement the trailing-window retirement rule.
      `Playbook.register()` dedupes by normalized slug (punctuation/case
      insensitive) — registering an existing idea returns it unchanged.
      `update_from_close(journal_entry)` is the deterministic hook: updates
      trials, then applies graduation (trial->active when n>=min_trials AND
      total pnl>0 AND win_rate>=0.5) and retirement (trial|active->retired
      when the trailing min_trials pnls sum negative) — pure code, no LLM
      judgment involved in the transition itself.
- [x] 5.2 Added `register_hypothesis` tool to bull, bear, AND pm (not just
      bull/bear — pm can register from its own synthesis too), each bound to
      a `make_h_register_hypothesis(persona)` factory that stamps
      `proposed_by`. `Playbook().context_view()` (trial/active expanded one
      line each, retired collapsed to a cautionary list) is injected into all
      three kickoff prompts. (Reflect-side registration deferred to Phase 7,
      as planned — reflect.py doesn't exist yet in this rollout.)
- [x] 5.3 `execution.h_propose` now checks `hypothesis_id` before the
      exploration check: if the linked hypothesis is still `status=="trial"`
      and `mode=="live"`, it force-downgrades to `mode="sim"` with a note,
      regardless of conviction — trial ideas don't get a conviction escape
      hatch the way exploration trades do. `propose_trade`'s schema
      (committee.py) gained `hypothesis_id`.
- [x] 5.4 Verified (temp journal + the REAL default `cma_lab/playbook.json`,
      confirmed empty beforehand and deleted immediately after each test so no
      artifacts were left in your repo): (a) register + dedupe by
      normalized/punctuation-insensitive name; (b) a live proposal linked to a
      trial hypothesis downgrades to sim with a note, independent of
      conviction; (c) 10 fabricated winning closes graduate a hypothesis to
      "active"; 10 fabricated losing closes retire one; a mixed win/loss
      sequence (net positive, win_rate 0.6) correctly graduates rather than
      retiring; (d) `sweep.run()` end-to-end: an open sim entry with a
      hypothesis_id closes via time_stop and the playbook's trial stats update
      through the real (non-stubbed) code path. NOT run: an actual committee
      session where a live persona calls register_hypothesis — that needs a
      real hosted-agent run (same caveat as Phases 3/4).

## Phase 6 — Predictions + calibration (spec: prediction-ledger) — DONE
- [x] 6.1 Created `cma_lab/predictions.py`: `PredictionStore` with falsifiability
      validation — claim must be >=15 chars AND pass `_is_vague()` (rejects
      hedge language: "-ish", "kind of", "sort of", "maybe", "probably", "some",
      unqualified "around", matching the spec's own "volatile-ish" example),
      probability clamped to [0.05, 0.95], category in
      {price,macro,industry,stock}, horizon_date a real ISO date. Price
      predictions additionally REQUIRE structured `symbol`/`level`/`direction`
      fields (not free-text parsing) so resolution can be deterministic —
      no NLP/LLM judgment in the resolution path itself.
      `calibration_table()` gives mean Brier per persona x category with n.
- [x] 6.2 Added `log_prediction` to bull, bear, AND pm tool lists in
      committee.py, each bound to `make_h_log_prediction(persona, debate_id)`.
      All three system prompts now instruct logging >=1 falsifiable prediction
      per session, win or pass.
- [x] 6.3 `sweep.py`'s `_resolve_predictions()` stub replaced with
      `PredictionStore().resolve_price_predictions(_quote)` — deterministic,
      reuses the same `_quote()` helper as position/shadow resolution.
- [x] 6.4 Extended the EXISTING `cma_lab/reflect.py` (built before this
      rollout) rather than creating a new file: added a web-search toolset
      (reflect previously had none), `get_pending_predictions` (matured
      non-price only — price is explicitly out of scope here) and
      `resolve_prediction` (requires a one-line justification; rejects price
      predictions and already-resolved ones). Bumped reflect's SPEC_VERSION
      1->2. Added `/resolve <pred_id> true|false` to advisor.py's CLI as the
      human-override path.
- [x] 6.5 `committee.py`'s PM kickoff now calls `_calibration_text()` (real
      per-persona/category mean Brier + n) in place of the Phase 3/4 stub
      line; PM system prompt updated to say to weight bull/bear by it under
      disagreement.
- [x] 6.6 Verified on temp stores plus the REAL default `predictions.json`
      (confirmed empty beforehand, deleted immediately after each test — no
      artifacts left behind): (a) the exact "volatile-ish" vague-claim example
      from the spec is rejected, legitimate price/macro claims still pass;
      (b) price predictions without symbol/level/direction are rejected;
      (c) `resolve_price_predictions` auto-resolves two opposing SPY calls
      correctly (bull right, bear wrong) with correct Brier scores, and is
      idempotent on a second pass; (d) `calibration_table()` aggregates
      correctly per persona/category; (e) `committee._calibration_text()`
      renders "no resolved predictions yet" when empty and the real table once
      populated; (f) reflect.py's `get_pending_predictions`/`resolve_prediction`
      correctly list only matured non-price predictions, reject price-category
      overrides, and reject missing justifications; (g) advisor.py's
      `/resolve` command resolves a real prediction and handles bad
      id/malformed args gracefully. NOT run: an actual hosted committee/reflect
      session — same caveat as prior phases, needs your credentials.

## Phase 7 — Reflection v2 + futurist (specs: falsifiable-proposals,
##            investment-committee, futurist-research) — DONE
- [x] 7.1 Extended the EXISTING `reflect.py` (SPEC_VERSION 2->3) with six new
      tools: `get_ungraded_trades`/`grade_trade` (thesis 2x2: right_win/
      right_loss/wrong_win/wrong_loss — grading is from thesis/kill_criteria/
      exit_plan/pnl already on the closed entry, not a separate price-history
      pull); `get_ungraded_debates`/`grade_debate` (bull_right/bear_right/
      both_wrong/unclear — a debate counts as "ungraded" only once its linked
      journal entry has CLOSED or its linked shadow entry has RESOLVED, checked
      via `_debate_resolution()`; writes `grade`+`grade_rationale` into the
      debate JSON file); `get_shadow_stats` (regret hit-rate); `update_beliefs`
      (dated append to beliefs/<persona>.md). `h_propose_risk_change` now also
      accepts `parameter=exploration_epsilon` (same MIN_SAMPLE gate as the
      existing params, clamped to [0.10, 0.40]). `journal.summarize()` gained
      `by_thesis_grade` (reuses the same weighted bucketize helper). SYSTEM
      prompt rewritten to sequence: lessons -> risk suggestion -> predictions
      -> grade trades -> grade debates -> shadow/exploration commentary ->
      (rare, evidence-gated) belief updates.
- [x] 7.2 Created `cma_lab/futurist.py`: review-then-research flow
      (`get_theses_full`+`get_futurist_predictions`+web_search ->
      `review_thesis` for EVERY existing thesis first, verdict
      strengthening/intact/weakening/invalidated with a dated note appended to
      the file's Review Log and its `status:` line updated; invalidated
      theses move to `theses/archive/`), then ONE new `write_thesis` (view /
      winners-losers / catalysts / what-would-change-my-mind) + 2-4
      `log_prediction` calls (category industry|stock, linked via
      `debate_id="thesis:<slug>"` — a pragmatic reuse of the existing
      prediction-ledger field rather than a schema change). Sonnet model,
      read-only Robinhood tools + web + radar read. `run_futurist.sh` +
      `cma_lab/launchd/com.sidd.spy.futurist.plist` (monthly, day 1, 17:30 —
      NOT installed, matching the reflection/scout convention).
- [x] 7.3 `theses_index_text()` (defined once in futurist.py) injected into
      all three committee kickoffs (bull/bear/pm) and into scout.py's sweep
      kickoff. PM also now gets `_debate_track_record()` (per-persona
      bull_right/bear_right tally from graded debate files) alongside the
      existing calibration table — both feed "who to trust under
      disagreement," from two different kinds of evidence (predictions vs
      debates).
- [x] 7.4 Verified end to end on temp stores (journal/debates/shadow/beliefs/
      theses — all via genuinely isolated tmp paths this time, double-checked
      by asserting the target didn't exist before writing, since Phase 3's
      testing revealed a subtle bug class: patching a module's Path constant
      from outside doesn't help if the code path never actually got exercised
      un-patched elsewhere — belief seed files ended up for real in
      cma_lab/beliefs/ during earlier phase testing, though harmlessly, since
      they're exactly the intended seed content and gitignored):
      (a) grade_trade grades a real closed entry and disappears from
      get_ungraded_trades; invalid grades rejected; (b) get_ungraded_debates
      correctly finds a resolved "propose" debate AND a resolved "pass"
      (shadow) debate while excluding an unresolved one; grade_debate writes
      grade+rationale, rejects bad grades/missing files; (c) committee's
      _debate_track_record() correctly tallies only graded files; (d)
      update_beliefs appends a dated section, rejects bad persona/empty note;
      (e) exploration_epsilon suggestion is gated on MIN_SAMPLE and clamped to
      0.40 on an out-of-range request; (f) futurist's write_thesis produces
      the full expected file structure, log_prediction links via the thesis
      slug, review_thesis updates the status line + appends a dated log entry
      for "strengthening," and the "invalidated" path removes the active file
      and creates it under archive/; theses_index_text() correctly reflects
      empty/populated/archived states. All test artifacts (theses/,
      predictions.json, temp debates/journal/shadow/beliefs dirs) were deleted
      after — confirmed nothing new landed in the repo beyond what Phase 3
      already legitimately seeded. NOT run: an actual hosted futurist/
      reflect/committee session — same caveat as every prior phase.

## Phase 8 — Web UI + docs
- [ ] 8.1 Web UI (`cma_lab/web/`): debate view on proposal cards (bull/bear/PM
      collapsible), playbook panel (status + stats), predictions panel
      (open + calibration table), shadow "trades not taken" panel. Keep LIVE
      approvals terminal-only as today.
- [ ] 8.2 Update `.gitignore` for: debates/, playbook.json, predictions.json,
      shadow.json, beliefs/, theses/.
- [ ] 8.3 Write `cma_lab/README_v2.md`: one-page operator guide — daily flow,
      commands, where each file lives, how to pause everything (kill switch).
- [ ] 8.4 Final verify: full dry run — engine -> committee --once -> sweep ->
      reflect -> open web UI and click through all panels.
