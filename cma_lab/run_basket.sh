#!/bin/bash
# Scheduled multi-ticker prototype — refresh the engine and run one committee
# cycle per ticker in simulation-only mode, then sweep simulated positions.
#
# Set TICKER_BASKET=AAPL,JPM,XOM (or your own list) in the environment
# Live trading is deliberately disabled here. Set TICKER_BASKET in the
# environment or edit the default below. Live automation needs a separate,
# explicitly reviewed runner and broker-fill reconciliation first.
set -euo pipefail

REPO="/Users/siddharthshankar/workspace/spy"
cd "$REPO"
mkdir -p cma_lab/briefings
LOG="cma_lab/briefings/$(date +%Y-%m-%d).txt"

BASKET="${TICKER_BASKET:-$("$REPO/.venv/bin/python" -c 'import sys; sys.path.insert(0, "cma_lab"); from lab import TICKER_BASKET; print(",".join(TICKER_BASKET))')}"

{
  echo "===== basket run @ $(date '+%Y-%m-%d %H:%M:%S %Z') — basket: $BASKET ====="
  IFS=',' read -ra TICKERS <<< "$BASKET"
  for t in "${TICKERS[@]}"; do
    echo
    echo "--- $t ---"
    # Refresh this ticker's signal without starting the read-only hosted agent.
    TICKER="$t" "$REPO/.venv/bin/python" spy_decision_engine/main.py
    echo
    # Force the autonomous live gate off for this scheduled prototype.
    SPY_SIM_ONLY=1 TICKER="$t" "$REPO/.venv/bin/python" cma_lab/committee.py --once
  done
  echo
  # One shared pass: closes any open position (any basket ticker) that hit
  # its stop/target/time_stop, resolves shadow/prediction entries, applies
  # the sleeve topup if due.
  "$REPO/.venv/bin/python" cma_lab/sweep.py --sim-only
  echo
} >> "$LOG" 2>&1
