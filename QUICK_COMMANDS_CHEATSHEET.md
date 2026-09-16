# SPY Trading System - Quick Commands Cheatsheet

**Fast reference for common operations. All commands run from `/Users/siddharthshankar/workspace/spy`**

---

## 🚀 START HERE

### Launch Dashboard Server
```bash
./start_dashboard.sh
# Or manually:
python3 dashboard_server.py
# Then open: http://localhost:8080
```

### Run Full Analysis
```bash
python3 main_with_holdings.py
# Generates all reports and auto-updates dashboard
```

### Quick Analysis (SPY only, no holdings)
```bash
python3 -c "from spy_decision_engine.main import run_analysis; run_analysis('SPY')"
```

---

## 📊 Trade Management

### Record a New Trade
```bash
python3 trade_cmd.py record --ticker SPY --strike 700 --entry-premium 0.61 --contracts 1 --reason "Contrarian bet"
# Full format with all options shown above
```

### Record Trade (Minimal)
```bash
python3 trade_cmd.py record --ticker SPY --strike 700 --entry-premium 0.61
```

### List All Trades
```bash
python3 trade_cmd.py list
```

### List Open Trades Only
```bash
python3 trade_cmd.py list --status open
```

### List Closed Trades Only
```bash
python3 trade_cmd.py list --status closed
```

### Check Specific Trade Status
```bash
python3 trade_cmd.py status --id 2026-01-13-005
```

### Close a Trade (Profit)
```bash
python3 trade_cmd.py close --id 2026-01-13-005 --exit-premium 1.25 --reason "Target hit"
```

### Close a Trade (Loss)
```bash
python3 trade_cmd.py close --id 2026-01-13-005 --exit-premium 0.30 --reason "Stop loss"
```

### View Trade P&L Summary
```bash
python3 trade_cmd.py summary
```

---

## 📈 Analysis & Reports

### Analyze All Holdings (Top 5)
```bash
python3 analyze_all_holdings.py
```

### Analyze Individual Holding
```bash
python3 -c "from spy_decision_engine.main import run_analysis; run_analysis('NVDA')"
# Replace NVDA with: AAPL, MSFT, AMZN, or GOOGL
```

### Generate Holdings Comparison
```bash
python3 top_5_holdings_analysis.py
```

### Query Database
```bash
python3 db_query.py
# Interactive prompt to query stored analysis
```

### View Momentum Analysis
```bash
python3 -c "import json; print(json.dumps(json.load(open('spy_decision_engine/reports/momentum.json')), indent=2))"
```

### View Sentiment Analysis
```bash
python3 -c "import json; print(json.dumps(json.load(open('spy_decision_engine/reports/sentiment.json')), indent=2))"
```

### View Final Decision
```bash
python3 -c "import json; print(json.dumps(json.load(open('spy_decision_engine/reports/final_decision.json')), indent=2))"
```

---

## 🔄 Dashboard Operations

### Update Dashboard Manually
```bash
python3 << 'EOF'
from spy_decision_engine.utils.dashboard_updater import DashboardUpdater
DashboardUpdater().update()
EOF
```

### View Dashboard HTML File
```bash
open spy_decision_engine/reports/dashboard.html
# Or open in your browser: file:///Users/siddharthshankar/workspace/spy/spy_decision_engine/reports/dashboard.html
```

---

## 🗃️ Data & Configuration

### View Current Trades (JSON)
```bash
cat spy_decision_engine/data/trades.json | python3 -m json.tool
```

### Check SPY Current Price
```bash
python3 -c "from yfinance import download; print(download('SPY', period='1d')['Close'].iloc[-1])"
```

### Check Holdings Current Prices
```bash
python3 -c "from yfinance import download; print(download('NVDA AAPL MSFT AMZN GOOGL', period='1d')['Close'].iloc[-1])"
```

### View Cache Files
```bash
ls -la spy_decision_engine/data/cache/
```

### Clear Cache
```bash
rm -rf spy_decision_engine/data/cache/*
# Next analysis will fetch fresh data
```

### Check Configuration
```bash
cat spy_decision_engine/config.py
```

---

## 🔧 Monitoring & Troubleshooting

### Monitor Live SPY Price
```bash
watch -n 1 'python3 -c "from yfinance import download; print(download(\"SPY\", period=\"1d\")[\"Close\"].iloc[-1])"'
```

