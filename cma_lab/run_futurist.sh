#!/bin/bash
# Monthly futurist run. Reviews existing theses against their own predictions
# and current news, then researches and writes one new 3-12 month thesis.
# Disable: launchctl unload ~/Library/LaunchAgents/com.sidd.spy.futurist.plist
set -euo pipefail

REPO="/Users/siddharthshankar/workspace/spy"
cd "$REPO"
mkdir -p cma_lab/briefings
LOG="cma_lab/briefings/futurist-$(date +%Y-%m-%d).txt"

{
  echo "===== futurist @ $(date '+%Y-%m-%d %H:%M:%S %Z') ====="
  "$REPO/.venv/bin/python" cma_lab/futurist.py
  echo
} >> "$LOG" 2>&1
