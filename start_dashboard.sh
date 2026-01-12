#!/bin/bash
# Start the SPY Trading Dashboard Server

set -e

# Get the directory of this script
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Check if venv exists
if [ ! -d ".venv" ]; then
    echo "❌ Virtual environment not found. Please run setup first."
    exit 1
fi

# Check if Flask is installed
if ! ./.venv/bin/python -c "import flask" 2>/dev/null; then
    echo "📦 Installing Flask..."
    ./.venv/bin/pip install flask -q
fi

echo ""
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║              🚀 SPY TRADING DASHBOARD                          ║"
echo "║                                                                ║"
echo "║  Starting server on http://localhost:8080                     ║"
echo "║                                                                ║"
echo "║  Features:                                                     ║"
echo "║  ✓ Live analysis dashboard                                    ║"
echo "║  ✓ Update Analysis button to rerun in real-time               ║"
echo "║  ✓ Real market data (yfinance + Finnhub)                      ║"
echo "║                                                                ║"
echo "║  Press CTRL+C to stop                                         ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

./.venv/bin/python dashboard_server.py
