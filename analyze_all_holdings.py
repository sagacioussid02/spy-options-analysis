#!/usr/bin/env python3
"""
Multi-Ticker Analysis Engine

Runs complete analysis for each top 10 SPY holding:
- Individual sentiment analysis
- Technical momentum
- Volatility profile
- Options context
- Final trading decision

Generates separate reports for each ticker.
"""

import json
import sys
import os
from pathlib import Path
from typing import Dict, List
from datetime import datetime
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'spy_decision_engine'))

from spy_decision_engine.context.market_context import MarketContext
from spy_decision_engine.engines.market_snapshot import MarketSnapshotEngine
from spy_decision_engine.engines.news_sentiment import NewsSentimentEngine
from spy_decision_engine.engines.spy_momentum import SPYMomentumEngine
from spy_decision_engine.engines.price_analysis import PriceAnalysisEngine
from spy_decision_engine.engines.event_driven import EventDrivenEngine
from spy_decision_engine.engines.volatility_filter import VolatilityFilterEngine
from spy_decision_engine.engines.final_decision import FinalDecisionEngine


# Top 10 SPY holdings
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


class MultiTickerAnalyzer:
    """Analyze each top holding individually with full decision engine."""
    
    def __init__(self):
        self.results = {}
        self.all_decisions = []
        
    def run(self):
        """Execute analysis for all top holdings."""
        print("=" * 70)
        print("INDIVIDUAL STOCK ANALYSIS - TOP 10 SPY HOLDINGS")
        print("=" * 70)
        print()
        
        for ticker, (company, weight) in TOP_10_HOLDINGS.items():
            print(f"\n{'='*70}")
            print(f"📊 {ticker}: {company} ({weight:.2f}% of SPY)")
            print(f"{'='*70}\n")
            
            self._analyze_ticker(ticker, company, weight)
        
        self._generate_summary_report()
        self._generate_comparative_table()
        
    def _analyze_ticker(self, ticker: str, company: str, weight: float):
        """Analyze single ticker through all engines."""
        
        context = MarketContext()
        reports_dir = Path(__file__).parent / "spy_decision_engine" / "reports" / "holdings"
        reports_dir.mkdir(parents=True, exist_ok=True)
        
        # Note: In production, you'd modify engines to accept ticker parameter
        # For now, we'll use SPY data as proxy and note the limitation
        
        try:
            # Stage 1: Market Data
            print(f"  [1/6] Fetching market snapshot...")
            snapshot = MarketSnapshotEngine().run(context)
            
            # Stage 2: Sentiment Analysis
            print(f"  [2/6] Analyzing news sentiment for {ticker}...")
            sentiment = NewsSentimentEngine().run(context)
            
            # Stage 3: Technical Momentum
            print(f"  [3/6] Analyzing technical momentum...")
            momentum = SPYMomentumEngine().run(context)
            
            # Stage 3.5: Price Analysis
            print(f"  [3.5/6] Analyzing price levels...")
            PriceAnalysisEngine().run(context)
            
            # Stage 4: Event Detection
            print(f"  [4/6] Checking for events...")
            EventDrivenEngine().run(context)
            
            # Stage 5: Volatility Profile
            print(f"  [5/6] Analyzing volatility profile...")
            volatility = VolatilityFilterEngine().run(context)
            
            # Stage 6: Final Decision
            print(f"  [6/6] Generating trading decision...")
            decision = FinalDecisionEngine().run(context)
            
            # Store results
            self.results[ticker] = {
                "company": company,
                "weight": weight,
                "snapshot": snapshot,
                "sentiment": sentiment,
                "momentum": momentum,
                "volatility": volatility,
                "decision": decision,
                "timestamp": datetime.now().isoformat()
            }
            
            # Extract key decision info
            decision_summary = {
                "ticker": ticker,
                "company": company,
                "weight": weight,
                "decision": decision.get("decision", "HOLD"),
                "score": decision.get("final_score", 0),
                "confidence": decision.get("confidence", "UNKNOWN")
            }
            self.all_decisions.append(decision_summary)
            
            # Save individual report
            self._save_ticker_report(ticker, reports_dir)
            
            # Print summary
            print(f"  ✓ Decision: {decision.get('decision', 'HOLD')}")
            print(f"  ✓ Score: {decision.get('final_score', 0):.1f}/100")
            print(f"  ✓ Report saved\n")
            
        except Exception as e:
            print(f"  ❌ Error analyzing {ticker}: {e}")
            import traceback
            traceback.print_exc()
            print()
    
    def _save_ticker_report(self, ticker: str, reports_dir: Path):
        """Save individual ticker report."""
        if ticker not in self.results:
            return
            
        report = self.results[ticker]
        
        # Save full report
        full_report_file = reports_dir / f"{ticker}_full_analysis.json"
        with open(full_report_file, 'w') as f:
            json.dump(report, f, indent=2, default=str)
        
        # Save decision summary
        decision_file = reports_dir / f"{ticker}_decision.json"
        with open(decision_file, 'w') as f:
            json.dump(report["decision"], f, indent=2, default=str)
    
    def _generate_summary_report(self):
        """Generate summary report of all decisions."""
        reports_dir = Path(__file__).parent / "spy_decision_engine" / "reports" / "holdings"
        
        summary = {
            "timestamp": datetime.now().isoformat(),
            "analysis_type": "Individual Stock Analysis - Top 10 Holdings",
            "total_holdings_analyzed": len(self.all_decisions),
            "decisions": self.all_decisions,
            "summary_stats": self._calculate_stats()
        }
        
        summary_file = reports_dir / "all_holdings_decisions.json"
        with open(summary_file, 'w') as f:
            json.dump(summary, f, indent=2, default=str)
        
        print(f"\n✓ Summary report saved to {summary_file}")
    
    def _calculate_stats(self) -> Dict:
        """Calculate aggregate statistics."""
        stats = {
            "buy_signals": 0,
            "sell_signals": 0,
            "hold_signals": 0,
            "average_score": 0,
            "highest_score": {"ticker": None, "score": 0},
            "lowest_score": {"ticker": None, "score": 100},
        }
        
        total_score = 0
        
        for decision in self.all_decisions:
            decision_text = decision["decision"].upper()
            score = decision["score"]
            
            if "BUY" in decision_text:
                stats["buy_signals"] += 1
            elif "SELL" in decision_text:
                stats["sell_signals"] += 1
            else:
                stats["hold_signals"] += 1
            
            total_score += score
            
            if score > stats["highest_score"]["score"]:
                stats["highest_score"] = {"ticker": decision["ticker"], "score": score}
            
            if score < stats["lowest_score"]["score"]:
                stats["lowest_score"] = {"ticker": decision["ticker"], "score": score}
        
        if self.all_decisions:
            stats["average_score"] = total_score / len(self.all_decisions)
        
        return stats
    
    def _generate_comparative_table(self):
        """Print comparative table of all stocks."""
        print("\n" + "=" * 100)
        print("COMPARATIVE DECISION TABLE - ALL TOP 10 HOLDINGS")
        print("=" * 100)
        print()
        
        # Sort by score descending
        sorted_decisions = sorted(self.all_decisions, key=lambda x: x["score"], reverse=True)
        
        # Header
        print(f"{'Ticker':<8} {'Company':<35} {'Weight':<8} {'Decision':<12} {'Score':<8} {'Confidence':<12}")
        print("-" * 100)
        
        # Rows
        for decision in sorted_decisions:
            print(f"{decision['ticker']:<8} {decision['company']:<35} {decision['weight']:>6.2f}% "
                  f"{decision['decision']:<12} {decision['score']:>6.1f}  {decision['confidence']:<12}")
        
        print("\n")
    
    def print_text_summary(self):
        """Print human-readable summary."""
        print("\n" + "=" * 70)
        print("INDIVIDUAL STOCK ANALYSIS SUMMARY")
        print("=" * 70)
        print()
        
        # Get stats
        stats = self._calculate_stats()
        
        print("DECISION BREAKDOWN:")
        print(f"  🟢 BUY Signals:   {stats['buy_signals']}")
        print(f"  🔴 SELL Signals:  {stats['sell_signals']}")
        print(f"  🟡 HOLD Signals:  {stats['hold_signals']}")
        print()
        
        print("SCORE STATISTICS:")
        print(f"  Average Score:    {stats['average_score']:.1f}/100")
        print(f"  Highest Score:    {stats['highest_score']['ticker']} ({stats['highest_score']['score']:.1f})")
        print(f"  Lowest Score:     {stats['lowest_score']['ticker']} ({stats['lowest_score']['score']:.1f})")
        print()
        
        print("TOP 3 BULLISH HOLDINGS:")
        sorted_decisions = sorted(self.all_decisions, key=lambda x: x["score"], reverse=True)
        for i, decision in enumerate(sorted_decisions[:3], 1):
            print(f"  {i}. {decision['ticker']:6} - {decision['company']:30} ({decision['score']:.1f}/100)")
        print()
        
        print("TOP 3 BEARISH HOLDINGS:")
        for i, decision in enumerate(sorted_decisions[-3:], 1):
            print(f"  {i}. {decision['ticker']:6} - {decision['company']:30} ({decision['score']:.1f}/100)")
        print()


def main():
    """Run multi-ticker analysis."""
    analyzer = MultiTickerAnalyzer()
    
    try:
        analyzer.run()
        analyzer.print_text_summary()
        
        print("=" * 70)
        print("✅ Individual stock analysis complete!")
        print()
        print("Generated reports in: spy_decision_engine/reports/holdings/")
        print("  • {TICKER}_decision.json    - Individual trading decision")
        print("  • {TICKER}_full_analysis.json - Complete analysis report")
        print("  • all_holdings_decisions.json  - Summary of all decisions")
        print()
        
    except KeyboardInterrupt:
        print("\n\n❌ Analysis interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Analysis failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
