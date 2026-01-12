# Finnhub API Integration Guide

## Overview
Finnhub provides better financial news than the free tier of NewsAPI. The integration upgrades sentiment analysis with real financial headlines.

## Setup Steps

### 1. Get Free API Key
- Visit: https://finnhub.io
- Sign up with email (free tier available)
- Go to Dashboard → API Keys
- Copy your API key

### 2. Add to .env File
Add this line to `.env`:
```
FINNHUB_API_KEY=your_api_key_here
```

Replace `your_api_key_here` with your actual key.

### 3. Test the Integration
Run the engine:
```bash
cd /Users/siddharthshankar/workspace/spy
source .venv/bin/activate
python spy_decision_engine/main.py
```

Check the output in `reports/sentiment.json` - it should now contain real financial headlines instead of PyPI package releases.

## API Limits (Free Tier)
- 60 API calls per minute
- Unlimited requests per month
- Good for our use case (we fetch news ~30 times/month)

## Fallback Behavior
If `FINNHUB_API_KEY` is not set or API fails:
- System automatically falls back to mock financial headlines
- No errors - just uses predefined headlines for testing
- You can still run the engine for development

## Headlines Covered
The integration fetches news for top SPY holdings:
- NVDA (NVIDIA)
- AAPL (Apple)
- MSFT (Microsoft)
- AMZN (Amazon)
- META (Meta/Facebook)
- GOOGL (Google/Alphabet)
- TSLA (Tesla)
- BRK-B (Berkshire Hathaway)

## What Changed
- **Before:** NewsAPI free tier returned PyPI packages, bundle deals, entertainment articles
- **Now:** Finnhub returns actual financial news (earnings, product launches, market analysis)
- **Result:** Sentiment analysis now works correctly with relevant financial headlines

## Common Issues

### Issue: "FINNHUB_API_KEY not set"
**Solution:** 
```bash
# Check .env file exists and has the key
cat .env | grep FINNHUB

# Or set directly in terminal
export FINNHUB_API_KEY="your_key_here"
python spy_decision_engine/main.py
```

### Issue: "Invalid API key"
**Solution:**
- Copy key again from https://finnhub.io/dashboard/api-keys
- Make sure no extra spaces: `FINNHUB_API_KEY=abc123xyz`

### Issue: Still getting mock headlines
**Reason:** API key is not set OR network error
**Check:** Look for warning messages in console output
**Solution:** Verify .env file is in correct location: `/Users/siddharthshankar/workspace/spy/.env`
