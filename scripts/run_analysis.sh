#!/bin/bash
# Quick runner for SPY trading decision system
# Usage: ./run_analysis.sh

set -e

echo "🚀 SPY Trading Decision System"
echo "=============================="
echo ""

# Run the main engine
echo "📊 Stage 1: Running analysis engines..."
./.venv/bin/python spy_decision_engine/main.py

# Generate visual dashboard
echo ""
echo "📊 Stage 2: Generating visual dashboard..."
./.venv/bin/python spy_decision_engine/utils/visualize_decision.py

echo ""
echo "✓ Analysis complete!"
echo ""
echo "📋 NEXT STEPS:"
echo "  1. Read the summary:"
echo "     cat spy_decision_engine/reports/final_decision_summary.txt"
echo ""
echo "  2. View the dashboard:"
echo "     open spy_decision_engine/reports/dashboard.html"
echo ""
echo "  3. If trading, record it:"
echo "     ./.venv/bin/python trade_cmd.py add --strike 688 --dte 1 --entry 4.93 --premium 4.93 --contracts 1"
echo ""
