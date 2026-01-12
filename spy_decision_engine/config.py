"""
Global configuration for the SPY decision engine.
"""
import os

# Directory paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPORTS_DIR = os.path.join(BASE_DIR, "reports")
DATA_DIR = os.path.join(BASE_DIR, "data")
CACHE_DIR = os.path.join(DATA_DIR, "cache")
RAW_DATA_DIR = os.path.join(DATA_DIR, "raw")

# Top SPY contributors to track
TOP_STOCKS = ["NVDA", "AAPL", "MSFT", "AMZN", "META", "GOOGL", "TSLA", "BRK-B"]

# Technical indicators settings
EMA_9_PERIOD = 9
EMA_21_PERIOD = 21
RSI_PERIOD = 14

# Momentum thresholds
RSI_BULLISH_MIN = 50
RSI_BULLISH_MAX = 80

# Volatility thresholds
VIX_HIGH_THRESHOLD = 20.0
IV_PERCENTILE_HIGH_THRESHOLD = 70

# Option parameters (can be overridden)
DEFAULT_OPTION_STRIKE = 688
DEFAULT_OPTION_EXPIRY = "2026-01-09"
DEFAULT_OPTION_TYPE = "CALL"

# News sentiment keywords
POSITIVE_KEYWORDS = [
    "beat", "beats", "surge", "jump", "gain", "profit", "strong",
    "bullish", "upside", "positive", "success", "growth", "soar",
    "rally", "upgrade", "outperform", "record", "new high",
    "momentum", "breakout", "rally", "recovery", "buy",
    "innovation", "launches", "new product", "announcement",
    "earnings beat", "revenue growth", "margin expansion"
]

NEGATIVE_KEYWORDS = [
    "miss", "decline", "drop", "loss", "weak", "bearish",
    "downside", "negative", "fail", "crash", "plunge", "concern",
    "selloff", "downgrade", "underperform", "warning", "risk",
    "recession", "slowdown", "weakness", "sell", "headwind",
    "earnings miss", "disappointing", "challenges", "pressure"
]