### Check Dashboard Server Status
```bash
lsof -i :8080
# Kill if needed: kill -9 <PID>
```

### Test Finnhub Connection
```bash
python3 -c "from spy_decision_engine.utils.data_fetcher import get_news; print(get_news('SPY')[:1])"
```

### Test FinBert Sentiment
```bash
python3 -c "from spy_decision_engine.utils.finbert_sentiment import analyze_sentiment; print(analyze_sentiment('This is great news for the market'))"
```

### View Error Logs
```bash
tail -50 spy_decision_engine/reports/final_decision.txt
```

### Run Full Test Suite
```bash
bash scripts/test_full_workflow.sh
```

---

## 📋 Common Workflows

### Morning Routine (Full Update)
```bash
# 1. Run full analysis
python3 main_with_holdings.py

# 2. Check new recommendation
python3 -c "import json; d=json.load(open('spy_decision_engine/reports/final_decision.json')); print(f\"Decision: {d['decision']} | Score: {d['final_score']} | Confidence: {d['confidence']}\")"

# 3. Open dashboard to review
open http://localhost:8080
```

### Record Trade After Analysis
```bash
# After reviewing dashboard and decision:
python3 trade_cmd.py record --ticker SPY --strike 700 --entry-premium 0.61 --contracts 1 --reason "Based on latest analysis"
```

### End of Day Review
```bash
# 1. List all trades with status
python3 trade_cmd.py list

# 2. Update holdings analysis
python3 analyze_all_holdings.py

# 3. View P&L
python3 trade_cmd.py summary
```

### Close Profitable Trade
```bash
# After monitoring position:
python3 trade_cmd.py close --id 2026-01-13-005 --exit-premium 1.25 --reason "Target hit at resistance"
# Dashboard auto-updates to show closed trade
```

### Setup New Day
```bash
# Clear old cache, run fresh analysis
rm -rf spy_decision_engine/data/cache/*
python3 main_with_holdings.py
# Dashboard now shows fresh analysis
```

---

## 🌍 Environment Setup

### Install Dependencies (One Time)
```bash
pip3 install -r requirements.txt
```

### Set API Keys (.env file)
```bash
cp .env.example .env
# Edit .env and add:
# FINNHUB_API_KEY=your_key_here
# OPENROUTER_API_KEY=your_key_here (optional for GPT integration)
```

### Verify API Keys Loaded
```bash
python3 -c "from spy_decision_engine.config import FINNHUB_API_KEY; print('✅ Finnhub configured' if FINNHUB_API_KEY else '❌ Missing API key')"
```

---

## 📚 Documentation Links

- **Full Setup Guide**: See [DASHBOARD_START.md](DASHBOARD_START.md)
- **Database Guide**: See [docs/guides/DATABASE_GUIDE.md](docs/guides/DATABASE_GUIDE.md)
- **Free APIs Setup**: See [docs/guides/FREE_APIS_GUIDE.md](docs/guides/FREE_APIS_GUIDE.md)
- **Daily Workflow**: See [docs/workflows/DAILY_WORKFLOW.md](docs/workflows/DAILY_WORKFLOW.md)

---

## ⚡ Speed Tips

| Task | Command | Time |
|------|---------|------|
| Start dashboard | `./start_dashboard.sh` | 2 sec |
| Run analysis | `python3 main_with_holdings.py` | 30-45 sec |
| Record trade | `python3 trade_cmd.py record ...` | 1 sec |
| Check decision | `python3 -c "import json; ..."` | 1 sec |
| View dashboard | Open `http://localhost:8080` | Instant |

---

## 🐛 Common Issues

**Dashboard not updating?**
```bash
# Restart server:
pkill -f dashboard_server.py
./start_dashboard.sh
```

**Trade not showing on dashboard?**
```bash
# Rebuild dashboard:
python3 -c "from spy_decision_engine.utils.dashboard_updater import DashboardUpdater; DashboardUpdater().update()"
```

**API key error?**
```bash
# Check .env file exists with valid key:
cat .env | grep FINNHUB_API_KEY
```

**Analysis not updating?**
```bash
# Clear cache and re-run:
rm -rf spy_decision_engine/data/cache/*
python3 main_with_holdings.py
```

---

**Last Updated**: January 13, 2026
**Active Tickers**: SPY (main), NVDA, AAPL, MSFT, AMZN, GOOGL (holdings)
