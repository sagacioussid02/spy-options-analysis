"""
Data fetcher utilities for market data using FREE APIs.

APIs Used:
- yfinance: Free, no API key. For stock prices, historical data, options, VIX
- Finnhub: Free tier. Better for financial news. Get API key from https://finnhub.io

To get Finnhub key: https://finnhub.io (free tier available)
Set environment variable: export FINNHUB_API_KEY="your_key_here"
Or add to .env file: FINNHUB_API_KEY=your_key_here
"""
import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
import logging

# Load .env file if it exists
try:
    from dotenv import load_dotenv
    env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
    load_dotenv(env_path)
except ImportError:
    pass  # dotenv not installed, will use environment variables

# Setup logging
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

# Try to import yfinance, fallback to mock if not available
try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False
    logger.warning("yfinance not installed. Install with: pip install yfinance")

# Try to import requests for NewsAPI
try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    logger.warning("requests not installed. Install with: pip install requests")


def get_market_data() -> Dict:
    """
    Fetch real market data for SPY and top contributors using yfinance.
    Falls back to mock data if yfinance unavailable.
    """
    if not YFINANCE_AVAILABLE:
        logger.warning("Using mock data - install yfinance: pip install yfinance")
        return _get_mock_market_data()
    
    try:
        stocks_to_track = ["SPY", "NVDA", "AAPL", "MSFT", "AMZN", "META", "GOOGL", "TSLA", "BRK-B"]
        data = {
            "timestamp": datetime.now().strftime("%H:%M"),
            "spy_price": None,
            "spy_change": None,
            "stocks": {}
        }
        
        for ticker in stocks_to_track:
            try:
                tick = yf.Ticker(ticker)
                info = tick.info
                
                price = info.get("currentPrice") or info.get("regularMarketPrice", 0)
                change_pct = info.get("regularMarketChangePercent", 0)
                volume = info.get("volume", 0)
                
                if ticker == "SPY":
                    data["spy_price"] = round(price, 2)
                    data["spy_change"] = round(change_pct, 2)
                else:
                    # Get volume ratio (current volume vs average)
                    avg_volume = info.get("averageVolume", volume)
                    volume_ratio = volume / avg_volume if avg_volume > 0 else 1.0
                    
                    data["stocks"][ticker] = {
                        "change_pct": round(change_pct, 2),
                        "volume_ratio": round(volume_ratio, 2),
                        "price": round(price, 2),
                    }
            except Exception as e:
                logger.warning(f"Error fetching {ticker}: {e}")
                continue
        
        return data
    
    except Exception as e:
        logger.error(f"Error fetching market data: {e}")
        return _get_mock_market_data()


def _get_mock_market_data() -> Dict:
    """Mock market data fallback."""
    return {
        "timestamp": datetime.now().strftime("%H:%M"),
        "spy_price": 688.42,
        "spy_change": 0.85,
        "stocks": {
            "NVDA": {"change_pct": 1.2, "volume_ratio": 1.4, "price": 142.3},
            "AAPL": {"change_pct": -0.3, "volume_ratio": 0.9, "price": 243.1},
            "MSFT": {"change_pct": 0.6, "volume_ratio": 1.1, "price": 441.2},
            "AMZN": {"change_pct": 0.9, "volume_ratio": 1.3, "price": 198.5},
            "META": {"change_pct": 1.5, "volume_ratio": 1.5, "price": 619.2},
            "GOOGL": {"change_pct": 0.4, "volume_ratio": 1.0, "price": 177.8},
            "TSLA": {"change_pct": -0.8, "volume_ratio": 0.8, "price": 324.1},
            "BRK-B": {"change_pct": 0.2, "volume_ratio": 0.7, "price": 462.5},
        }
    }


