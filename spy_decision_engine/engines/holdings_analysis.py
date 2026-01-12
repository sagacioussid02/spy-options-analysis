#!/usr/bin/env python3
"""
SPY Holdings-Weighted Analysis Engine

Analyzes top 10 SPY holdings individually and combines results
weighted by their SPY allocation percentage.

This provides a more granular view of what's driving SPY decisions.
"""

import json
import sys
import os
from pathlib import Path
from typing import Dict, List, Tuple
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Top 10 SPY holdings with their percentages
TOP_10_HOLDINGS = {
    "NVDA": ("NVIDIA Corporation", 7.73),
    "AAPL": ("Apple Inc.", 6.86),
    "MSFT": ("Microsoft Corporation", 6.13),
    "AMZN": ("Amazon.com, Inc.", 3.83),
    "GOOGL": ("Alphabet Inc.", 3.11),
    "AVGO": ("Broadcom Inc.", 2.79),
    "GOOG": ("Alphabet Inc.", 2.49),
    "META": ("Meta Platforms, Inc.", 2.45),
    "TSLA": ("Tesla, Inc.", 2.16),
    "BRK-B": ("Berkshire Hathaway Inc.", 1.57),
}

# Total weight of top 10
TOTAL_WEIGHT = sum(pct for _, pct in TOP_10_HOLDINGS.values())


class HoldingsAnalysisEngine:
    """Analyze SPY by breaking down its top holdings."""
    
    def __init__(self):
        self.results = {}
        self.weighted_scores = {
            "momentum": 0,
            "sentiment": 0,
            "volatility": 0,
            "alignment": 0,
        }
        
    def run(self, context):
        """Execute holdings analysis."""
        print("📊 HOLDINGS-WEIGHTED ANALYSIS")
        print("=" * 70)
        print(f"Analyzing top 10 holdings (Total weight: {TOTAL_WEIGHT:.1f}%)")
        print()
        
        self._analyze_holdings(context)
        self._calculate_weighted_scores(context)
        self._save_report()
        
        return self.results
    
    def _analyze_holdings(self, context):
        """Analyze each holding individually."""
        print(f"{'Ticker':<10} {'Company':<25} {'Weight':<8} {'Score':<8} {'Trend':<10}")
        print("-" * 70)
        
        for ticker, (company, weight) in TOP_10_HOLDINGS.items():
            # Placeholder: In production, you'd fetch real data for each ticker
            # For now, use SPY data as proxy (same market conditions affect all)
            
            score = self._calculate_holding_score(ticker, context)
            trend = self._determine_trend(ticker, context)
            
            self.results[ticker] = {
                "company": company,
                "weight": weight,
                "score": score,
                "trend": trend,
                "timestamp": datetime.now().isoformat()
            }
            
            print(f"{ticker:<10} {company:<25} {weight:>6.2f}% {score:>6.1f}  {trend:<10}")
        
        print()
    
    def _calculate_holding_score(self, ticker: str, context) -> float:
        """Calculate individual holding score based on market context."""
        # Use SPY context as proxy for now
        # In production: Fetch ticker-specific sentiment, momentum, options data
        
        market_data = context.market_snapshot or {}
        sentiment_data = context.news_sentiment or {}
        momentum_data = context.spy_momentum or {}
        
        base_score = (market_data.get("current_price", 380) or 380) % 100
        sentiment_boost = (sentiment_data.get("sentiment_score", 0.5) or 0.5) * 20
        momentum_boost = (momentum_data.get("rsi", 50) or 50) / 100 * 20
        
        score = base_score + sentiment_boost + momentum_boost
        return min(100, max(0, score))
    
    def _determine_trend(self, ticker: str, context) -> str:
        """Determine trend direction for holding."""
        momentum_data = context.spy_momentum or {}
        
        if momentum_data.get("ema_cross"):
            return "🔼 UP"
        elif momentum_data.get("trend") == "bearish":
            return "🔽 DOWN"
        else:
            return "➡️ NEUTRAL"
    
    def _calculate_weighted_scores(self, context):
        """Calculate weighted average scores across all holdings."""
        print("📈 WEIGHTED SCORE CALCULATION")
        print("-" * 70)
        
        total_weighted_score = 0
        
        for ticker, data in self.results.items():
            weight_fraction = data["weight"] / TOTAL_WEIGHT
            weighted = data["score"] * weight_fraction
            total_weighted_score += weighted
            
            print(f"{ticker}: {data['score']:5.1f} × {data['weight']:5.2f}% ÷ {TOTAL_WEIGHT:.1f}% = {weighted:5.1f}")
        
        print("-" * 70)
        print(f"{'TOTAL WEIGHTED SCORE':<40} {total_weighted_score:>6.1f}/100")
        print()
        
        # Store weighted result in context
        context.holdings_weighted = {
            "weighted_score": total_weighted_score,
            "holdings_analysis": self.results,
            "analysis_method": "top-10-weighted",
            "recommendation": self._get_recommendation(total_weighted_score)
        }
    
    def _get_recommendation(self, score: float) -> str:
        """Convert weighted score to recommendation."""
        if score >= 75:
            return "🟢 STRONG BUY"
        elif score >= 60:
            return "🟢 BUY"
        elif score >= 50:
            return "🟡 HOLD"
        elif score >= 35:
            return "🔴 SELL"
        else:
            return "🔴 STRONG SELL"
    
    def _save_report(self):
        """Save holdings analysis report."""
        reports_dir = Path(__file__).parent.parent / "reports"
        output_file = reports_dir / "holdings_analysis.json"
        
        report = {
            "timestamp": datetime.now().isoformat(),
            "method": "Top-10 Holdings Weighted Analysis",
            "holdings": self.results,
            "weighted_scores": self.weighted_scores,
            "total_weight": TOTAL_WEIGHT,
            "top_10_composition": {
                ticker: {
                    "company": company,
                    "percentage": weight
                }
                for ticker, (company, weight) in TOP_10_HOLDINGS.items()
            }
        }
        
        with open(output_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        print(f"✓ Holdings analysis report written to {output_file}")


if __name__ == "__main__":
    from context.market_context import MarketContext
    
    context = MarketContext()
    engine = HoldingsAnalysisEngine()
    engine.run(context)
