# SPY Decision Engine - Enhancement Summary

## 📊 Recent Updates (January 6, 2026)

### 1. Dual API News Integration ✅
**What Changed**: 
- `get_news_headlines()` now fetches from BOTH **Finnhub** and **NewsAPI**
- Combines stock-specific financial news (Finnhub) with general market context (NewsAPI)
- Automatic fallback if either API fails

**Files Updated**: `utils/data_fetcher.py`

**Benefits**:
- More comprehensive news coverage
- Better detection of catalysts affecting SPY holdings
- Reduced reliance on single API

---

### 2. Per-Stock Sentiment Analysis ✅
**What Changed**:
- Sentiment engine now calculates individual scores for **top 10 SPY stocks** + SPY itself
- Tracks: NVIDIA, Apple, Microsoft, Amazon, Meta, Google, Tesla, Berkshire, JPMorgan, SPY
- Each stock gets: sentiment score, mention count, positive/negative counts, recent headlines

**Output Structure**:
```json
"by_stock": {
  "NVIDIA": {
    "score": 0.5,
    "mentions": 5,
    "positive": 1,
    "negative": 1,
    "recent_headlines": [...]
  },
  ...
}
```

**Files Updated**: `engines/news_sentiment.py`

**Benefits**:
- See which holdings have positive/negative sentiment
- Identify lagging stocks in otherwise bullish market
- Better weighted decision-making per stock

---

### 3. Enhanced Final Decision Report ✅
**What Changed**:
Final decision now includes **20+ new parameters**:

#### Market Conditions
- SPY price, trend, RSI, EMAs, VWAP, VIX
- All key technical indicators in one place

#### Stock Sentiment Analysis
- Ranked list of stocks by sentiment score
- Shows which holdings are in the news

#### Entry Strategy
- Conservative entry (wait for dip to support)
- Current entry (buy now at market)
- Risky entry (near resistance)
- **Recommended entry** based on all factors

#### Position Management
- Position size recommendation (SMALL to LARGE)
- Volatility-adjusted rationale
- Risk per trade (in dollars)

#### Options Greeks (Estimated)
- Delta, Gamma, Theta, Vega
- Note: These are approximations; check actual broker prices

#### Risk/Reward Analysis
- Entry price
- Take profit target (at resistance)
- Stop loss level
- Risk/reward ratio (e.g., "1:0.17")

#### Time Decay
- Days to expiry
- Daily theta decay estimate
- Theta warning level

#### Bullish/Bearish Factors
- Lists all positive signals supporting the decision
- Lists all negative signals against the decision

#### Confidence Score
- Confidence value (0-100)
- What drives confidence up or down

#### Upcoming Catalysts
- Reference to PREDICTION_MARKETS.md
- Next monitoring steps

**Files Updated**: `engines/final_decision.py`

**Sample Output**:
```json
{
  "final_score": 79.9,
  "decision": "BUY SMALL",
  "confidence": "HIGH",
  "entry_strategy": {
    "conservative_entry": 688.69,
    "current_entry": 691.81,
    "recommended_entry": 688.69
  },
  "position_management": {
    "size_recommendation": "MEDIUM-LARGE (20-25%)",
    "risk_per_trade": 85832.51
  },
  "risk_reward": {
    "take_profit_target": 692.32,
    "stop_loss_level": 667.15,
    "risk_reward_ratio": "1:0.17"
  },
  "bullish_factors": [
    "Bullish trend (EMA-9: 686.44)",
    "Price above VWAP",
    "RSI in sweet spot: 63.5",
    ...
  ]
}
```

---

### 4. Prediction Markets Guide ✅
**What Changed**:
Created comprehensive guide: `PREDICTION_MARKETS.md`

**Covers**:
- **PredictIt**: Real-money market for political/economic events
- **Polymarket**: Decentralized market for tech/earnings predictions
- **Kalshi**: Event contracts/derivatives
- **Manifold Markets**: Community-driven forecasts

**Free Alternatives**:
- Fed decision calendar
- Earnings calendars (Yahoo, Investing.com, CNBC)
- Economic event calendars

