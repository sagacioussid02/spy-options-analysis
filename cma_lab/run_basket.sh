#!/bin/bash
# Scheduled multi-ticker run — refresh the engine and run one committee cycle
# per ticker, then sweep open positions.
#
# LIVE when SPY_LIVE=1 is set in cma_lab/.env: committee proposals go through
# execution.execute_autonomous (risk_gate, $30/order cap, 1-share cap, sleeve
# exposure cap, broker-state reconciliation in sweep.py). Orders are only
# journaled as filled once the broker reports them filled.
#
# Off-switch: run with SPY_SIM_ONLY=1 (forces everything to paper), or set
# kill_switch in risk_overrides. Set TICKER_BASKET=AAPL,JPM,XOM to override
# the default basket.
set -euo pipefail

REPO="/Users/siddharthshankar/workspace/spy"
cd "$REPO"
mkdir -p cma_lab/briefings
LOG="cma_lab/briefings/$(date +%Y-%m-%d).txt"
PYTHON="$REPO/.venv/bin/python"
export PYTHONUNBUFFERED=1
BASKET_TIMEOUT_S=9000
ENGINE_TIMEOUT_S=600
COMMITTEE_TIMEOUT_S=1100
TOKEN_REFRESH_TIMEOUT_S=60
SWEEP_TIMEOUT_S=300

BASKET="${TICKER_BASKET:-$("$REPO/.venv/bin/python" -c 'import sys; sys.path.insert(0, "cma_lab"); from lab import TICKER_BASKET; print(",".join(TICKER_BASKET))')}"
RUN_DEADLINE=$(( $(date +%s) + BASKET_TIMEOUT_S ))

failures=0
run_step() {
  local label="$1"
  local timeout_s="$2"
  shift 2
  local is_sweep=false
  local remaining_s
  case "$label" in
    "position sweep"*) is_sweep=true ;;
  esac
  if [[ "$is_sweep" == false ]]; then
    remaining_s=$(( RUN_DEADLINE - $(date +%s) ))
    if (( remaining_s <= 0 )); then
      failures=$((failures + 1))
      echo "===== ${label} skipped: basket deadline reached ====="
      return 1
    fi
    if (( timeout_s > remaining_s )); then
      timeout_s=$remaining_s
    fi
  fi
  echo "===== ${label} started @ $(date '+%Y-%m-%d %H:%M:%S %Z') ====="
      if "$PYTHON" cma_lab/run_step.py "$timeout_s" "$@"; then
    echo "===== ${label} finished: OK ====="
  else
    local status=$?
    failures=$((failures + 1))
    echo "===== ${label} finished: FAILED (exit ${status}) ====="
    return 1
  fi
  return 0
}

on_exit() {
  local status=$?
  if [[ $status -ne 0 ]]; then
    echo "===== basket process exited: ${status} @ $(date '+%Y-%m-%d %H:%M:%S %Z') =====" >> "$LOG"
  fi
}
trap on_exit EXIT

# Keep one token lineage: refresh on the host and push to the CMA vault so the
# hosted agents never hold a stale (rotated-away) refresh token.
{
  echo "===== basket run @ $(date '+%Y-%m-%d %H:%M:%S %Z') — basket: $BASKET ====="
  echo "===== basket deadline: ${BASKET_TIMEOUT_S}s; per-step caps: token_refresh=${TOKEN_REFRESH_TIMEOUT_S}s engine=${ENGINE_TIMEOUT_S}s committee=${COMMITTEE_TIMEOUT_S}s sweep=${SWEEP_TIMEOUT_S}s ====="
  run_step "Robinhood token refresh" "$TOKEN_REFRESH_TIMEOUT_S" "$PYTHON" cma_lab/refresh_token.py || true
  IFS=',' read -ra TICKERS <<< "$BASKET"
  for t in "${TICKERS[@]}"; do
    if (( $(date +%s) >= RUN_DEADLINE )); then
      failures=$((failures + 1))
      echo "===== basket deadline reached; skipping remaining tickers ====="
      break
    fi
    echo
    echo "--- $t ---"
    # Refresh this ticker's signal without starting the read-only hosted agent.
    if run_step "$t engine" "$ENGINE_TIMEOUT_S" env TICKER="$t" "$PYTHON" spy_decision_engine/main.py; then
      echo
      run_step "$t committee" "$COMMITTEE_TIMEOUT_S" env TICKER="$t" "$PYTHON" cma_lab/committee.py --once || true
    else
      echo "===== $t committee skipped: engine did not finish successfully ====="
    fi
  done
  echo
  # One shared pass: closes any open position (any basket ticker) that hit
  # its stop/target/time_stop, resolves shadow/prediction entries, applies
  # the sleeve topup if due.
  if [[ "${SPY_SIM_ONLY:-}" =~ ^(1|true|yes)$ ]]; then
    run_step "position sweep (sim-only)" "$SWEEP_TIMEOUT_S" "$PYTHON" cma_lab/sweep.py --sim-only || true
  else
    run_step "position sweep" "$SWEEP_TIMEOUT_S" "$PYTHON" cma_lab/sweep.py || true
  fi
  echo
  if (( failures )); then
    echo "===== basket completed with ${failures} failed step(s); inspect this log ====="
  else
    echo "===== basket completed: all steps OK ====="
  fi
} >> "$LOG" 2>&1

if (( failures )); then
  exit 1
fi