def get_news_headlines(ticker: str = "SPY") -> List[str]:
    """
    Fetch financial news from both Finnhub and NewsAPI (free tiers).
    Finnhub: optimized for stock market news
    NewsAPI: general news source for broader market context
    Falls back to mock data if APIs unavailable.
    
    Args:
        ticker: Stock ticker to fetch news for (default: SPY for market context)
    """
    if not REQUESTS_AVAILABLE:
        logger.warning("Using mock headlines - install requests: pip install requests")
        return _get_mock_headlines()
    
    headlines_list = []
    
    # Try Finnhub first (better for stock-specific news)
    finnhub_key = os.getenv("FINNHUB_API_KEY")
    if finnhub_key:
        headlines_list.extend(_fetch_finnhub_headlines(finnhub_key, ticker))
    
    # Also try NewsAPI (for broader market context)
    news_key = os.getenv("NEWS_API_KEY")
    if news_key and ticker == "SPY":  # Only use broader context for SPY
        headlines_list.extend(_fetch_newsapi_headlines(news_key))
    
    if headlines_list:
        logger.info(f"Fetched {len(headlines_list)} headlines for {ticker} from APIs")
        # Remove duplicates while preserving order
        seen = set()
        unique_headlines = []
        for h in headlines_list:
            if h not in seen:
                seen.add(h)
                unique_headlines.append(h)
        return unique_headlines[:25]  # Return top 25 unique headlines
    else:
        if not finnhub_key and not news_key:
            logger.warning("No API keys found (FINNHUB_API_KEY, NEWS_API_KEY). Using mock headlines.")
            logger.info("Get free keys: https://finnhub.io and https://newsapi.org")
        else:
            logger.warning("Failed to fetch from APIs. Using mock headlines.")
        return _get_mock_headlines()


