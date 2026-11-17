#!/bin/bash
# Sutra adapter: the desk's read tools on http://127.0.0.1:8790 (see
# docs/guides/SPY_DESK_MCP.md, "Sutra HTTP adapter").
# SPY_DESK_TOKEN is read from cma_lab/.env (keep it chmod 600); the adapter
# refuses to start without it. Nothing here sets SPY_LIVE. The adapter blocks
# every broker call except reads, unless SPY_DESK_SUTRA_TRADING is set, and
# then only inside place_desk_order (see sutra_trading.py).
# Disable: launchctl unload ~/Library/LaunchAgents/com.sidd.spy.sutra-api.plist
set -euo pipefail

REPO="/Users/siddharthshankar/workspace/spy"
cd "$REPO/cma_lab"
exec "$REPO/.venv/bin/python" sutra_api.py
