# Quick Reference: Behavioral Analytics Commands

## 🎯 Before Making a Trade

### Check if it's worth taking
```bash
python3 spy_decision_engine/utils/trade_recommendation_engine.py
```
Output: ✅ STRONG BUY / 🟡 CAUTIOUS BUY / ⚠️ SKIP / ❌ AVOID

### Predict success rate on similar trades
```bash
python3 << 'EOF'
from spy_decision_engine.utils.behavioral_analytics import BehavioralAnalytics
a = BehavioralAnalytics()
p = a.predict_trade_outcome({"reason": "Momentum: trend following", "confidence": 75})
print(f"Win Rate: {p['historical_win_rate']:.0%}, Expected Value: ${p['expected_value']:.0f}")
EOF
```

---

## 📊 After Closing a Trade

### Auto-update behavioral analysis
```bash
python3 spy_decision_engine/utils/behavioral_analytics.py
```
Shows updated win rates by strategy type

### Check for behavioral biases
```bash
python3 << 'EOF'
from spy_decision_engine.utils.behavioral_analytics import BehavioralAnalytics
a = BehavioralAnalytics()
b = a.detect_behavioral_biases()
for bias in b['biases']:
    print(f"• {bias['bias']}: {bias['description']}")
EOF
```

---

## 📈 View Your Performance

### Overall report
```bash
python3 spy_decision_engine/utils/behavioral_analytics.py
```

### JSON export (for analysis)
```bash
cat spy_decision_engine/reports/behavioral_analysis.json | python3 -m json.tool
```

### Strategy breakdown
```bash
python3 << 'EOF'
from spy_decision_engine.utils.behavioral_analytics import BehavioralAnalytics
a = BehavioralAnalytics()
analysis = a.analyze_behavior_patterns()
for strat, stats in analysis['strategy_breakdown'].items():
    print(f"{strat}: {stats['win_rate']:.0%} | Avg: ${stats['avg_profit']:.0f}")
EOF
```

---

## 🎓 Learn Your Patterns

### See all your trades with conditions
```bash
cat spy_decision_engine/data/trades.json | python3 -m json.tool | grep -A5 "reason"
```

### What strategy performs best?
```bash
python3 << 'EOF'
from spy_decision_engine.utils.behavioral_analytics import BehavioralAnalytics
a = BehavioralAnalytics()
analysis = a.analyze_behavior_patterns()
best = max(analysis['strategy_breakdown'].items(), key=lambda x: x[1]['win_rate'])
print(f"Best Strategy: {best[0]} ({best[1]['win_rate']:.0%} win rate)")
EOF
```

### Are you a momentum trader or contrarian?
```bash
python3 << 'EOF'
from spy_decision_engine.utils.behavioral_analytics import BehavioralAnalytics
a = BehavioralAnalytics()
analysis = a.analyze_behavior_patterns()

momentum = analysis['strategy_breakdown'].get('MOMENTUM', {})
contrarian = analysis['strategy_breakdown'].get('CONTRARIAN', {})

print(f"Momentum: {momentum.get('total_trades', 0)} trades, {momentum.get('win_rate', 0):.0%} win")
print(f"Contrarian: {contrarian.get('total_trades', 0)} trades, {contrarian.get('win_rate', 0):.0%} win")
EOF
```

---

## 💡 Make Better Trades

### Should I size up or down based on my strategy?
```
MOMENTUM (100% win rate) → Larger position
MIXED (0% win rate)      → Avoid entirely  
CONTRARIAN (0% data)     → Mini position to test
```

### My P&L breakdown by strategy
```bash
python3 << 'EOF'
from spy_decision_engine.utils.behavioral_analytics import BehavioralAnalytics
a = BehavioralAnalytics()
analysis = a.analyze_behavior_patterns()
for strat, stats in analysis['strategy_breakdown'].items():
    pnl = stats['total_pnl']
    print(f"{strat}: ${pnl:+.0f} ({stats['win_rate']:.0%})")
print(f"\nTotal: ${analysis['overall_pnl']:+.0f}")
EOF
```

