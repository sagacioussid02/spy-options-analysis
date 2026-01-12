# 📊 Database System Guide

Your SPY trading system now has a **complete database** that stores:
- All engine runs (daily decisions)
- All trades (entry/exit details)
- Analysis results
- Daily performance summaries

Everything is automatically saved to a **local SQLite database** (no setup needed!).

---

## Database Features

### ✅ What Gets Stored Automatically

1. **Engine Runs** - Every time you run the decision engine:
   - Daily decision (BUY/SELL/HOLD)
   - Confidence score
   - Current SPY price
   - Recommended entry & take profit targets
   - All component scores
   - Full report JSON

2. **Trades** - When you record trades with `trade_cmd.py`:
   - Entry date/time/price/premium
   - Strike price and DTE
   - Number of contracts
   - Engine confidence at entry
   - Exit date/time/price/premium (when closed)
   - Profit/loss and ROI
   - Direction (UP for calls, DOWN for puts)

3. **Analysis Results** - After analyzing trades:
   - Win rates by strike, DTE, confidence level
   - Prediction accuracy
   - Recommendations

4. **Daily Performance** - End-of-day summary:
   - Trades entered/closed
   - Daily P&L
   - Win rate for the day
   - Engine decision & confidence

---

## How It Works

### Step 1: Engine Saves Decision

```bash
./.venv/bin/python spy_decision_engine/main.py
# Automatically saves to: spy_decision_engine/data/spy_trading.db
```

**What's saved:**
- Timestamp, decision, score, confidence
- SPY price, entry targets, take profit, stop loss
- All component scores (momentum, sentiment, volatility)
- Full decision report (JSON)

### Step 2: You Record Trades

```bash
# Add entry
./.venv/bin/python trade_cmd.py add \
  --strike 691 \
  --dte 2 \
  --entry 2.18 \
  --premium 2.18 \
  --contracts 10

# Close trade
./.venv/bin/python trade_cmd.py close \
  --id 2026-01-06-001 \
  --exit 2.50 \
  --premium-sold 2.50
```

**What's saved:**
- Trade ID, entry/exit date/time
- Strike, DTE, premium, contracts
- Engine confidence at entry
- Profit/loss automatically calculated
- Marked as OPEN or CLOSED

### Step 3: Query Database Anytime

```bash
./.venv/bin/python db_query.py [command]
```

---

## Query Commands

### 📊 View Recent Engine Runs
```bash
./.venv/bin/python db_query.py runs
```

Shows last 20 engine decisions with timestamps and targets.

### 📈 View Recent Trades
```bash
./.venv/bin/python db_query.py trades
```

Shows all trades (open and closed) with entry/exit prices and profit.

### 🔴 View Open Trades
```bash
./.venv/bin/python db_query.py open
```

Only shows trades that haven't been closed yet.

### 📊 Overall Statistics
```bash
./.venv/bin/python db_query.py stats
```

Shows:
- Total trades
- Win/loss count
- Win rate %
- Total profit/loss
- Average profit per trade
- Profit factor

### 🎯 Win Rate By Strike
```bash
./.venv/bin/python db_query.py strike
```

Shows which strikes have been most profitable:
```
Strike   Trades  Wins  Win Rate  Total Profit  Avg ROI
$689     5       4     80.0%     $125.00       18.5%
$691     8       6     75.0%     $200.00       14.2%
$694     3       1     33.3%     -$50.00       -8.3%
```

**Insight:** $689 calls work better than $694 calls

### 📅 Win Rate By DTE
```bash
./.venv/bin/python db_query.py dte
```

Shows which expiration works best:
```
DTE   Trades  Wins  Win Rate  Total Profit  Avg ROI
1     10      3     30.0%     -$120.00      -3.2%  ← Risky!
2     15      11    73.3%     $550.00       15.7%  ← Good!
3     8       6     75.0%     $380.00       14.1%
4     5       4     80.0%     $280.00       12.5%
```

