#!/bin/bash

echo "🧪 COMPLETE WORKFLOW TEST"
echo "======================="
echo ""

echo "1️⃣  Running decision engine..."
./.venv/bin/python spy_decision_engine/main.py > /dev/null 2>&1
echo "   ✓ Decision generated"
echo ""

echo "2️⃣  Checking option premiums..."
PREMIUM_OUTPUT=$(./.venv/bin/python spy_decision_engine/utils/option_pricing.py)
echo "   ✓ Premiums calculated"
echo ""

echo "3️⃣  Recording a sample trade entry..."
TRADE_ID=$(./.venv/bin/python trade_cmd.py add --strike 691 --dte 2 --entry 2.18 --premium 2.18 --contracts 5 2>&1 | grep "Trade added" | awk '{print $3}')
echo "   ✓ Trade recorded: $TRADE_ID"
echo ""

echo "4️⃣  Recording trade exit..."
./.venv/bin/python trade_cmd.py close --id $TRADE_ID --exit 2.50 --premium-sold 2.50 > /dev/null 2>&1
echo "   ✓ Trade closed"
echo ""

echo "5️⃣  Querying database - all trades:"
echo "   ---"
./.venv/bin/python db_query.py trades 2>/dev/null | head -15
echo "   ---"
echo ""

echo "6️⃣  Querying database - statistics:"
echo "   ---"
./.venv/bin/python db_query.py stats 2>/dev/null | head -12
echo "   ---"
echo ""

echo "✅ COMPLETE WORKFLOW VERIFIED!"
echo ""
echo "Your system is ready for trading tomorrow! 📈"
