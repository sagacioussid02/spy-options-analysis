#!/bin/bash
# Scheduled decision-view run. Writes each briefing to a dated log so the
# grounded engine+account briefing is waiting for you each morning.
#
# Change WHEN it runs by editing the launchd plist (StartCalendarInterval),
# not this file. Disable with:  launchctl unload ~/Library/LaunchAgents/com.sidd.spy.decisionview.plist
set -euo pipefail

REPO="/Users/siddharthshankar/workspace/spy"
cd "$REPO"
mkdir -p cma_lab/briefings
LOG="cma_lab/briefings/$(date +%Y-%m-%d).txt"

{
  echo "===== decision view @ $(date '+%Y-%m-%d %H:%M:%S %Z') ====="
  # --run-engine refreshes final_decision.json first so the briefing reasons
  # over a current signal (not a stale snapshot). Falls back to existing JSON if
  # the engine run fails.
  "$REPO/.venv/bin/python" cma_lab/decision_view.py --run-engine
  echo
  # Bull/bear/PM debate over the fresh engine signal — proposes (sim
  # auto-executes, live queues for /approve) or passes (recorded + graded).
  "$REPO/.venv/bin/python" cma_lab/committee.py --once
  echo
  # Deterministic close of open sim positions hitting stop/target/time_stop,
  # and resolution of any shadow (pass) entries reaching their time_stop.
  "$REPO/.venv/bin/python" cma_lab/sweep.py
  echo
} >> "$LOG" 2>&1