**Insight:** 2 DTE has the best win rate (73%)

### 💪 Win Rate By Confidence
```bash
./.venv/bin/python db_query.py confidence
```

Shows if engine confidence predicts wins:
```
Confidence Range  Trades  Wins  Win Rate  Total Profit  Avg ROI
80-100%           10      9     90.0%     $550.00       18.2%  ← Strong!
70-80%            12      8     66.7%     $200.00       8.5%
60-70%            8       4     50.0%     -$50.00       -1.2%
<60%              5       1     20.0%     -$100.00      -6.0%  ← Weak
```

**Insight:** Only trade when confidence > 80%

### 📅 Daily Performance
```bash
./.venv/bin/python db_query.py daily
```

Shows daily P&L summary for trend analysis:
```
Date       Trades  Win Rate  Daily P&L  Decision       Confidence
2026-01-06 3       66.7%     $240.00    BUY SMALL      80%
2026-01-05 2       100.0%    $450.00    BUY MEDIUM     85%
2026-01-04 1       0.0%      -$80.00    BUY SMALL      65%
```

### 💾 Export All Data
```bash
./.venv/bin/python db_query.py export
```

Creates backup JSON file with all data:
- All engine runs
- All trades
- All analysis
- All stats
- Timestamps

Example output: `spy_trading_backup_20260106_224500.json`

---

## Real-World Example Workflow

### Monday Morning (9:30am)

```bash
# 1. Run the engine
./.venv/bin/python spy_decision_engine/main.py

# Output: Decision: BUY SMALL, Confidence: 79.9%, Target: $692.32

# 2. Check your historical performance first
./.venv/bin/python db_query.py stats

# Output: Win Rate: 73%, Profit: $1,240, Best: $691 strike, 2 DTE

# 3. See what worked best
./.venv/bin/python db_query.py dte

# Output: 2 DTE: 73% win rate vs 1 DTE: 30% win rate
```

### During Market (10:15am)

```bash
# 4. Check option premiums
./.venv/bin/python spy_decision_engine/utils/option_pricing.py

# Output: Buy $691 call at $2.18, expect to sell at $2.50 (15% ROI)

# 5. Buy the options and record the trade
./.venv/bin/python trade_cmd.py add \
  --strike 691 \
  --dte 2 \
  --entry 2.18 \
  --premium 2.18 \
  --contracts 10

# Output: Trade 2026-01-06-001 added and saved to DB
```

### Afternoon (2:45pm)

```bash
# 6. Hit take profit target, close the trade
./.venv/bin/python trade_cmd.py close \
  --id 2026-01-06-001 \
  --exit 2.50 \
  --premium-sold 2.50

# Output: Profit $320 (14.7%), saved to DB
```

### End of Day (4:00pm)

```bash
# 7. Check today's summary
./.venv/bin/python db_query.py open

# Output: No open trades (all closed)

# 8. View all trades with database
./.venv/bin/python db_query.py trades

# Output: Shows all trades (today + history)

# 9. See updated statistics
./.venv/bin/python db_query.py stats

# Output: Win Rate: 75%, Updated profit: $1,560, etc.
```

### Weekly Review (Friday)

```bash
# Check weekly performance
./.venv/bin/python db_query.py daily

# Check what strikes worked best this week
./.venv/bin/python db_query.py strike

# Check if DTE preference changed
./.venv/bin/python db_query.py dte

# Export all data for analysis
./.venv/bin/python db_query.py export
```

---

## Database File Location

```
/Users/siddharthshankar/workspace/spy/spy_decision_engine/data/spy_trading.db
```

This is a single SQLite file. You can:
- **Backup**: Copy this file anywhere
- **Analyze**: Use any SQLite viewer (DB Browser for SQLite, etc.)
- **Share**: Email to yourself for analysis
- **Restore**: Copy back to restore history

---

## Database Schema

