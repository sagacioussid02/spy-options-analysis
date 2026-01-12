"""
Price Analysis Engine

Fetches pricing data and provides buy/sell price recommendations
based on technical levels, volatility, and options premiums.
"""
import json
import os
from typing import Dict, Tuple

from context.market_context import MarketContext
from utils.data_fetcher import get_historical_spy_data
import config
import yfinance as yf


class PriceAnalysisEngine:
    """Analyzes pricing levels and recommends entry/exit prices."""
    
    def run(self, context: MarketContext) -> None:
        """
        Execute price analysis.
        
        Args:
            context: Shared market context with momentum and sentiment data
        """
        # Get current ticker data
        current_price = context.spy_momentum.get("indicators", {}).get("current_price", 0)
        vwap = context.spy_momentum.get("indicators", {}).get("vwap", 0)
        rsi = context.spy_momentum.get("rsi", 50)
        
        # Get daily data for the ticker
        daily_data = self._get_daily_data(context.ticker)
        
        # Calculate support/resistance levels
        support, resistance = self._calculate_levels(daily_data)
        
        # Get volatility (from data_fetcher or mock)
        try:
            from utils.data_fetcher import get_vix
            volatility = get_vix()
        except:
            volatility = 15
        
        # Get options pricing context (if available)
        option_strike = current_price
        option_premium = 5.5
        bid_ask = {"bid": 5.54, "ask": 5.63}
        theta_risk = "MODERATE"
        
        # Build pricing recommendations
        output = {
            "current_price": round(current_price, 2),
            "daily_data": daily_data,
            "technical_levels": {
                "support": round(support, 2),
                "resistance": round(resistance, 2),
                "vwap": round(vwap, 2),
            },
            "entry_prices": self._calculate_entry_prices(current_price, support, resistance),
            "position_sizing": {
                "volatility": round(volatility, 2),
                "position_size_pct": self._calculate_position_size(volatility),
                "rationale": self._position_sizing_rationale(volatility),
            },
            "options_context": {
                "strike": option_strike,
                "premium": round(option_premium, 2),
                "bid_ask_spread": bid_ask,
                "theta_risk": theta_risk,
            },
            "buy_decision": self._get_buy_decision(
                current_price, support, vwap, rsi, 
                context.spy_momentum.get("trend", "NEUTRAL"), 
                context.news_sentiment.get("score", 0.5)
            ),
        }
        
        # Write to context
        context.price_analysis = output
        
        # Write to JSON file
        self._write_report(output)
    
    def _get_daily_data(self, ticker: str = "SPY") -> Dict:
        """Fetch current daily OHLCV data for the ticker."""
        try:
            stock = yf.Ticker(ticker)
            # Get today's data
            hist = stock.history(period="1d")
            
            if not hist.empty:
                latest = hist.iloc[-1]
                return {
                    "open": round(float(latest["Open"]), 2),
                    "high": round(float(latest["High"]), 2),
                    "low": round(float(latest["Low"]), 2),
                    "close": round(float(latest["Close"]), 2),
                    "volume": int(latest["Volume"]),
                    "day_range": round(float(latest["High"]) - float(latest["Low"]), 2),
                }
        except Exception as e:
            pass
        
        # Return mock if unavailable
        return {
            "open": 689.50,
            "high": 693.20,
            "low": 687.10,
            "close": 691.81,
            "volume": 45_000_000,
            "day_range": 6.10,
        }
    
    def _calculate_levels(self, spy_data: Dict) -> Tuple[float, float]:
        """Calculate support and resistance levels based on daily range."""
        high = spy_data.get("high", 0)
        low = spy_data.get("low", 0)
        close = spy_data.get("close", 0)
        
        # Support: recent low
        support = low
        
        # Resistance: recent high
        resistance = high
        
        return support, resistance
    
    def _calculate_entry_prices(self, current: float, support: float, resistance: float) -> Dict:
        """Suggest optimal entry prices based on technical levels."""
        range_size = resistance - support
        
        # Conservative: near support (20% up from support)
        conservative = support + (range_size * 0.20)
        
        # Aggressive: current price (immediate entry)
        aggressive = current
        
        # Risky: near resistance (80% up from support)
        risky = support + (range_size * 0.80)
        
        return {
            "conservative": round(conservative, 2),
            "at_current": round(aggressive, 2),
            "risky": round(risky, 2),
        }
    
    def _calculate_position_size(self, vix: float) -> str:
        """Determine position size based on VIX (volatility)."""
        if vix < 12:
            return "LARGE (25-30%)"
        elif vix < 15:
            return "MEDIUM-LARGE (20-25%)"
        elif vix < 18:
            return "MEDIUM (15-20%)"
        elif vix < 22:
            return "MEDIUM-SMALL (10-15%)"
        else:
            return "SMALL (5-10%)"
    
    def _position_sizing_rationale(self, vix: float) -> str:
        """Explain position sizing rationale."""
        if vix < 15:
            return "Low volatility - comfortable with larger position"
        elif vix < 20:
            return "Moderate volatility - balanced approach"
        else:
            return "Elevated volatility - reduce position to manage risk"
    
    def _get_buy_decision(self, current: float, support: float, vwap: float, 
                         rsi: float, trend: str, sentiment: float) -> Dict:
        """Generate buy decision based on all factors."""
        reasons = []
        score = 0
        
        # Price relative to support
        if current > vwap:
            reasons.append("Price above VWAP - bullish")
            score += 25
        
        # Trend assessment
        if trend == "BULLISH":
            reasons.append("Trend is bullish")
            score += 25
        
        # RSI assessment
        if 50 <= rsi <= 70:
            reasons.append("RSI in sweet spot (50-70) - not overbought")
            score += 25
        
        # Sentiment
        if sentiment > 0.6:
            reasons.append("Positive news sentiment")
            score += 25
        
        decision = "STRONG BUY" if score >= 90 else "BUY" if score >= 70 else "WAIT"
        
        return {
            "decision": decision,
            "score": score,
            "reasons": reasons,
        }
    
    def _write_report(self, output: Dict) -> None:
        """Write pricing analysis report to JSON file."""
        report_path = os.path.join(config.REPORTS_DIR, "price_analysis.json")
        with open(report_path, "w") as f:
            json.dump(output, f, indent=2)
        print(f"✓ Price Analysis report written to {report_path}")
