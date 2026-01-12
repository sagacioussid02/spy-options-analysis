# 📊 SPY Options Premium Guide

## Quick Answer: What Option Price Should I Buy?

**Stock prices from engine:**
- Current: $691.81
- Recommended entry: $688.69  
- Take profit target: $692.32

**But what's the option PREMIUM?**

When you trade options, you pay a "premium" (price) for that contract. This premium changes based on:
1. **How far the strike is from current price** (ATM, ITM, OTM)
2. **Days to expiration** (1-4 DTE)
3. **Volatility** (market turbulence)
4. **How much you expect the stock to move**

---

## Today's Premium Table

Based on your engine decision (BUY CALLS, target $692.32, 2 DTE):

### 📈 SPY Call Options

| Strike | Type | Entry Price | At Target | Profit | ROI | B/E Stock |
|--------|------|-------------|-----------|--------|-----|-----------|
| **$689** | ITM -2 | $3.55 | $3.95 | +$40 | 11% | $692.55 |
| **$690** | ITM -1 | $2.82 | $3.18 | +$36 | 13% | $692.82 |
| **$691** | ATM ⭐ | $2.18 | $2.50 | +$32 | 15% | $693.18 |
| **$692** | OTM +1 | $1.63 | $1.90 | +$27 | 16% | $693.63 |
| **$693** | OTM +2 | $1.18 | $1.40 | +$22 | 19% | $694.18 |
| **$694** | OTM +3 | $0.83 | $1.00 | +$17 | 21% | $694.83 |

### What Each Column Means:

- **Strike**: The price level of the option (e.g., $691 call = profit if SPY > $691)
- **Type**: 
  - ITM = In The Money (strike is below current price) - Expensive but safer
  - ATM = At The Money (strike is at current price) - Sweet spot
  - OTM = Out The Money (strike is above current price) - Cheap but risky
- **Entry Price**: What you PAY today to buy 1 contract (multiply by 100 for real dollars: $2.18 × 100 = $218)
- **At Target**: What it will be worth if SPY hits $692.32 target (premium value, not stock price)
- **Profit**: Dollar profit per contract if you exit at target price (100 shares)
  - $691 call: You pay $2.18, can sell for $2.50, profit = $0.32 × 100 = $32
- **ROI**: Return on investment %
  - $691 call: ($0.32 / $2.18) = 14.5% profit
- **B/E Stock**: Stock price where you break even (entry premium + strike)
  - $691 call with $2.18 premium: B/E = $691 + $2.18 = $693.18
  - Means: SPY must go to $693.18+ just to not lose money

---

## Real-World Example: Which Strike to Buy?

### Scenario: It's 9:30am, SPY is at $691.81

**Engine says:**
- Target: $692.32 (only $0.51 move!)
- Confidence: HIGH
- Decision: BUY CALLS

**Option pricing shows:**
- $691 call (ATM): Buy at $2.18, sell at $2.50 = $32 profit, 15% ROI ✓
- $692 call (OTM): Buy at $1.63, sell at $1.90 = $27 profit, 16% ROI ✓
- $694 call (OTM): Buy at $0.83, sell at $1.00 = $17 profit, 21% ROI (risky - needs bigger move)

**Recommendation:**
```
👉 BUY $691 CALLS at $2.18/contract
   Reason: ATM has best balance - reasonable cost, good profit potential
   Alternative: $692 calls if you want cheaper entry (smaller profit but similar ROI)
```

---

## Key Insight: Entry Price ≠ Stock Price

**WRONG:** "I buy SPY at $688.69"
- That's the **stock price target**, not the option price

**RIGHT:** "I buy $691 call option at $2.18"
- That's the **option premium** you actually pay
- You pay $2.18 × 100 = $218 per contract
- If you buy 10 contracts: $218 × 10 = $2,180 total

---

## Calculating Your Profit

### Example Trade:

```
Step 1: BUY $691 Call
  Current SPY: $691.81
  Entry Price (premium): $2.18/contract
  Number of contracts: 10
  Total cost: $2.18 × 100 × 10 = $2,180

Step 2: WAIT for SPY to hit target
  Target: $692.32
  Expected $691 call premium: $2.50
  
Step 3: SELL $691 Call
  Exit Price (premium): $2.50/contract
  Contracts sold: 10
  Total revenue: $2.50 × 100 × 10 = $2,500

Step 4: PROFIT
  Gross profit: $2,500 - $2,180 = $320
  ROI: 14.5%
```

---

## Command to Get Today's Premiums

```bash
# In the morning, run this to see exact premiums:
./.venv/bin/python spy_decision_engine/utils/option_pricing.py

# Output shows:
# - Current SPY price
# - Target price
# - All strikes with entry/exit premiums
# - Your recommended strike (usually ATM)
```

---

## Strike Selection Strategy

### 🟢 Conservative (Lower Risk)
- Buy **ITM** (In The Money) calls
- More expensive ($3-4)
- But already profitable if you hold to expiration
- Good if: You're unsure about direction

### 🟡 Balanced (Recommended)
- Buy **ATM** (At The Money) calls  ⭐
- Moderate cost ($2-2.50)
- Good profit potential without being too risky
- Good if: You have high confidence in the move

