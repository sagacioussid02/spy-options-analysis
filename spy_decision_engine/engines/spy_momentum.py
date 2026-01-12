"""
Momentum Engine

Determines momentum and trend analysis based on technical indicators:
- 9 EMA vs 21 EMA
- RSI(14)
- VWAP

Works for any ticker (SPY or individual stocks).
"""
import json
import os
from typing import Dict

from context.market_context import MarketContext
from utils.data_fetcher import get_historical_spy_data
from utils.indicators import calculate_ema, calculate_rsi, calculate_vwap
import config


class SPYMomentumEngine:
    """Analyzes momentum and determines if trading is allowed."""
    
    def run(self, context: MarketContext) -> None:
        """
        Execute momentum analysis.
        
        Args:
            context: Shared market context to write results to
        """
        # Fetch historical data for the ticker
        prices, volumes, _ = get_historical_spy_data(ticker=context.ticker)
        
        # Calculate technical indicators
        ema_9 = calculate_ema(prices, config.EMA_9_PERIOD)
        ema_21 = calculate_ema(prices, config.EMA_21_PERIOD)
        rsi = calculate_rsi(prices, config.RSI_PERIOD)
        vwap = calculate_vwap(prices, volumes)
        
        current_price = prices[-1]
        current_ema_9 = ema_9[-1] if ema_9 else current_price
        current_ema_21 = ema_21[-1] if ema_21 else current_price
        
        # Check bullish conditions
        ema_cross = current_ema_9 > current_ema_21
        above_vwap = current_price > vwap
        rsi_bullish = config.RSI_BULLISH_MIN <= rsi <= config.RSI_BULLISH_MAX
        
        # Determine if trade is allowed
        trade_allowed = ema_cross and above_vwap and rsi_bullish
        
        # Calculate momentum score (0-1)
        score = 0.0
        if ema_cross:
            score += 0.35
        if above_vwap:
            score += 0.35
        if rsi_bullish:
            score += 0.30
        
        # Determine trend
        trend = "BULLISH" if trade_allowed else "BEARISH"
        
        # Build output
        output = {
            "trend": trend,
            "ema_cross": ema_cross,
            "rsi": round(rsi, 1),
            "above_vwap": above_vwap,
            "score": round(score, 2),
            "trade_allowed": trade_allowed,
            "indicators": {
                "ema_9": round(current_ema_9, 2),
                "ema_21": round(current_ema_21, 2),
                "vwap": round(vwap, 2),
                "current_price": round(current_price, 2),
            }
        }
        
        # Write to context
        context.spy_momentum = output
        
        # Write to JSON file
        self._write_report(output)
    
    def _write_report(self, output: Dict) -> None:
        """Write momentum report to JSON file."""
        report_path = os.path.join(config.REPORTS_DIR, "momentum.json")
        with open(report_path, "w") as f:
            json.dump(output, f, indent=2)
        print(f"✓ SPY Momentum report written to {report_path}")
