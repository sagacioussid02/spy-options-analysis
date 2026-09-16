# Volume & Open Interest Tracking Quick Reference

## Quick Start (< 1 minute)

```bash
# Record a volume snapshot for your trade
python3 << 'EOF'
from spy_decision_engine.utils.volume_liquidity_tracker import VolumeLiquidityTracker
t = VolumeLiquidityTracker()
t.record_volume_snapshot("SPY", 700, "CALL", volume=20000, open_interest=50000)
print("✓ Snapshot recorded")
EOF

# Check liquidity before trading
python3 << 'EOF'
from spy_decision_engine.utils.volume_liquidity_tracker import VolumeLiquidityTracker
t = VolumeLiquidityTracker()
a = t.analyze_volume_for_trade("SPY", 700, "CALL")
print(f"Liquidity: {a['liquidity_score']:.0f}/100 - {a['recommendation']}")
EOF
```

## Command Reference

### Record Volume/OI Snapshots

**Single Snapshot:**
```python
from spy_decision_engine.utils.volume_liquidity_tracker import VolumeLiquidityTracker
tracker = VolumeLiquidityTracker()
tracker.record_volume_snapshot("SPY", 700, "CALL", volume=20000, open_interest=50000)
```

**Track Over 3 Days:**
```python
# Day 1 (Entry)
tracker.record_volume_snapshot("SPY", 700, "CALL", volume=18000, open_interest=48000)

# Day 2 (Middle)
tracker.record_volume_snapshot("SPY", 700, "CALL", volume=20000, open_interest=50000)

# Day 3 (Exit or analysis)
tracker.record_volume_snapshot("SPY", 700, "CALL", volume=22000, open_interest=52000)
```

### Analyze Liquidity

**Get Liquidity Score:**
```python
analysis = tracker.analyze_volume_for_trade("SPY", 700, "CALL")
print(analysis['liquidity_score'])  # 0-100
print(analysis['recommendation'])   # ✅ GOOD or ⚠️  POOR
```

**Get Volume Trend:**
```python
trend = tracker.get_volume_trend("SPY", 700, "CALL", days=3)
print(trend['volume']['trend'])       # INCREASING or DECREASING
print(trend['volume']['change_pct'])  # +40.0 or -15.3
```

**Compare Multiple Strikes:**
```python
comparison = tracker.compare_strike_liquidity("SPY", [695, 700, 705], "CALL")
# Shows which strikes are most liquid
for strike, volume in comparison['ranked_by_volume']:
    print(f"${strike}: {volume:,} contracts")
```

### Integration Commands

**Before Entering a Trade:**
```bash
python3 << 'EOF'
from spy_decision_engine.utils.volume_liquidity_tracker import VolumeLiquidityTracker
t = VolumeLiquidityTracker()

# Check target
analysis = t.analyze_volume_for_trade("SPY", 700, "CALL")

if analysis['liquidity_score'] >= 60:
    print(f"✅ Good liquidity ({analysis['liquidity_score']:.0f}/100) - ENTER")
else:
    print(f"⚠️  Low liquidity ({analysis['liquidity_score']:.0f}/100) - SKIP")
EOF
```

**Check Volume Performance Correlation:**
```bash
python3 spy_decision_engine/utils/liquidity_enhanced_analysis.py
```
Shows if high-liquidity trades outperform low-liquidity ones.

## Data Flow

```
Your Trade Decision
        ↓
Volume Check (liquidity_score)
        ↓
RECORD snapshot (volume, OI)
        ↓
[Wait 1-3 days]
        ↓
RECORD exit snapshot
        ↓
Analyze correlation:
   High liquidity → Better wins?
   Volume surge → Entry signal?
   OI trend → Position timing?
```

## What Gets Tracked

### Volume Metrics
- **Total Volume**: How many contracts traded today
- **Volume Trend**: Growing or declining interest
- **Volume vs Average**: 50-day moving average comparison
- **Spike Detection**: Unusual activity (>150% of avg)

### Open Interest Metrics
- **Total OI**: How many contracts currently open
- **OI Trend**: New positions or unwinding
- **OI vs Volume**: Sticky positions vs quick exit
- **Accumulation**: Institutions building positions

### Liquidity Score (0-100)
- **80-100**: Excellent (tight spread, high volume)
- **60-79**: Good (reasonable liquidity)
- **40-59**: Acceptable (moderate spread)
- **20-39**: Poor (wide spread, low volume)
- **0-19**: Avoid (illiquid, hard to exit)

## Signals Generated

