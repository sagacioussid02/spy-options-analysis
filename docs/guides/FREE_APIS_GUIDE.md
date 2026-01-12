# Free APIs Integration Guide

Your SPY Decision Engine now uses **100% free APIs** for real market data!

## ✅ What's Integrated

| Data Source | API | Free? | API Key Required? |
|------------|-----|-------|-------------------|
| Stock prices, historical data, options | **yfinance** | ✅ Yes | ❌ No |
| News headlines | **NewsAPI** | ✅ Yes (free tier) | ✅ Yes (free) |
| VIX (volatility index) | **yfinance** | ✅ Yes | ❌ No |
| Technical indicators | Calculated locally | ✅ Yes | ❌ No |

---

## 🚀 Quick Setup

### 1. The virtual environment already has dependencies installed:

```bash
# Already done! But if you need to reinstall:
python -m pip install yfinance requests
```

### 2. (Optional) Set up NewsAPI for real news headlines:

Get a **free API key** (no credit card needed):
1. Visit: https://newsapi.org
2. Sign up → Verify email
3. Copy your API key from dashboard
4. Set environment variable:

```bash
export NEWS_API_KEY="your_key_here"
```

Or add to shell config (`~/.bashrc`, `~/.zshrc`, etc.):
```bash
echo 'export NEWS_API_KEY="sk_xxx..."' >> ~/.bashrc
source ~/.bashrc
```

### 3. Run the engine:

```bash
cd /Users/siddharthshankar/workspace/spy/spy_decision_engine
python main.py
```

---

## 📊 What Each API Provides

### **yfinance** (No API key needed)
Free, unlimited. Gets real market data:

```python
import yfinance as yf

# Stock prices and changes
spy = yf.Ticker("SPY").info
print(spy["currentPrice"], spy["regularMarketChangePercent"])

# Historical data for technical analysis
hist = yf.Ticker("SPY").history(period="3mo")
prices = hist["Close"].tolist()

# Options chain
opts = yf.Ticker("SPY").option_chain("2026-01-09")
calls = opts.calls  # bid, ask, volume, open_interest
puts = opts.puts

# VIX (volatility)
vix = yf.Ticker("^VIX").history(period="1d")
```

**Updated functions:**
- `get_market_data()` – Real SPY + top 8 stocks
- `get_historical_spy_data()` – Real 3-month historical data
- `get_vix()` – Real VIX values
- `get_option_chain_data()` – Real options pricing
- `get_spy_iv_percentile()` – Estimated from option spreads

### **NewsAPI** (Free tier, optional)
Free tier: 100 requests/day, 1 month history

```python
import requests

api_key = os.getenv("NEWS_API_KEY")
url = "https://newsapi.org/v2/everything"
params = {
    "q": "NVDA",
    "sortBy": "publishedAt",
    "language": "en",
    "pageSize": 2,
    "apiKey": api_key
}
response = requests.get(url, params=params)
headlines = [a["title"] for a in response.json()["articles"]]
```

**Updated function:**
- `get_news_headlines()` – Real headlines or mock fallback

---

## 🛡️ Fallback Behavior

All functions gracefully fallback to **mock data** if:
- API is unavailable
- Network error occurs
- No API key set (NewsAPI only)
- Rate limit exceeded

Example log messages:
```
WARNING:utils.data_fetcher:NEWS_API_KEY environment variable not set. Using mock headlines.
WARNING:utils.data_fetcher:Error fetching market data: [error]
```

---

## 📈 Real Data Example

When you run `python main.py`, you get **actual market data**:

### Snapshot Report (Real data from yfinance)
```json
{
  "timestamp": "21:56",
  "stocks": {
    "NVDA": {"change_pct": -0.45, "volume_ratio": 0.94, "price": 187.24},
    "AAPL": {"change_pct": -1.83, "volume_ratio": 0.87, "price": 262.36},
    ...
  },
  "green_count": 4,
  "red_count": 4,
  "alignment_score": 0.5
}
```

