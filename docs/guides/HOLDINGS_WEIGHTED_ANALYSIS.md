# Holdings-Weighted Analysis for SPY Trading

## Overview

Your trading system now supports **holdings-weighted analysis** - a more granular approach to understanding SPY price movements by analyzing its top 10 holdings individually.

This technique helps you:
- Identify which major components are driving SPY movements
- Detect sector rotations before they fully impact SPY
- Find divergences between SPY and its key constituents
- Make more informed options trades

## How It Works

### Top 10 SPY Holdings (39.1% of index)

| Ticker | Company | Weight | Engines Run |
|--------|---------|--------|-------------|
| NVDA | NVIDIA Corporation | 7.73% | Momentum, Sentiment, Options |
| AAPL | Apple Inc. | 6.86% | Momentum, Sentiment, Options |
| MSFT | Microsoft Corporation | 6.13% | Momentum, Sentiment, Options |
| AMZN | Amazon.com, Inc. | 3.83% | Momentum, Sentiment, Options |
| GOOGL | Alphabet Inc. | 3.11% | Momentum, Sentiment, Options |
| AVGO | Broadcom Inc. | 2.79% | Momentum, Sentiment, Options |
| GOOG | Alphabet Inc. (Class C) | 2.49% | Momentum, Sentiment, Options |
| META | Meta Platforms, Inc. | 2.45% | Momentum, Sentiment, Options |
| TSLA | Tesla, Inc. | 2.16% | Momentum, Sentiment, Options |
| BRK-B | Berkshire Hathaway Inc. | 1.57% | Momentum, Sentiment, Options |

## Running Analysis

### Option 1: Run SPY + Holdings Analysis (Recommended)
```bash
python main_with_holdings.py
```

**What it does:**
1. Runs your standard SPY aggregate analysis
2. Analyzes each of the top 10 holdings
3. Calculates weighted average scores
4. Provides comparative summary

**Output:**
- Standard SPY reports in `spy_decision_engine/reports/`
- New `holdings_analysis.json` with individual stock breakdowns
- Console output showing how each holding contributes to SPY

### Option 2: SPY Analysis Only
```bash
python main_with_holdings.py --spy-only
```

Same as running the regular `spy_decision_engine/main.py`

### Option 3: Holdings Analysis Only
```bash
python main_with_holdings.py --holdings-only
```

Quick analysis without the full SPY aggregate analysis

## Understanding the Results

### SPY Aggregate Score
Shows traditional analysis of SPY as a whole:
```
SPY AGGREGATE ANALYSIS:
  Decision: BUY SMALL
  Score: 78.2/100
  Confidence: HIGH
```

### Holdings Breakdown
Shows contribution of each holding:
```
NVDA: 100.0 × 7.73% ÷ 39.1% = 19.8 points
AAPL: 100.0 × 6.86% ÷ 39.1% = 17.5 points
MSFT: 100.0 × 6.13% ÷ 39.1% = 15.7 points
...
TOTAL WEIGHTED SCORE: 100.0/100
```

### Interpreting Divergences

#### Example 1: Bullish Holdings, Bearish SPY
```
Holdings Score: 85.0 (strong bullish)
SPY Score: 45.0 (bearish)
```
**Interpretation:** Other SPY components (non-top-10) may be dragging down the index. Consider:
- Sector rotation happening in smaller cap stocks
- Technical support levels being tested
- Market sentiment vs. fundamentals mismatch

#### Example 2: Bearish Holdings, Bullish SPY
```
Holdings Score: 35.0 (bearish)
SPY Score: 75.0 (bullish)
```
**Interpretation:** Small/mid-cap stocks carrying momentum. Consider:
- Risk-on market sentiment
- Growth stocks underperforming
- Possible mean reversion trade

## Integration with Your Workflow

### Daily Trading Routine
1. **Morning:**
   ```bash
   python main_with_holdings.py
   ```
   
2. **Review:** 
   - Check `final_decision_summary.txt` for SPY signal
   - Check `holdings_analysis.json` for sector composition
   - Open dashboard to visualize

3. **Decision:**
   - If SPY and holdings agree → HIGH confidence trade
   - If they diverge → Check individual holdings for reasons
   - Use as input to options strategy selection

### Trade Monitoring
Keep `trade_monitor.py` running to track open positions:
```bash
python trade_monitor.py
```

The holdings analysis helps explain why your positions are moving as they are.

## Advanced Usage

### Customizing Holdings List

To analyze different holdings, edit the `TOP_10_HOLDINGS` dict in `spy_decision_engine/engines/holdings_analysis.py`:

```python
TOP_10_HOLDINGS = {
    "NVDA": ("NVIDIA Corporation", 7.73),
    "AAPL": ("Apple Inc.", 6.86),
    # Add or remove tickers here
}
```

### Individual Stock Analysis

To analyze a single holding in detail:

```python
from spy_decision_engine.context.market_context import MarketContext
from spy_decision_engine.engines.holdings_analysis import HoldingsAnalysisEngine

context = MarketContext()
engine = HoldingsAnalysisEngine()

# Get individual stock score
score = engine._calculate_holding_score("NVDA", context)
print(f"NVDA Score: {score}")
```

## Technical Details

### Scoring Methodology

For each holding, the system calculates:

1. **Base Score** - Derived from market context
   - Price position relative to 100 scale
   - Normalized to 0-100 range

2. **Sentiment Boost** - From news and FinBERT analysis
   - +20 points for strong positive sentiment
   - -20 points for strong negative sentiment
   - Scales to current market sentiment

3. **Momentum Boost** - From technical indicators
   - RSI (Relative Strength Index)
   - EMA crossovers
   - VWAP alignment
   - Scales to 0-20 points

### Weighting Algorithm

Final score for each holding:
```
Weighted Score = (Individual Score × Weight) / Total Top-10 Weight
Total Weighted Score = Sum of all weighted scores
```

This normalizes the contribution by each stock's importance in SPY.

## Output Files

After running `main_with_holdings.py`:

```
spy_decision_engine/reports/
├── holdings_analysis.json          ← Individual stock breakdown
├── final_decision.json             ← SPY aggregate decision
├── sentiment.json                  ← News sentiment (all stocks)
├── momentum.json                   ← Technical momentum
├── snapshot.json                   ← Market data snapshot
└── ... other standard reports
```

## Limitations & Future Improvements

### Current Limitations
- Uses SPY market data as proxy for individual stocks
- Doesn't fetch real-time ticker-specific data
- All holdings treated with same sensitivity to market conditions

### Planned Enhancements
1. **Real-time ticker data**
   - Fetch individual stock prices
   - Calculate individual technical indicators
   - Get stock-specific sentiment

2. **Sector rotation detection**
   - Group holdings by sector
   - Identify sector divergences
   - Track sector momentum separately

3. **Options chain analysis**
   - Analyze implied volatility per holding
   - Compare options across holdings
   - Identify correlation-based hedges

4. **Machine learning insights**
   - Train model on holdings behavior
   - Predict divergence likelihood
   - Score holdings individually

## Quick Reference

```bash
# Full analysis with holdings breakdown
python main_with_holdings.py

# Just holdings analysis (fast)
python main_with_holdings.py --holdings-only

# View reports
ls spy_decision_engine/reports/holdings_analysis.json

# Monitor trades
python trade_monitor.py

# Dashboard
python spy_decision_engine/utils/visualize_decision.py
open spy_decision_engine/reports/dashboard.html
```

---

**Questions?** Check `docs/guides/` for technical details or run `python main_with_holdings.py --help`