```
VOLUME_SURGE        → Unusual activity, potential breakout
OI_ACCUMULATION     → Institutions buying, trend continuation
OI_DECLINE          → Unwinding positions, potential reversal
MOMENTUM_BUILDING   → Matching volume + OI increase
LIQUIDATION_RISK    → Dropping volume/OI, hard to exit
HEALTHY_LIQUIDITY   → Balanced volume and OI growth
```

## Integration Points

### 1. Trade Recording
When you record a trade, capture liquidity:
```bash
python3 trade_cmd.py record --ticker SPY --strike 700 --entry-premium 0.61 \
  --reason "Momentum trade, HIGH liquidity ($700 call 50k+ contracts)"
```

### 2. Trade Recommendation Engine
```python
# Trade scoring now includes liquidity factor
# 35% market + 35% behavioral + 20% volatility + 10% liquidity
recommendation = engine.score_trade("SPY", 700, "CALL")
```

### 3. Behavioral Analytics
```python
# Track if high/low liquidity trades perform differently
# Group historical trades by liquidity tier
analysis = behavioral_analysis.correlate_liquidity_with_wins()
```

## Common Workflows

### Workflow 1: Pre-Trade Liquidity Check
```bash
# Before entering a trade
python3 << 'EOF'
from spy_decision_engine.utils.volume_liquidity_tracker import VolumeLiquidityTracker
t = VolumeLiquidityTracker()

targets = [695, 700, 705]
for strike in targets:
    a = t.analyze_volume_for_trade("SPY", strike, "CALL")
    status = "✅" if a['liquidity_score'] >= 60 else "⚠️"
    print(f"{status} ${strike}: {a['liquidity_score']:.0f}/100")
EOF
```

### Workflow 2: Track Trade Over 3 Days
```bash
# Day 1 - Entry
python3 << 'EOF'
from spy_decision_engine.utils.volume_liquidity_tracker import VolumeLiquidityTracker
t = VolumeLiquidityTracker()
t.record_volume_snapshot("SPY", 700, "CALL", volume=20000, open_interest=50000)
print("Day 1: Snapshot recorded")
EOF

# Day 2 - Check trend
python3 << 'EOF'
from spy_decision_engine.utils.volume_liquidity_tracker import VolumeLiquidityTracker
t = VolumeLiquidityTracker()
t.record_volume_snapshot("SPY", 700, "CALL", volume=22000, open_interest=52000)
trend = t.get_volume_trend("SPY", 700, "CALL")
print(f"Day 2: {trend['volume']['trend']} {trend['volume']['change_pct']:+.1f}%")
EOF

# Day 3 - Exit and analyze
python3 << 'EOF'
from spy_decision_engine.utils.volume_liquidity_tracker import VolumeLiquidityTracker
t = VolumeLiquidityTracker()
t.record_volume_snapshot("SPY", 700, "CALL", volume=24000, open_interest=54000)
a = t.analyze_volume_for_trade("SPY", 700, "CALL")
print(f"Day 3: Liquidity {a['liquidity_score']:.0f}/100, trend {a['volume_trend']}")
EOF
```

### Workflow 3: Monthly Liquidity Performance Review
```bash
# At end of month, check if liquidity correlates with wins
python3 << 'EOF'
from spy_decision_engine.utils.liquidity_enhanced_analysis import EnhancedBehavioralAnalysis
analysis = EnhancedBehavioralAnalysis()
report = analysis.generate_liquidity_performance_report()
print(report)
EOF
```

## Files Used

- `spy_decision_engine/utils/volume_liquidity_tracker.py` - Core tracking system
- `spy_decision_engine/utils/liquidity_enhanced_analysis.py` - Performance correlation
- `spy_decision_engine/data/volume_history.json` - Volume/OI history
- `spy_decision_engine/reports/liquidity_analysis.json` - Analysis results

## Next Steps

1. **Immediate**: Set FINNHUB_API_KEY in `.env` for auto-fetching
2. **Short-term**: Record volume snapshots for your next 5 trades
3. **Medium-term**: After 5 closed trades, run liquidity analysis
4. **Long-term**: Use liquidity as 4th factor in trade scoring (after market, behavior, volatility)

## Liquidity Thresholds

Use these recommendations:

| Score | Action | Risk |
|-------|--------|------|
| 80-100 | ✅ OPTIMAL | Tight spread, easy exit |
| 60-79 | ✅ GOOD | Acceptable for trades |
| 40-59 | ⚠️ CAUTION | Wider spread, consider alternatives |
| 20-39 | ❌ AVOID | Difficult to exit |
| 0-19 | 🛑 DANGER | Illiquid, potential trap |

---

**Current System Status**: ✅ Live and tracking (manual snapshots) / ⏳ Awaiting API key for automated fetching
