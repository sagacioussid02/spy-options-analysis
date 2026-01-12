# 📝 Trade Recording Workflow - Complete Example

## Your Complete Day Trading Workflow

### Morning: Before 9:30am ET

```bash
# Step 1: Run the engine to get today's decision
cd /Users/siddharthshankar/workspace/spy
./.venv/bin/python spy_decision_engine/main.py

# Step 2: Review the decision
jq '{score: .final_score, decision: .decision, 
     entry: .entry_strategy, tp: .risk_reward.take_profit_target, 
     sl: .risk_reward.stop_loss_level}' \
  spy_decision_engine/reports/final_decision.json | jq .

# Step 3: Check option premiums (CRITICAL!)
# This shows you what option prices to expect for different strikes
./.venv/bin/python spy_decision_engine/utils/option_pricing.py

# Output should show:
# {
#   "score": 79.9,
#   "decision": "BUY SMALL",
#   "confidence": "HIGH",
#   "entry": {
#     "conservative_entry": 688.69,
#     "recommended_entry": 688.69
#   },
#   "tp": 692.32,
#   "sl": 667.15
# }
```

---

## 9:30am ET: Market Open - Time to Trade

### Decision Framework:

```bash
# Check current SPY price
# Then decide:

# If SPY is at $687-688 (support)
#   → Entry confidence: 85% → BUY CALLS
python trade_cmd.py add \
  --strike 690 \
  --dte 2 \
  --entry 688.00 \
  --premium 3.50 \
  --contracts 10 \
  --direction UP \
  --reason "Bullish momentum, at support level"

# Output: ✓ Trade added: 2026-01-07-001

# If SPY is at $689-691 (current)
#   → Entry confidence: 65% → BUY CALLS but smaller
python trade_cmd.py add \
  --strike 690 \
  --dte 2 \
  --entry 690.50 \
  --premium 2.00 \
  --contracts 5 \
  --direction UP \
  --reason "At market, less ideal entry"

# If SPY is at $692+ (resistance)
#   → Entry confidence: 30% → SKIP TODAY
echo "Skip today - at resistance, no edge"
```

---

## During Trading: 9:30am - 4:00pm ET

### Exit Rules (Set Alerts/Reminders):

```bash
# RULE 1: Quick 25% profit
# If position up 25% in first 30 min → Take it
# Example: Entry $2.50, Premium = $3.13 (+25%)
python trade_cmd.py close \
  --id 2026-01-07-001 \
  --exit 691.00 \
  --premium-sold 3.13 \
  --reason "Quick 25% profit, lock in"

# RULE 2: Half position at 50% profit
# Example: Entry $2.50, Premium = $3.75 (+50%)
python trade_cmd.py close \
  --id 2026-01-07-001 \
  --exit 691.50 \
  --premium-sold 3.75 \
  --reason "50% profit, take half off"

# RULE 3: Let winner run but with stop
# Keep remaining 50% until take profit target
# If hits stop loss ($667.15), close everything

# RULE 4: End of day
# At 3:55pm, close whatever is left
python trade_cmd.py close \
  --id 2026-01-07-001 \
  --exit 692.32 \
  --premium-sold 4.13 \
  --reason "End of day, realize profits"
```

---

## After Close: 4:00pm ET - Record Everything

### Example: Trade was profitable

```bash
# You bought 690 call at 9:35am for $2.50
# You sold at 2:45pm for $4.13
# Profit: $163 per contract × 10 = $1,630

python trade_cmd.py add \
  --strike 690 \
  --dte 2 \
  --entry 688.69 \
  --time "09:35" \
  --premium 2.50 \
  --contracts 10 \
  --confidence 79.9 \
  --direction UP \
  --reason "Bullish setup at support"

python trade_cmd.py close \
  --id 2026-01-07-001 \
  --exit 692.32 \
  --time "14:45" \
  --premium-sold 4.13 \
  --reason "Took profit at target"

# Output:
# ✓ Trade 2026-01-07-001 closed
#   Exit: $692.32 @ 14:45
#   Premium Sold: $4.13
#   Profit: $1630.00 (65.2%)
#   Result: ✓ High confidence trade worked
```

### Example: Trade was losing

```bash
# You bought 690 call at 9:40am for $2.50
# Price tanked to $688.50
# You hit stop loss and sold for $0.80

python trade_cmd.py close \
  --id 2026-01-07-002 \
  --exit 688.50 \
  --time "10:15" \
  --premium-sold 0.80 \
  --reason "Hit stop loss"

# Output:
# ✓ Trade 2026-01-07-002 closed
#   Exit: $688.50 @ 10:15
#   Premium Sold: $0.80
#   Profit: -$1700.00 (-68.0%)
#   Result: ✗ Low confidence trade failed as expected
```

