#!/bin/bash
# Scheduled multi-ticker run — one full decision_view/committee cycle per
# ticker in TICKER_BASKET, then a single shared sweep.py pass that closes
# any basket member's open positions hitting stop/target/time_stop (sweep
# already scans the whole journal by each entry's own symbol, so it needs
# no ticker argument and no loop of its own).
#
# Set TICKER_BASKET=AAPL,JPM,XOM (or your own list) in the environment
# before running, or edit the default below. Change WHEN it runs by editing
# the launchd plist / cloud routine schedule, not this file.
set -euo pipefail

REPO="/Users/siddharthshankar/workspace/spy"
cd "$REPO"
mkdir -p cma_lab/briefings
LOG="cma_lab/briefings/$(date +%Y-%m-%d).txt"

BASKET="${TICKER_BASKET:-AAPL,JPM,XOM}"

{
  echo "===== basket run @ $(date '+%Y-%m-%d %H:%M:%S %Z') — basket: $BASKET ====="
  IFS=',' read -ra TICKERS <<< "$BASKET"
  for t in "${TICKERS[@]}"; do
    echo
    echo "--- $t ---"
    # --run-engine refreshes final_decision.json first so the debate reasons
    # over a current signal (not a stale snapshot) for THIS ticker.
    TICKER="$t" "$REPO/.venv/bin/python" cma_lab/decision_view.py --run-engine
    echo
    # Bull/bear/PM debate over the fresh engine signal — proposes (sim
    # auto-executes, live queues for /approve or executes autonomously
    # under the per-order + sleeve exposure caps) or passes (recorded + graded).
    TICKER="$t" "$REPO/.venv/bin/python" cma_lab/committee.py --once
  done
  echo
  # One shared pass: closes any open position (any basket ticker) that hit
  # its stop/target/time_stop, resolves shadow/prediction entries, applies
  # the sleeve topup if due.
  "$REPO/.venv/bin/python" cma_lab/sweep.py
  echo
} >> "$LOG" 2>&1