### engine_runs table
Stores daily decisions from the engine.

| Column | Type | Content |
|--------|------|---------|
| timestamp | TEXT | When decision was made |
| decision | TEXT | BUY SMALL, BUY MEDIUM, HOLD, etc. |
| final_score | REAL | 0-100 confidence |
| spy_price | REAL | Current SPY price |
| recommended_entry | REAL | Entry price target |
| take_profit | REAL | Target take profit price |
| stop_loss | REAL | Stop loss price |

### trades table
Stores all trade entries/exits.

| Column | Type | Content |
|--------|------|---------|
| trade_id | TEXT | Unique ID like 2026-01-06-001 |
| entry_date | TEXT | Date of entry |
| strike | REAL | Strike price ($691, etc.) |
| dte | INT | Days to expiration (1-4) |
| premium_paid | REAL | Entry premium ($2.18) |
| premium_sold | REAL | Exit premium ($2.50) |
| contracts | INT | Number of contracts |
| profit | REAL | Profit/loss in dollars |
| profit_pct | REAL | ROI percentage |
| is_open | INT | 1 = open, 0 = closed |

### analysis_results table
Stores win rate analysis by strikes, DTEs, etc.

### daily_performance table
Stores end-of-day summaries.

---

## Tips for Using the Database

### 1️⃣ Always backup your database before big changes
```bash
cp spy_decision_engine/data/spy_trading.db ~/backups/spy_trading_backup.db
```

### 2️⃣ Export data regularly for analysis
```bash
./.venv/bin/python db_query.py export
# Use the JSON in Excel/Google Sheets for charts
```

### 3️⃣ Query before trading
```bash
# Before trading, check what's been working:
./.venv/bin/python db_query.py stats
./.venv/bin/python db_query.py strike
./.venv/bin/python db_query.py confidence
```

### 4️⃣ Track daily P&L
```bash
./.venv/bin/python db_query.py daily
# Shows daily profit/loss + win rates
```

### 5️⃣ Find your winning pattern
```bash
# After 20+ trades, you'll see:
# - Best strike: $689-690 (80% win rate)
# - Best DTE: 2 days (73% win rate)
# - Best confidence: > 80% (90% win rate)

# Use this to improve your entries!
```

---

## What Happens Over Time

### Week 1: Just tracking
- Record every trade
- Database builds history
- No clear patterns yet

### Week 2-3: Patterns emerge
```
Best Entry: $689 calls (80% win)
Best DTE: 2 days (73% win)
Best Confidence: > 80% (90% win)
Worst: $694 OTM calls (30% win)
```

### Week 4+: You become smarter
- Only trade your winning patterns
- Skip your losing patterns
- System gets better each day
- Win rate improves steadily

---

## Commands Quick Reference

| Want to... | Run... |
|------------|--------|
| Record an entry | `./.venv/bin/python trade_cmd.py add --strike 691 --dte 2 --entry 2.18 --premium 2.18 --contracts 10` |
| Close a trade | `./.venv/bin/python trade_cmd.py close --id 2026-01-06-001 --exit 2.50 --premium-sold 2.50` |
| See all trades | `./.venv/bin/python db_query.py trades` |
| See statistics | `./.venv/bin/python db_query.py stats` |
| See best strike | `./.venv/bin/python db_query.py strike` |
| See best DTE | `./.venv/bin/python db_query.py dte` |
| See if confidence matters | `./.venv/bin/python db_query.py confidence` |
| See daily P&L | `./.venv/bin/python db_query.py daily` |
| Backup data | `./.venv/bin/python db_query.py export` |

---

## Summary

Your system now has **persistent, queryable data** of:
- ✅ Every decision the engine makes
- ✅ Every trade you execute
- ✅ Complete win/loss analysis
- ✅ Strike-by-strike performance
- ✅ DTE performance trends
- ✅ Confidence accuracy tracking

This means **you learn from every single trade** and the system improves over time! 📈