---

## After Trading: View Your Results

### Check your trades for the day

```bash
python trade_cmd.py list

# Output:
# 📂 ALL TRADES (2)
# 
#   2026-01-07-001: SPY Call 690 (2 DTE)
#     Entry: $688.69 @ 09:35
#     Exit: $692.32 @ 14:45
#     P&L: $1630.00 (65.2%)
# 
#   2026-01-07-002: SPY Call 690 (2 DTE)
#     Entry: $690.50 @ 09:40
#     Exit: $688.50 @ 10:15
#     P&L: -$1700.00 (-68.0%)
```

### Get daily summary

```bash
python trade_cmd.py summary

# Output:
# ============================================================
# TRADE SUMMARY
# ============================================================
# Total Trades: 2
# Wins: 1 | Losses: 1
# Win Rate: 50.0%
# Net Profit: -$70.00
# Avg Profit/Trade: -$35.00
# Largest Win: $1630.00
# Largest Loss: -$1700.00
# Profit Factor: 0.96
# ============================================================
```

---

## After 10 Trades: Analyze Patterns

```bash
python trade_cmd.py analyze

# Output shows:
# 🎯 BEST ENTRY PRICE
#   Recommendation: Enter at support ($688-689) - 85% win rate
#
# 📅 BEST DTE
#   Recommendation: Use 2 DTE - 72% win rate
#
# 💪 CONFIDENCE THRESHOLD
#   Recommendation: Only trade when confidence > 75% (78% win rate)
#
# 🔮 PREDICTION ACCURACY
#   Overall Accuracy: 76%
#
# 📝 TRADING RULES
#   • Only trade when engine confidence > 75% (78% win rate)
#   • Prefer entry at support ($688-689)
#   • Use 2 DTE for best results
#   • Direction accuracy is 76% - track this
```

---

## Week 1-2: See Patterns Emerge

After 20-30 trades, the analyzer will show you:

```
Best Entry Price: $688-689 (support) - 82% win rate
Worst Entry Price: $692+ (resistance) - 28% win rate
Best DTE: 2 days (72% win rate)
Worst DTE: 1 day (40% win rate)

Confidence Threshold: Only trade 75%+
- At 75%+ confidence: 76% win rate ✓
- Below 75% confidence: 42% win rate ✗

Prediction Accuracy: 76% correct direction calls
Win Rate: 62%
Profit Factor: 2.1x (winning trades earn 2.1x vs losing)
```

**Key Learning**: "I make money when I:
1. Wait for support ($688-689)
2. Only trade when confidence > 75%
3. Use 2 DTE
4. Exit at targets ($692+) or stops"

---

## Commands Reference

### Add a trade
```bash
python trade_cmd.py add \
  --strike 690 \
  --dte 2 \
  --entry 688.69 \
  --premium 2.50 \
  --contracts 10
```

### Close a trade
```bash
python trade_cmd.py close \
  --id 2026-01-07-001 \
  --exit 692.32 \
  --premium-sold 4.13
```

### View trades
```bash
python trade_cmd.py list              # All trades
python trade_cmd.py list --open       # Only open trades
```

### Get summary
```bash
python trade_cmd.py summary           # Quick stats
```

### Analyze patterns
```bash
python trade_cmd.py analyze           # Full analysis + recommendations
```

---

## The Learning Loop (GAN-like)

```
1. Run engine → Get recommendation
   ↓
2. Trade based on recommendation
   ↓
3. Record result (win/loss)
   ↓
4. Analyze patterns (which prices work? which DTEs? which confidence?)
   ↓
5. Update trading rules based on data
   ↓
6. IMPROVE: Next trade uses learned rules
   ↓
7. Repeat → Engine gets "smarter" over time
```

**Example improvement**:
- Week 1: Trade anything with confidence > 60% → 42% win rate
- Week 2: Trade only at support with confidence > 75% → 78% win rate
- Week 3: Add 2 DTE preference → 85% win rate
- Week 4: Add earnings catalyst filter → 88% win rate

Your system learns and improves itself! 📈

---

## Tomorrow's Checklist

- [ ] Run engine: `python spy_decision_engine/main.py`
- [ ] Review: `jq '.entry_strategy, .risk_reward, .confidence_score' final_decision.json`
- [ ] Trade:
  - [ ] Check if SPY at support → Buy calls
  - [ ] Set exit alerts (+25%, +50%, -3%)
  - [ ] Record entry with `trade_cmd.py add`
- [ ] After close:
  - [ ] Record exit with `trade_cmd.py close`
  - [ ] View results with `trade_cmd.py summary`
- [ ] After 10+ trades:
  - [ ] Analyze patterns: `trade_cmd.py analyze`
  - [ ] Update your rules based on what works

Good luck! 🚀