### 🔴 Aggressive (Higher Risk/Reward)
- Buy **OTM** (Out The Money) calls
- Cheap ($0.80-1.50)
- But needs bigger stock move to profit
- Good if: You're very confident + willing to lose

---

## Why Not Just Buy OTM and Get 21% ROI?

The $694 call has 21% ROI vs 15% for $691.

**But:** It only makes money if SPY hits $694+
- Engine target: $692.32
- Need: $694 (extra $1.68 move)
- If SPY only goes to $692.32, $694 call expires worthless
- Your $83 loss = $0 profit

**vs. $691 call at target:**
- Profitable if SPY just hits $692+ (which is the target!)

**Lesson:** Higher ROI means higher risk. The recommended strike matches your engine's target.

---

## How to Use This Daily

### Morning (before 9:30am):
```bash
# Get today's premium table
./.venv/bin/python spy_decision_engine/utils/option_pricing.py

# Shows:
# Strike   Entry $   Target $   Profit   ROI
# $691     $2.18     $2.50      $32      15% ← Usually here
# $692     $1.63     $1.90      $27      16%
# $694     $0.83     $1.00      $17      21% ← Only if very confident
```

### At market open:
```bash
# Check current SPY vs entry price
# Buy recommended strike at shown entry premium
# Set exit order at target premium or stop loss

Example:
  Current SPY: $691.81
  Buy: $691 call for $2.18 (or better)
  Exit: $2.50 (take profit) or $0.80 (stop loss)
```

### After close:
```bash
# Record what you actually paid/sold at
python trade_cmd.py add \
  --strike 691 \
  --entry 2.18 \
  --dte 2 \
  --premium 2.18

python trade_cmd.py close \
  --id 2026-01-07-001 \
  --exit 2.50
```

---

## Table of Examples

### If Engine Says BUY CALLS:

| SPY Scenario | Best Strike | Entry Cost | Target | Profit | Why |
|--------------|-------------|-----------|--------|--------|-----|
| At support ($688-689) | $690 | $2.82 | $3.18 | +$36 | Safe + high confidence |
| At current ($691) | $691 ATM | $2.18 | $2.50 | +$32 | Balanced |
| At resistance ($693+) | SKIP | - | - | - | Low probability |

### If Engine Says BUY PUTS (rare):

| SPY Scenario | Best Strike | Entry Cost | Target | Profit | Why |
|--------------|-------------|-----------|--------|--------|-----|
| At resistance | $691 | $2.18 | $2.50 | +$32 | Mirror of calls |
| Near all-time high | $690 | $2.82 | $3.18 | +$36 | More conviction |

---

## Common Mistakes to Avoid

❌ **MISTAKE 1:** Confusing stock price with option premium
- "I'll buy SPY at $688.69" → That's the stock target, not option price
- ✓ **CORRECT:** "I'll buy $690 call for $2.82"

❌ **MISTAKE 2:** Always buying OTM because ROI is higher
- OTM $694 call has 21% ROI but needs $1.68 move
- ✓ **CORRECT:** Buy ATM/ITM that aligns with your target

❌ **MISTAKE 3:** Not accounting for Greeks (delta, gamma, theta)
- As stock price changes, premium doesn't move 1:1
- Engine shows estimated Greeks
- ✓ **CORRECT:** Use pricing table which accounts for this

❌ **MISTAKE 4:** Ignoring breakeven stock price
- $691 call needs SPY > $693.18 to not lose money
- Your target is only $692.32
- ✓ **CORRECT:** Choose a strike where breakeven < your target (usually ATM works)

---

## Summary: Option Premium Cheat Sheet

| Need | Action | Tool |
|------|--------|------|
| See today's premiums | Run `python spy_decision_engine/utils/option_pricing.py` | Terminal |
| Know which strike to buy | Look at "RECOMMENDED STRIKE" in output | Output shows it |
| Understand entry cost | Multiply premium by 100 × contracts wanted | Mental math |
| Know exit premium (profit) | Look at "Target $" column at your target price | Table |
| Track your actual trades | Use `python trade_cmd.py add/close` | CLI |
| See if your prices match theory | After trade, compare to pricing table | Retrospective |

---

## Real Data Example

From today's engine (Jan 6, 2026):

```
BUY CALLS
Current SPY: $691.81
Recommended Entry: $688.69 (wait for dip)
Take Profit: $692.32

Option Premiums:
  $689 call: Buy $3.55, Sell $3.95 = +$40 profit
  $690 call: Buy $2.82, Sell $3.18 = +$36 profit
  $691 call: Buy $2.18, Sell $2.50 = +$32 profit ⭐ RECOMMENDED
  $692 call: Buy $1.63, Sell $1.90 = +$27 profit
```

**Tomorrow when market opens:**
1. Check if SPY hit recommended entry ($688.69) or near it
2. If YES: Buy $691 calls for around $2.18 each
3. If NO: Wait or consider $690 calls (safer)
4. Set exit order to sell at $2.50 or stop loss at $0.80

Done! 📈
