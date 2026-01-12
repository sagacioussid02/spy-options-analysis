# SPY Options Decision Engine

A local, modular Python application that helps you decide whether to buy short-term SPY options (calls or puts). This is a **human decision support system**, not an auto-trader.

## 🎯 What It Does

The engine runs 6 independent analysis engines in sequence:

1. **Market Snapshot** – Tracks top SPY contributors (NVDA, AAPL, MSFT, etc.)
2. **News Sentiment** – Analyzes recent headlines using keyword-based sentiment
3. **SPY Momentum** (Critical Gate) – Checks technical conditions (EMA, RSI, VWAP)
   - If momentum fails, trading is NOT recommended
4. **Volatility Filter** – Penalizes options in high VIX/IV environments
5. **Options What-If** – Simulates premium behavior over 3 days
6. **Final Decision** – Aggregates all signals into a single recommendation

Each engine writes its output to both:
- A shared `MarketContext` object (for inter-engine communication)
- A JSON report in `/reports`

## 🚀 Quick Start

### Prerequisites
```bash
# Install free APIs (yfinance, requests)
pip install yfinance requests

# Optional: Set up NewsAPI for real headlines
export NEWS_API_KEY="your_free_key_from_newsapi.org"
```

### Run
```bash
cd spy_decision_engine
python3 main.py
```

See [FREE_APIS_GUIDE.md](../FREE_APIS_GUIDE.md) for detailed setup.

## 📊 Output

The system produces **6 JSON reports**:

- `snapshot.json` – Market alignment and top stock movements
- `sentiment.json` – News sentiment analysis
- `momentum.json` – Technical indicators (EMA, RSI, VWAP)
- `volatility.json` – VIX and IV analysis
- `options.json` – Option premium scenarios
- `final_decision.json` – Final recommendation and reasoning

## 🧠 Decision Formula

```
final_score = 0.35 * momentum_score
            + 0.25 * alignment_score
            + 0.20 * sentiment_score
            + 0.20 * (1 - volatility_penalty)
```

Scores are interpreted as:
- **75+** → "BUY SMALL" (High confidence)
- **60–74** → "BUY MICRO" (Medium confidence)
- **40–59** → "HOLD / PASS" (Neutral)
- **25–39** → "AVOID" (Medium confidence)
- **<25** → "DO NOT TRADE" (High confidence)

## 📁 Architecture

```
spy_decision_engine/
├── main.py                      # Orchestrator
├── config.py                    # Configuration & thresholds
│
├── context/
│   └── market_context.py        # Shared data object
│
├── engines/
│   ├── market_snapshot.py       # Engine 1
│   ├── news_sentiment.py        # Engine 2
│   ├── spy_momentum.py          # Engine 3 (Gate)
│   ├── volatility_filter.py     # Engine 4
│   ├── options_whatif.py        # Engine 5
│   └── final_decision.py        # Engine 6
│
├── utils/
│   ├── data_fetcher.py          # Mock data sources
│   ├── indicators.py            # Technical calculations
│   └── scoring.py               # Decision logic
│
├── reports/
│   ├── snapshot.json
│   ├── sentiment.json
│   ├── momentum.json
│   ├── volatility.json
│   ├── options.json
│   └── final_decision.json
│
└── data/
    ├── cache/                   # Cached data
    └── raw/                     # Raw data files
```

## ⚙️ Key Thresholds

Edit `config.py` to adjust:

```python
# Technical indicator periods
EMA_9_PERIOD = 9
EMA_21_PERIOD = 21
RSI_PERIOD = 14

# Bullish conditions
RSI_BULLISH_MIN = 50
RSI_BULLISH_MAX = 80

# Volatility thresholds
VIX_HIGH_THRESHOLD = 20.0
IV_PERCENTILE_HIGH_THRESHOLD = 70

# Option defaults
DEFAULT_OPTION_STRIKE = 688
DEFAULT_OPTION_EXPIRY = "2026-01-09"
DEFAULT_OPTION_TYPE = "CALL"
```

## 🔄 Engine Interface

Every engine implements this contract:

```python
class YourEngine:
    def run(self, context: MarketContext) -> None:
        # 1. Fetch/analyze data
        # 2. Write results to context
        context.your_output = {...}
        # 3. Write JSON report to /reports
```

## � Current Implementation

**Data Sources (All FREE):**
- **yfinance** (free, no API key) – Real-time stock prices, historical data, options, VIX
- **NewsAPI** (free tier, optional API key) – News headlines
- All calculations done locally

**Sentiment Analysis:**
- Simple keyword matching (no NLP libraries)
- Positive/negative word lists in `config.py`

**Technical Indicators:**
- EMA (Exponential Moving Average) – from real historical prices
- RSI (Relative Strength Index) – from real historical prices
- VWAP (Volume Weighted Average Price) – from real volumes

**Graceful Fallbacks:**
- If APIs unavailable, automatically uses mock data
- Engine continues to run with mock data until APIs return

## 🛑 Critical Gate

The **SPY Momentum Engine** is a critical gate:

```
If trade_allowed == False:
    ❌ Skip all downstream engines
    ❌ No options analysis
    ❌ No final decision
    
Otherwise:
    ✅ Run volatility, options, and final decision engines
```

This prevents trading in bearish environments.

## 💡 Example Output

```
Final Score: 90.3/100
Decision: BUY SMALL
Confidence: HIGH

Reasoning:
  • SPY momentum is bullish (EMA + VWAP aligned)
  • Top holdings are well-aligned and positive
  • News sentiment is positive
  • Volatility environment is favorable for options
```

## 🔧 Extending the System

To add a new engine:

1. Create `engines/your_engine.py`
2. Implement the `run(context)` method
3. Write results to `context` and JSON file
4. Add to `main.py` orchestration flow

Example:

```python
from engines.your_engine import YourEngine

# In main.py
YourEngine().run(context)
```

## ⚠️ Disclaimers

- **NOT an auto-trader** – decisions are human-reviewed recommendations
- **NO real-money execution** – for analysis only
- **Local only** – no cloud deployment
- **v1 Rule-based** – no machine learning in this version

## 📚 References

- Technical indicators: [Investopedia](https://www.investopedia.com/)
- RSI interpretation: [0-30 = Oversold, 70-100 = Overbought]
- VIX: [Stock market volatility index]
- IV Percentile: [Historical volatility percentile]

---

Built as a modular, human-readable decision support system for SPY options analysis.
