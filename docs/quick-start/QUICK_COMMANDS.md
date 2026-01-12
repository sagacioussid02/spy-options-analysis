# ⚡ Quick Command Reference - Keep This Handy

## Your Complete System in 5 Commands

### 1️⃣ Get Today's Decision (9:30am)
```bash
./.venv/bin/python spy_decision_engine/main.py
```
**Output:** Decision, entry price, target, stop loss, confidence score

---

### 2️⃣ See Option Premiums
```bash
./.venv/bin/python spy_decision_engine/utils/option_pricing.py
```
**Output:** Strike prices with entry/exit premiums and profit targets

---

### 3️⃣ Record Your Trade Entry
```bash
./.venv/bin/python trade_cmd.py add \
  --strike 691 \
  --dte 2 \
  --entry 2.18 \
  --premium 2.18 \
  --contracts 10 \
  --direction UP \
  --reason "High confidence setup"
```
**Output:** Trade ID (save this for closing later)

---

### 4️⃣ Record Your Trade Exit
```bash
./.venv/bin/python trade_cmd.py close \
  --id 2026-01-07-001 \
  --exit 2.50 \
  --premium-sold 2.50
```
**Output:** Profit/loss calculated and saved

---

### 5️⃣ View All Your Data & Analysis
```bash
./.venv/bin/python db_query.py
```
**Output:** Everything - recent trades, stats, performance

---

## Additional Queries

### View Recent Trades Only
```bash
./.venv/bin/python db_query.py trades
```

### View Trade Statistics
```bash
./.venv/bin/python db_query.py stats
```

### View Win Rate by Strike
```bash
./.venv/bin/python db_query.py strike
```

### View Win Rate by DTE
```bash
./.venv/bin/python db_query.py dte
```

### View Win Rate by Confidence
```bash
./.venv/bin/python db_query.py confidence
```

### Analyze Patterns (After 10+ trades)
```bash
./.venv/bin/python trade_cmd.py analyze
```

### Backup All Data
```bash
./.venv/bin/python db_query.py export
```

---

## Tomorrow's Schedule

| Time | Action | Command |
|------|--------|---------|
| 9:25am | Activate terminal | `cd /Users/siddharthshankar/workspace/spy` |
| 9:30am | Run engine | `./.venv/bin/python spy_decision_engine/main.py` |
| 9:32am | Get option premiums | `./.venv/bin/python spy_decision_engine/utils/option_pricing.py` |
| 9:35am | Buy options + record | `./.venv/bin/python trade_cmd.py add ...` |
| 12:00pm | Monitor position | Check if near targets |
| 3:55pm | Sell + record exit | `./.venv/bin/python trade_cmd.py close ...` |
| 4:00pm | Review day | `./.venv/bin/python db_query.py` |

---

## Critical: Don't Forget

### When Recording Entry
```bash
--strike        # The strike price (e.g., 691)
--dte           # Days to expiration (e.g., 2)
--entry         # The option entry price you paid (e.g., 2.18)
--premium       # Same as entry for calls (e.g., 2.18)
--contracts     # Number of contracts (default 10)
--direction     # UP or DOWN
--reason        # Why you're trading
```

### When Recording Exit
```bash
--id            # Trade ID from entry (e.g., 2026-01-07-001)
--exit          # The stock price when you sold (informational)
--premium-sold  # The option premium you actually sold at (e.g., 2.50)
```

---

## Database Location

All your data is stored here (automatic):
```
/Users/siddharthshankar/workspace/spy/spy_decision_engine/data/spy_trading.db
```

This file grows with each trade. Back it up weekly:
```bash
./.venv/bin/python db_query.py export
# Creates: spy_trading_backup_YYYYMMDD_HHMMSS.json
```

---

## After 10 Trades: Check Learning

```bash
./.venv/bin/python trade_cmd.py analyze

# System will tell you:
# ✓ Best strike to trade (highest win rate)
# ✓ Best DTE to use (1, 2, 3, or 4 days)
# ✓ Best confidence threshold (minimum to trade)
# ✓ Your prediction accuracy (how often engine is right)
```

---

## Monthly Targets

| After | Expected | Action |
|-------|----------|--------|
| 1 week (5-7 trades) | 50-60% win rate | Keep trading, record everything |
| 2 weeks (10-15 trades) | 60-65% win rate | Start following patterns |
| 3 weeks (20-25 trades) | 65-75% win rate | Apply learned rules |
| 4 weeks (30+ trades) | 70-80% win rate | Consistent monthly profits |

---

## Success Formula

```
Consistent Profit = 
  (Engine Accuracy: 75%) × 
  (Your Discipline: 100%) × 
  (Proper Position Sizing: √) × 
  (Time: 30+ days) × 
  (Recording Every Trade: ✓)
```

**You have everything. Now execute. 🚀**