---

## 📋 Integrate Into Decision Flow

### When recording a trade
```bash
# 1. Record the trade
python3 trade_cmd.py record --ticker SPY --strike 700 --entry-premium 0.61 --reason "Momentum: bullish trend"

# 2. Check recommendation
python3 spy_decision_engine/utils/trade_recommendation_engine.py

# 3. Adjust position size if needed
# Recommendation score < 50% → Use micro position
# Recommendation score 50-70% → Use standard position  
# Recommendation score > 70% → Use larger position
```

### When closing a trade
```bash
# 1. Close the trade
python3 trade_cmd.py close --id 2026-01-13-005 --exit-premium 1.25

# 2. Update behavior analytics
python3 spy_decision_engine/utils/behavioral_analytics.py

# 3. Check if your win rate changed
# (especially important after 5-10 trades of same type)
```

---

## 🔍 Debug Commands

### Verify behavioral data is loading
```bash
python3 << 'EOF'
from spy_decision_engine.utils.behavioral_analytics import BehavioralAnalytics
a = BehavioralAnalytics()
print("✓ Behavioral analytics loaded")
analysis = a.analyze_behavior_patterns()
print(f"✓ Found {analysis['total_closed_trades']} closed trades")
print(f"✓ Found {analysis['total_open_trades']} open trades")
EOF
```

### Check if market data is available
```bash
python3 << 'EOF'
from spy_decision_engine.utils.trade_recommendation_engine import TradeRecommendationEngine
engine = TradeRecommendationEngine()
market = engine.load_market_data()
print(f"✓ Decision: {market['decision']}")
print(f"✓ Sentiment: {market['sentiment']}")
print(f"✓ Momentum: {market['momentum']}")
EOF
```

### List all strategies you've used
```bash
python3 << 'EOF'
import json
with open('spy_decision_engine/data/trades.json') as f:
    trades = json.load(f)
    strategies = set()
    for trade in trades['trades']:
        reason = trade['entry']['reason']
        strategy = reason.split(':')[0].strip().upper()
        strategies.add(strategy)
    print("Strategies used:")
    for s in sorted(strategies):
        print(f"  • {s}")
EOF
```

---

## 📊 Dashboard Integration

The dashboard automatically shows:
- Your behavioral analysis summary
- Win rates by strategy  
- Next recommended action

Refresh at: `http://localhost:8080`

Or manually update:
```bash
python3 << 'EOF'
from spy_decision_engine.utils.dashboard_updater import DashboardUpdater
DashboardUpdater().update()
EOF
```

---

## 🚀 One-Liner Power Moves

### My best performing strategy
```bash
python3 -c "from spy_decision_engine.utils.behavioral_analytics import BehavioralAnalytics; a = BehavioralAnalytics(); s = max(a.analyze_behavior_patterns()['strategy_breakdown'].items(), key=lambda x: x[1]['win_rate']); print(f'{s[0]}: {s[1][\"win_rate\"]:.0%}')"
```

### My overall P&L
```bash
python3 -c "from spy_decision_engine.utils.behavioral_analytics import BehavioralAnalytics; a = BehavioralAnalytics(); analysis = a.analyze_behavior_patterns(); print(f'${analysis[\"overall_pnl\"]:+.0f}')"
```

### Should I take this momentum trade?
```bash
python3 -c "from spy_decision_engine.utils.behavioral_analytics import BehavioralAnalytics; a = BehavioralAnalytics(); p = a.predict_trade_outcome({'reason': 'Momentum: trend following'}); print('✅ YES' if p['historical_win_rate'] > 0.5 else '❌ NO')"
```

---

**Update Frequency:** Run after each closed trade  
**Data Location:** `spy_decision_engine/reports/behavioral_analysis.json`  
**Last Sync:** When behavioral_analytics.py runs
