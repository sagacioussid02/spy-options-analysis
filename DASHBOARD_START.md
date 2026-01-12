# SPY Trading Dashboard - Quick Start

## Starting the Dashboard

### Option 1: Using the bash script (Recommended)
```bash
./start_dashboard.sh
```

### Option 2: Direct Python
```bash
./.venv/bin/python dashboard_server.py
```

## Access the Dashboard

Once the server starts, open your browser to:
```
http://localhost:8080
```

You'll see:
- 📊 Live SPY trading analysis
- 🏢 Top 5 holdings comparison
- 📊 Individual holdings detailed analysis
- 💼 Active trades tracking
- 📈 Component score charts

## Update Analysis Button

Click the **🔄 Update Analysis** button (top-right corner) to:
1. ✓ Rerun all analysis engines
2. ✓ Fetch fresh market data
3. ✓ Recalculate all scores
4. ✓ Update dashboard automatically

The analysis will:
- Fetch real yfinance data (SPY, holdings prices)
- Get fresh Finnhub news headlines
- Run FinBert sentiment analysis
- Recalculate momentum, sentiment, holdings scores
- Update your final trading decision

Takes approximately 30-60 seconds per run.

## What Runs When You Click Update

The button executes: `python spy_decision_engine/main.py`

This runs all analysis stages:
1. **Market Snapshot** - Current market conditions
2. **News Sentiment** - FinBert analysis of headlines
3. **SPY Momentum** - Price, RSI, EMA, VWAP
4. **Event-Driven** - Major market-moving events
5. **Price Analysis** - Support/resistance, entry levels
6. **Volatility Filter** - VIX and options environment
7. **Options Analysis** - What-if scenario analysis
8. **Final Decision** - Weighted score calculation
9. **Holdings Analysis** - Top 5 holdings individual analysis
10. **Dashboard Update** - Regenerates HTML with new data

## Stopping the Server

Press `CTRL+C` in the terminal to stop the server.

## Troubleshooting

**Port 8080 already in use?**
```bash
# Find process using port 8080
lsof -i :8080

# Kill it
kill -9 <PID>
```

**Flask not found?**
The script will auto-install Flask on first run.

**Analysis failed?**
- Check your internet connection (needs yfinance & Finnhub)
- Verify Finnhub API key is set in config.py
- Check logs in the terminal

## Browser Tips

- **Refresh** (Cmd+R on Mac) - Full page reload
- **Update Analysis** button - Reruns analysis and updates live
- **Open DevTools** (Cmd+Option+I) - Check for any errors