### Momentum Report (Real indicators from historical prices)
```json
{
  "trend": "BULLISH",
  "ema_cross": true,
  "rsi": 63.5,
  "above_vwap": true,
  "indicators": {
    "ema_9": 686.44,
    "ema_21": 683.68,
    "vwap": 676.04,
    "current_price": 691.81
  }
}
```

---

## 🔧 Implementation Details

### How Data Flows

```
Market Snapshot Engine:
  → yf.Ticker("SPY").info
  → yf.Ticker(stock_name).info for each top stock
  → Writes real prices, changes, volumes to snapshot.json

SPY Momentum Engine:
  → yf.Ticker("SPY").history(period="3mo")
  → Calculates EMA, RSI, VWAP from real historical data
  → Writes real technical indicators to momentum.json

Volatility Filter:
  → yf.Ticker("^VIX").history()
  → yf.Ticker("SPY").option_chain() for IV percentile
  → Writes to volatility.json

Options What-If:
  → yf.Ticker("SPY").option_chain(expiry)
  → Finds closest strike, extracts bid/ask/volume
  → Writes to options.json

News Sentiment:
  → newsapi.org/v2/everything (if NEWS_API_KEY set)
  → Fallback to mock headlines
  → Writes to sentiment.json
```

---

## ⚠️ Rate Limits

### yfinance
- **No official rate limit**, but respect the service
- Recommended: Max 1-2 requests per minute per ticker
- Current implementation: ~10 tickers, ~1 request per run ✅

### NewsAPI (Free tier)
- **100 requests per day**
- **1 month historical data**
- Current implementation: ~8 stocks × 2 articles = 16 requests per run ✅
- Plenty of room: 100 requests ÷ 16 per run = ~6 runs per day

---

## 🐛 Troubleshooting

### "ModuleNotFoundError: No module named 'yfinance'"
```bash
# Install packages
python -m pip install yfinance requests

# Or with venv
/Users/siddharthshankar/workspace/spy/.venv/bin/python -m pip install yfinance requests
```

### "WARNING: NEWS_API_KEY environment variable not set"
This is **normal**. The engine will use mock headlines. To enable real headlines:
```bash
export NEWS_API_KEY="sk_xxx..."
python main.py
```

### "Error fetching market data"
Usually a temporary network issue. Check:
1. Internet connection
2. yfinance server status
3. Try again in a few seconds

Mock data will be used automatically.

### Options data missing or zeros
yfinance returns zeros when:
- Market is closed (options markets close before stock markets)
- Option is deep out-of-the-money
- Low volume on that strike

This is normal. The engine handles it gracefully.

---

## 💡 Next Steps

1. **Run with real data:**
   ```bash
   cd spy_decision_engine
   python main.py
   ```

2. **(Optional) Enable news headlines:**
   ```bash
   export NEWS_API_KEY="your_key"
   python main.py
   ```

3. **Schedule daily runs:**
   ```bash
   # Every day at 9:30 AM (market open)
   0 9 * * 1-5 cd /path/to/spy && python main.py
   ```

4. **Monitor the reports:**
   - `reports/snapshot.json` – Daily market status
   - `reports/momentum.json` – Technical indicators
   - `reports/final_decision.json` – Recommendation

---

## 📝 Code Reference

**File:** [`utils/data_fetcher.py`](../spy_decision_engine/utils/data_fetcher.py)

Key functions:
- `get_market_data()` – Real stock prices
- `get_news_headlines()` – Real headlines or mock
- `get_historical_spy_data()` – Real 3-month SPY data
- `get_vix()` – Real VIX
- `get_spy_iv_percentile()` – IV percentile estimate
- `get_option_chain_data()` – Real options prices

All with graceful fallbacks to mock data.

---

## ✅ Free APIs - Complete!

Your engine now has:
- ✅ Real stock market data (yfinance)
- ✅ Real technical indicators (calculated from real prices)
- ✅ Real volatility data (VIX, IV)
- ✅ Real options chains (bid/ask/volume)
- ✅ Optional real news headlines (NewsAPI free tier)

**All using free APIs with no paid tiers required!**