def _fetch_finnhub_headlines(api_key: str, ticker: str = "SPY") -> List[str]:
    """Fetch headlines from Finnhub for specific ticker or all SPY holdings.
    
    Args:
        api_key: Finnhub API key
        ticker: Specific ticker to fetch for, or "SPY" for all holdings
    """
    headlines = []
    
    # If specific ticker requested, fetch only for that ticker
    if ticker != "SPY":
        symbols = [ticker]
    else:
        # For SPY, fetch news for market and top holdings
        symbols = ["SPY", "NVDA", "AAPL", "MSFT", "AMZN", "META", "GOOGL", "TSLA", "BRK.B", "JNJ"]
    
    for symbol in symbols:
        try:
            url = "https://finnhub.io/api/v1/company-news"
            params = {
                "symbol": symbol,
                "from": (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d"),
                "to": datetime.now().strftime("%Y-%m-%d"),
                "token": api_key
            }
            
            response = requests.get(url, params=params, timeout=5)
            if response.status_code == 200:
                articles = response.json()
                if articles:
                    # For specific ticker, get more articles; for market context get fewer
                    num_articles = 5 if ticker != "SPY" else 2
                    for article in articles[:num_articles]:
                        headline = article.get("headline", "")
                        if headline:
                            headlines.append(headline)
        except Exception as e:
            logger.debug(f"Finnhub error for {symbol}: {e}")
            continue
    
    return headlines


def _fetch_newsapi_headlines(api_key: str) -> List[str]:
    """Fetch headlines from NewsAPI for market context."""
    headlines = []
    
    try:
        url = "https://newsapi.org/v2/everything"
        params = {
            "q": "(stock market OR Fed OR earnings OR IPO OR crypto OR tech stocks) AND (breaking OR news)",
            "sortBy": "publishedAt",
            "language": "en",
            "pageSize": 20,
            "apiKey": api_key,
            "from": (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d"),
        }
        
        response = requests.get(url, params=params, timeout=5)
        if response.status_code == 200:
            articles = response.json().get("articles", [])
            for article in articles[:10]:
                title = article.get("title", "")
                if title and len(title) > 20:  # Filter out very short titles
                    # Basic filter to avoid obvious non-news
                    if not any(term in title.lower() for term in ["github", "version", "release 0.", "npm package"]):
                        headlines.append(title)
    except Exception as e:
        logger.debug(f"NewsAPI error: {e}")
    
    return headlines


def _get_mock_headlines() -> List[str]:
    """Mock headlines fallback."""
    return [
        "NVDA beats earnings expectations, raises guidance",
        "Apple faces supply chain concerns in Asia",
        "Meta's AI investments showing early promise",
        "Microsoft reports strong cloud growth",
        "Amazon expands warehouse automation",
        "Tesla faces EV competition headwinds",
        "Alphabet reports record ad revenue",
        "Berkshire maintains defensive stance",
        "Tech sector leads market rally",
        "Positive sentiment on AI momentum"
    ]


def get_historical_spy_data(ticker: str = "SPY") -> Tuple[List[float], List[float], List[float]]:
    """
    Get historical price and volume data using yfinance.
    Returns (prices, volumes, timestamps) for the last 50 periods.
    Falls back to mock data if yfinance unavailable.
    
    Args:
        ticker: Stock ticker to fetch data for (default: SPY)
    """
    if not YFINANCE_AVAILABLE:
        logger.warning(f"Using mock historical data - install yfinance: pip install yfinance")
        return _get_mock_historical_spy_data()
    
    try:
        stock = yf.Ticker(ticker)
        # Fetch last 3 months of daily data
        hist = stock.history(period="3mo")
        
        if hist.empty:
            logger.warning(f"No {ticker} historical data returned from yfinance")
            return _get_mock_historical_spy_data()
        
        # Get last 50 bars
        prices = hist["Close"].tolist()[-50:]
        volumes = hist["Volume"].tolist()[-50:]
        
        if len(prices) < 15:
            logger.warning(f"Insufficient data: got {len(prices)} periods, need at least 15")
            return _get_mock_historical_spy_data()
        
        return prices, volumes, list(range(len(prices)))
    
    except Exception as e:
        logger.error(f"Error fetching historical SPY data: {e}")
        return _get_mock_historical_spy_data()


def _get_mock_historical_spy_data() -> Tuple[List[float], List[float], List[float]]:
    """Mock historical data fallback."""
    prices = [
        680.5, 680.2, 680.8, 680.5, 681.2, 681.0, 681.8, 681.5, 682.2, 682.0,
        682.8, 682.5, 683.2, 683.0, 683.8, 683.5, 684.2, 684.0, 684.8, 684.5,
        685.2, 685.0, 685.8, 685.5, 686.2, 686.0, 686.8, 686.5, 687.2, 687.0,
        687.8, 687.5, 688.2, 688.0, 688.8, 688.5, 689.2, 689.0, 689.8, 689.5,
        690.2, 690.0, 690.8, 690.5, 691.2, 691.0, 691.8, 691.5, 692.2, 692.0
    ]
    volumes = [
        2500000, 2550000, 2600000, 2650000, 2700000, 2750000, 2800000, 2850000, 2900000, 2950000,
        3000000, 3050000, 3100000, 3150000, 3200000, 3250000, 3300000, 3350000, 3400000, 3450000,
        3500000, 3550000, 3600000, 3650000, 3700000, 3750000, 3800000, 3850000, 3900000, 3950000,
        4000000, 4050000, 4100000, 4150000, 4200000, 4250000, 4300000, 4350000, 4400000, 4450000,
        4500000, 4550000, 4600000, 4650000, 4700000, 4750000, 4800000, 4850000, 4900000, 4950000
    ]
    return prices, volumes, list(range(len(prices)))


def get_vix() -> float:
    """Get VIX value from yfinance. Returns mock data if unavailable."""
    if not YFINANCE_AVAILABLE:
        return 16.8  # Mock fallback
    
    try:
        vix = yf.Ticker("^VIX")
        data = vix.history(period="1d")
        if not data.empty:
            return float(data["Close"].iloc[-1])
    except Exception as e:
        logger.warning(f"Error fetching VIX: {e}")
    
    return 16.8  # Mock fallback


def get_spy_iv_percentile() -> float:
    """
    Get SPY implied volatility percentile.
    
    Note: yfinance doesn't directly provide historical IV percentile.
    This would require options chain analysis or external data source.
    For now, using mock data. To improve:
    - Fetch SPY option chain and calculate IV from bid/ask spreads
    - Store historical IV data to calculate percentile
    """
    if not YFINANCE_AVAILABLE:
        return 42.0  # Mock fallback
    
    try:
        # Alternative approach: estimate IV percentile from options spreads
        spy = yf.Ticker("SPY")
        # Get nearest expiry with options
        expirations = spy.options
        if expirations:
            opts = spy.option_chain(expirations[0])
            calls = opts.calls
            
            if not calls.empty:
                # Use bid-ask spread as proxy for IV (larger spread = higher IV)
                calls["spread"] = calls["ask"] - calls["bid"]
                avg_spread = calls["spread"].mean()
                # Simple heuristic: higher spread = higher IV
                iv_percentile = min(100, (avg_spread * 10))  # Scale to 0-100
                return round(iv_percentile, 1)
    except Exception as e:
        logger.warning(f"Error calculating IV percentile: {e}")
    
    return 42.0  # Mock fallback


def get_option_chain_data(strike: int, expiry: str, ticker: str = "SPY") -> Dict:
    """
    Get option chain data for a specific strike and expiry using yfinance.
    Returns option pricing data for calls and puts.
    Falls back to mock data if unavailable.
    
    Args:
        strike: Strike price (e.g., 688)
        expiry: Expiration date (e.g., "2026-01-09")
        ticker: Stock ticker for options (default: SPY)
    """
    if not YFINANCE_AVAILABLE:
        return _get_mock_option_chain_data(strike, expiry)
    
    try:
        stock = yf.Ticker(ticker)
        
        # Check if expiry exists
        if expiry not in stock.options:
            logger.warning(f"Expiry {expiry} not available for {ticker}. Using nearest expiry.")
            if stock.options:
                expiry = stock.options[0]  # Use nearest available
            else:
                return _get_mock_option_chain_data(strike, expiry)
        
        # Get option chain for expiry
        opts = stock.option_chain(expiry)
        calls = opts.calls
        puts = opts.puts
        
        # Find closest strike
        closest_call = calls.iloc[(calls["strike"] - strike).abs().argsort()[:1]]
        closest_put = puts.iloc[(puts["strike"] - strike).abs().argsort()[:1]]
        
        if closest_call.empty or closest_put.empty:
            return _get_mock_option_chain_data(strike, expiry)
        
        call_row = closest_call.iloc[0]
        put_row = closest_put.iloc[0]
        
        data = {
            "strike": int(call_row["strike"]),
            "expiry": expiry,
            "call": {
                "bid": round(float(call_row["bid"]), 2) if call_row["bid"] > 0 else 0,
                "ask": round(float(call_row["ask"]), 2) if call_row["ask"] > 0 else 0,
                "last_price": round(float(call_row["lastPrice"]), 2) if call_row["lastPrice"] > 0 else (float(call_row["bid"]) + float(call_row["ask"])) / 2,
                "volume": int(call_row["volume"]) if call_row["volume"] > 0 else 0,
                "open_interest": int(call_row["openInterest"]) if call_row["openInterest"] > 0 else 0,
            },
            "put": {
                "bid": round(float(put_row["bid"]), 2) if put_row["bid"] > 0 else 0,
                "ask": round(float(put_row["ask"]), 2) if put_row["ask"] > 0 else 0,
                "last_price": round(float(put_row["lastPrice"]), 2) if put_row["lastPrice"] > 0 else (float(put_row["bid"]) + float(put_row["ask"])) / 2,
                "volume": int(put_row["volume"]) if put_row["volume"] > 0 else 0,
                "open_interest": int(put_row["openInterest"]) if put_row["openInterest"] > 0 else 0,
            }
        }
        
        return data
    
    except Exception as e:
        logger.warning(f"Error fetching option chain: {e}")
        return _get_mock_option_chain_data(strike, expiry)


def _get_mock_option_chain_data(strike: int, expiry: str) -> Dict:
    """Mock option chain data fallback."""
    return {
        "strike": strike,
        "expiry": expiry,
        "call": {
            "bid": 15.2,
            "ask": 15.8,
            "last_price": 15.5,
            "volume": 12500,
            "open_interest": 85000,
        },
        "put": {
            "bid": 8.3,
            "ask": 8.9,
            "last_price": 8.6,
            "volume": 8500,
            "open_interest": 125000,
        }
    }
