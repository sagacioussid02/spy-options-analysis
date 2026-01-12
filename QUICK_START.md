# 🚀 SPY Trading Dashboard - Quick Commands

## Start the Dashboard UI

### Easiest Way
```bash
./start_dashboard.sh
```

### Or Direct
```bash
./.venv/bin/python dashboard_server.py
```

**Then open your browser to:** `http://localhost:8080`

---

## What You'll See

✅ **Live Trading Dashboard** with:
- 📊 Current SPY price and trend
- 🎯 Final decision score (BUY/HOLD/AVOID)
- 📈 Analysis components (Momentum, Sentiment, Holdings, etc.)
- 🏢 Top 5 holdings comparison table
- 📊 Individual holdings detailed analysis
- 💼 Active trades tracking
- ⚡ Score distribution chart

---

## Update Analysis (Live)

**Click the 🔄 Update Analysis button** (top-right corner) to:

1. ✅ Rerun all analysis engines
2. ✅ Fetch fresh SPY and holdings data (yfinance)
3. ✅ Get latest news headlines (Finnhub)
4. ✅ Run FinBert sentiment analysis
5. ✅ Recalculate final decision score
6. ✅ Update dashboard automatically

**Takes:** ~30-60 seconds per analysis run

---

## Alternative: Run from Command Line

If you want to run analysis without the UI:
```bash
python spy_decision_engine/main.py
```

This generates:
- `spy_decision_engine/reports/final_decision.json` - Overall decision
- `spy_decision_engine/reports/momentum.json` - SPY momentum data
- `spy_decision_engine/reports/sentiment.json` - News sentiment
- `spy_decision_engine/reports/top_5_holdings/` - Individual holdings
- `spy_decision_engine/reports/dashboard.html` - Updated dashboard

---

## Stop the Dashboard

Press `CTRL+C` in the terminal where the server is running.

---

## Features Summary

| Feature | Details |
|---------|---------|
| **Real Data** | yfinance (stocks), Finnhub (news), FinBert (AI sentiment) |
| **Live Updates** | Click button to rerun analysis any time |
| **Holdings** | Individual analysis for NVDA, AAPL, MSFT, AMZN, GOOGL |
| **Multi-timeframe** | Momentum, sentiment, volatility, options analysis |
| **Weighted Scoring** | 28% momentum, 18% alignment, 18% event-driven, 14% sentiment, 14% volatility, 8% holdings |
| **No Mock Data** | 100% real market data, no hardcoded values |

---

## Troubleshooting

**Server won't start?**
```bash
# Kill any existing server on port 8080
lsof -i :8080
kill -9 <PID>

# Then try again
./start_dashboard.sh
```

**Analysis runs slow?**
- First run takes longer (loads FinBert model)
- Subsequent runs are faster (~30-45 seconds)
- Check internet connection for API calls

**Dashboard doesn't update?**
- Check browser console (F12) for errors
- Make sure analysis ran successfully (check terminal)
- Try a full page refresh (Cmd+R on Mac)

---

## File Structure

```
spy_decision_engine/
├── main.py                 # Main analysis orchestrator
├── reports/                # Output reports
│   ├── dashboard.html      # Interactive UI
│   ├── final_decision.json # Final score & decision
│   ├── momentum.json       # SPY momentum analysis
│   ├── sentiment.json      # News sentiment breakdown
│   ├── top_5_holdings/     # Individual holding analysis
│   └── ...other reports
├── engines/                # Analysis engines
├── utils/                  # Utilities (data fetch, scoring, etc.)
└── config.py              # Configuration & API keys

dashboard_server.py         # Web server (serves UI + handles updates)
start_dashboard.sh         # Quick start script
```
