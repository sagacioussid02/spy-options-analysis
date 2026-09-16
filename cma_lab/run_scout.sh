#!/bin/bash
# Weekly sector radar sweep -> radar.json + Robinhood "Radar" watchlist + log.
# Disable: launchctl unload ~/Library/LaunchAgents/com.sidd.spy.scout.plist
set -euo pipefail

REPO="/Users/siddharthshankar/workspace/spy"
cd "$REPO"
mkdir -p cma_lab/briefings
LOG="cma_lab/briefings/radar-$(date +%Y-%m-%d).txt"

{
  echo "===== radar sweep @ $(date '+%Y-%m-%d %H:%M:%S %Z') ====="
  "$REPO/.venv/bin/python" cma_lab/scout.py
  echo
} >> "$LOG" 2>&1
