#!/bin/bash
# Weekly reflection. Reads the trade journal, updates lessons.md, and (only with
# enough closed trades) records bounded risk suggestions for you to review.
# Disable: launchctl unload ~/Library/LaunchAgents/com.sidd.spy.reflection.plist
set -euo pipefail

REPO="/Users/siddharthshankar/workspace/spy"
cd "$REPO"
mkdir -p cma_lab/briefings
LOG="cma_lab/briefings/reflection-$(date +%Y-%m-%d).txt"

{
  echo "===== reflection @ $(date '+%Y-%m-%d %H:%M:%S %Z') ====="
  "$REPO/.venv/bin/python" cma_lab/reflect.py
  echo
} >> "$LOG" 2>&1