**How to Use**:
1. Check if NVIDIA beats earnings this quarter (Jan 29)
2. Monitor Fed rate decision probability (Jan 29)
3. Track AI regulation news
4. Alert on major tech announcements

**Integration Examples**:
- Option 1: Manual weekly review
- Option 2: Automate via API calls
- Incorporate event probabilities into final_decision.json

---

## 📈 Current Decision Example

**Input Data**:
- SPY: $691.81 (bullish trend)
- EMA-9: $686.44, EMA-21: $683.68 (bullish cross)
- RSI: 63.5 (not overbought)
- VIX: 14.8 (low volatility)
- Sentiment: +5 headlines, -3 headlines (62% positive)

**Per-Stock Sentiment**:
- Apple: 1.0 (very positive)
- Berkshire: 1.0 (very positive)
- NVIDIA: 0.5 (mixed)
- Meta: 0.5 (neutral)
- Tesla: 0.5 (mixed)

**Output Decision**:
```
Final Score: 79.9/100
Decision: BUY SMALL
Confidence: HIGH
Recommended Entry: $688.69 (wait for dip)
Take Profit: $692.32
Stop Loss: $667.15
Position Size: 20-25%
Risk/Reward: 1:0.17
```

---

## 🎯 Reports Available

All reports saved to `/reports/`:

1. **snapshot.json** - Market snapshot with individual stock changes
2. **sentiment.json** - Overall + per-stock sentiment analysis
3. **momentum.json** - Technical indicators (EMA, RSI, VWAP, price)
4. **price_analysis.json** - OHLCV data, entry prices, Greeks estimates
5. **volatility.json** - VIX data and options environment
6. **options.json** - Options premium, bid/ask, Greeks
7. **final_decision.json** - Comprehensive decision with all parameters

---

## 🚀 Next Steps / Optional Enhancements

### Short-term
1. ✅ Dual API news integration - DONE
2. ✅ Per-stock sentiment - DONE
3. ✅ Enhanced final decision - DONE
4. ✅ Prediction markets guide - DONE
5. 🟡 Manual prediction market monitoring (check weekly)

### Medium-term
1. Automate event probability fetching from Polymarket API
2. Add earnings calendar integration
3. Implement position tracking in database
4. Create historical performance tracking

### Long-term
1. Machine learning for sentiment weighting
2. Backtesting framework for strategy validation
3. Real-time alert system
4. Integration with trading platforms (Alpaca, TD Ameritrade)

---

## 📋 Configuration Notes

### .env File Requirements
```
FINNHUB_API_KEY=your_key_from_finnhub.io
NEWS_API_KEY=your_key_from_newsapi.org
```

Both are free tier with no credit card required for basic usage.

### API Rate Limits
- **Finnhub**: 60 calls/min (free tier)
- **NewsAPI**: 100 calls/day (free tier)
- **yfinance**: Unlimited (no API key needed)

---

## 📚 Documentation Files

- **QUICK_REFERENCE.md** - Quick start guide
- **blueprint.md** - Original architecture blueprint
- **PREDICTION_MARKETS.md** - Event catalyst tracking guide
- **README.md** - Technical documentation
- **FINNHUB_SETUP.md** - Finnhub API setup guide

---

## 🔍 How to Use the Enhanced Decision

### For Daily Trading
1. Run: `python spy_decision_engine/main.py`
2. Read: `reports/final_decision.json`
3. Key fields to check:
   - `decision`: BUY/SELL/HOLD
   - `recommended_entry`: Where to buy
   - `risk_reward_ratio`: Is it worth it?
   - `bullish_factors`: Confirm the thesis
   - `bearish_factors`: Identify risks

### For Risk Management
1. Check `risk_reward` section for stop loss
2. Adjust `position_management.size_recommendation`
3. Monitor `time_decay.theta_daily` if holding close to expiry
4. Review `bearish_factors` before entering

### For Opportunity Hunting
1. Track `stock_sentiment_analysis` - which stocks are hot?
2. Monitor `upcoming_catalysts` - when are earnings/Fed decisions?
3. Compare `by_stock` sentiment to find divergences
4. Use divergences as trade setups

---

Generated: January 6, 2026
Version: 2.1 (Enhanced with per-stock sentiment, prediction markets, comprehensive decision)
