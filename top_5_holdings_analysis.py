#!/usr/bin/env python3
"""
Top 5 Holdings Individual Analysis Pipeline

Creates separate analysis reports for each of the top 5 SPY holdings:
1. NVDA (7.73%)
2. AAPL (6.86%)
3. MSFT (6.13%)
4. AMZN (3.83%)
5. GOOGL (3.11%)

Generates the same reports as SPY analysis:
- snapshot.json
- sentiment.json
- momentum.json
- final_decision.json
- final_decision_summary.txt
"""

import json
import sys
import os
from pathlib import Path
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'spy_decision_engine'))

from spy_decision_engine.context.market_context import MarketContext
from spy_decision_engine.engines.market_snapshot import MarketSnapshotEngine
from spy_decision_engine.engines.news_sentiment import NewsSentimentEngine
from spy_decision_engine.engines.spy_momentum import SPYMomentumEngine
from spy_decision_engine.engines.price_analysis import PriceAnalysisEngine
from spy_decision_engine.engines.event_driven import EventDrivenEngine
from spy_decision_engine.engines.volatility_filter import VolatilityFilterEngine
from spy_decision_engine.engines.options_whatif import OptionsWhatIfEngine
from spy_decision_engine.engines.final_decision import FinalDecisionEngine
from spy_decision_engine.utils.dashboard_updater import DashboardUpdater


TOP_5_HOLDINGS = {
    "NVDA": ("NVIDIA Corporation", 7.73),
    "AAPL": ("Apple Inc.", 6.86),
    "MSFT": ("Microsoft Corporation", 6.13),
    "AMZN": ("Amazon.com, Inc.", 3.83),
    "GOOGL": ("Alphabet Inc.", 3.11),
}


class Top5HoldingsAnalyzer:
    """Analyze top 5 holdings with same pipeline as SPY."""
    
    def __init__(self):
        self.base_reports_dir = Path(__file__).parent / "spy_decision_engine" / "reports" / "top_5_holdings"
        self.base_reports_dir.mkdir(parents=True, exist_ok=True)
        self.results = {}
    
    def run(self):
        """Execute analysis for all top 5 holdings."""
        print("=" * 70)
        print("TOP 5 SPY HOLDINGS - INDIVIDUAL ANALYSIS")
        print("=" * 70)
        print()
        
        for ticker, (company, weight) in TOP_5_HOLDINGS.items():
            self._analyze_holding(ticker, company, weight)
        
        self._print_summary()
    
    def _analyze_holding(self, ticker: str, company: str, weight: float):
        """Analyze single holding through complete pipeline."""
        
        # Create individual folder for this holding
        holding_dir = self.base_reports_dir / ticker
        holding_dir.mkdir(parents=True, exist_ok=True)
        
        print(f"{'='*70}")
        print(f"📊 {ticker}: {company} ({weight:.2f}% of SPY)")
        print(f"{'='*70}\n")
        
        try:
            context = MarketContext(ticker=ticker)
            
            # Run all analysis engines (same as SPY pipeline)
            print(f"  Stage 1: Market Analysis")
            print(f"  {'─'*50}")
            
            MarketSnapshotEngine().run(context)
            print(f"    ✓ Market snapshot")
            
            NewsSentimentEngine().run(context)
            print(f"    ✓ News sentiment")
            
            SPYMomentumEngine().run(context)
            print(f"    ✓ Momentum analysis")
            print()
            
            print(f"  Stage 2: Technical Analysis")
            print(f"  {'─'*50}")
            
            EventDrivenEngine().run(context)
            print(f"    ✓ Event detection")
            
            PriceAnalysisEngine().run(context)
            print(f"    ✓ Price analysis")
            print()
            
            print(f"  Stage 3: Options Analysis")
            print(f"  {'─'*50}")
            
            VolatilityFilterEngine().run(context)
            print(f"    ✓ Volatility analysis")
            
            OptionsWhatIfEngine().run(context)
            print(f"    ✓ Options what-if")
            print()
            
            print(f"  Stage 4: Final Decision")
            print(f"  {'─'*50}")
            
            final_decision = FinalDecisionEngine().run(context)
            
            # Fallback if decision is None
            if final_decision is None:
                final_decision = {
                    "decision": "HOLD",
                    "final_score": 50.0,
                    "confidence": "LOW",
                    "reasoning": "Analysis complete but decision engine returned None",
                    "momentum_score": 0,
                    "sentiment_score": 0,
                    "alignment_score": 0,
                    "event_score": 0
                }
            
            print(f"    ✓ Trading decision")
            print()
            
            # Save reports to individual holding folder
            self._save_reports(ticker, holding_dir, context, final_decision)
            
            # Store results
            self.results[ticker] = {
                "company": company,
                "weight": weight,
                "decision": final_decision.get("decision", "HOLD"),
                "score": final_decision.get("final_score", 0),
                "confidence": final_decision.get("confidence", "UNKNOWN"),
                "reports_location": str(holding_dir)
            }
            
            # Print summary
            print(f"  DECISION: {final_decision.get('decision', 'HOLD')}")
            print(f"  SCORE: {final_decision.get('final_score', 0):.1f}/100")
            print(f"  CONFIDENCE: {final_decision.get('confidence', 'UNKNOWN')}")
            print(f"  📁 Reports saved to: {holding_dir.name}/")
            print()
            
        except Exception as e:
            print(f"  ❌ Error analyzing {ticker}: {e}")
            import traceback
            traceback.print_exc()
            print()
    
    def _save_reports(self, ticker: str, holding_dir: Path, context, final_decision):
        """Save all reports for individual holding."""
        
        # Save market snapshot
        if context.market_snapshot:
            with open(holding_dir / "snapshot.json", 'w') as f:
                json.dump(context.market_snapshot, f, indent=2, default=str)
        
        # Save sentiment - filter to only include data for this specific ticker
        if context.news_sentiment:
            filtered_sentiment = self._filter_sentiment_by_ticker(ticker, context.news_sentiment)
            with open(holding_dir / "sentiment.json", 'w') as f:
                json.dump(filtered_sentiment, f, indent=2, default=str)
        
        # Save momentum
        if context.spy_momentum:
            with open(holding_dir / "momentum.json", 'w') as f:
                json.dump(context.spy_momentum, f, indent=2, default=str)
        
        # Save price analysis
        if hasattr(context, 'price_analysis') and context.price_analysis:
            with open(holding_dir / "price_analysis.json", 'w') as f:
                json.dump(context.price_analysis, f, indent=2, default=str)
        
        # Save event analysis
        if hasattr(context, 'event_analysis') and context.event_analysis:
            with open(holding_dir / "event_driven.json", 'w') as f:
                json.dump(context.event_analysis, f, indent=2, default=str)
        
        # Save volatility
        if hasattr(context, 'volatility_analysis') and context.volatility_analysis:
            with open(holding_dir / "volatility.json", 'w') as f:
                json.dump(context.volatility_analysis, f, indent=2, default=str)
        
        # Save options analysis
        if hasattr(context, 'options_analysis') and context.options_analysis:
            with open(holding_dir / "options.json", 'w') as f:
                json.dump(context.options_analysis, f, indent=2, default=str)
        
        # Save final decision
        if final_decision:
            with open(holding_dir / "final_decision.json", 'w') as f:
                json.dump(final_decision, f, indent=2, default=str)
        
        # Save human-readable summary
        self._save_text_summary(ticker, holding_dir, final_decision)
    
    def _filter_sentiment_by_ticker(self, ticker: str, sentiment_data: dict) -> dict:
        """Filter sentiment data to only include the specific ticker."""
        filtered = {
            "overall": sentiment_data.get("overall", {}),
            "by_stock": {},
            "top_headlines": []
        }
        
        # Map ticker to company name used in sentiment data
        ticker_to_company = {
            "NVDA": "NVIDIA",
            "AAPL": "Apple",
            "MSFT": "Microsoft",
            "AMZN": "Amazon",
            "GOOGL": "Google"
        }
        
        company_name = ticker_to_company.get(ticker, ticker)
        
        # Include only the headlines and stock data for this ticker
        by_stock = sentiment_data.get("by_stock", {})
        if company_name in by_stock:
            filtered["by_stock"][company_name] = by_stock[company_name]
        
        # Filter headlines to only include those mentioning this ticker
        all_headlines = sentiment_data.get("top_headlines", [])
        for headline in all_headlines:
            if any(keyword.lower() in headline.lower() for keyword in [ticker, company_name]):
                filtered["top_headlines"].append(headline)
        
        # Keep at least a few headlines even if they don't directly mention this ticker
        if not filtered["top_headlines"] and all_headlines:
            filtered["top_headlines"] = all_headlines[:3]
        
        return filtered
    
    def _save_text_summary(self, ticker: str, holding_dir: Path, final_decision):
        """Save human-readable summary."""
        
        summary = f"""================================================================================
{ticker} - TRADING DECISION SUMMARY
================================================================================

Decision:    {final_decision.get('decision', 'UNKNOWN')}
Score:       {final_decision.get('final_score', 0):.1f}/100
Confidence:  {final_decision.get('confidence', 'UNKNOWN')}

Generated:   {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

================================================================================
REASONING
================================================================================

{final_decision.get('reasoning', 'N/A')}

================================================================================
COMPONENT SCORES
================================================================================

Momentum:    {final_decision.get('momentum_score', 0):.2f}
Sentiment:   {final_decision.get('sentiment_score', 0):.2f}
Alignment:   {final_decision.get('alignment_score', 0):.2f}
Event-Driven: {final_decision.get('event_score', 0):.2f}

================================================================================
"""
        
        with open(holding_dir / "final_decision_summary.txt", 'w') as f:
            f.write(summary)
    
    def _print_summary(self):
        """Print summary of all holdings analysis."""
        print("\n" + "=" * 70)
        print("TOP 5 HOLDINGS ANALYSIS SUMMARY")
        print("=" * 70)
        print()
        
        print(f"{'Ticker':<8} {'Company':<30} {'Weight':<10} {'Decision':<12} {'Score':<10}")
        print("-" * 70)
        
        for ticker, (company, weight) in TOP_5_HOLDINGS.items():
            if ticker in self.results:
                result = self.results[ticker]
                print(f"{ticker:<8} {company:<30} {weight:>8.2f}%  {result['decision']:<12} {result['score']:>8.1f}")
        
        print()
        print("📁 Reports Location:")
        print(f"   {self.base_reports_dir}/")
        print()
        print("Folder Structure:")
        for ticker in TOP_5_HOLDINGS.keys():
            print(f"   {ticker}/")
            print(f"      ├── snapshot.json")
            print(f"      ├── sentiment.json")
            print(f"      ├── momentum.json")
            print(f"      ├── price_analysis.json")
            print(f"      ├── event_driven.json")
            print(f"      ├── volatility.json")
            print(f"      ├── options.json")
            print(f"      ├── final_decision.json")
            print(f"      └── final_decision_summary.txt")
        print()
        
        # Save comparison report
        self._save_comparison_report()
    
    def _save_comparison_report(self):
        """Save comparison report of all top 5."""
        comparison = {
            "timestamp": datetime.now().isoformat(),
            "analysis_type": "Top 5 Holdings Individual Analysis",
            "holdings_analyzed": len(self.results),
            "results": self.results,
            "statistics": self._calculate_stats()
        }
        
        comparison_file = self.base_reports_dir / "top_5_comparison.json"
        with open(comparison_file, 'w') as f:
            json.dump(comparison, f, indent=2, default=str)
        
        print(f"✓ Comparison report: {comparison_file}")


    def _calculate_stats(self):
        """Calculate statistics."""
        buy_count = sum(1 for r in self.results.values() if "BUY" in r["decision"].upper())
        sell_count = sum(1 for r in self.results.values() if "SELL" in r["decision"].upper())
        hold_count = len(self.results) - buy_count - sell_count
        avg_score = sum(r["score"] for r in self.results.values()) / len(self.results) if self.results else 0
        
        return {
            "total_analyzed": len(self.results),
            "buy_signals": buy_count,
            "sell_signals": sell_count,
            "hold_signals": hold_count,
            "average_score": avg_score
        }


def main():
    """Run top 5 holdings analysis."""
    try:
        analyzer = Top5HoldingsAnalyzer()
        analyzer.run()
        
        print("\n" + "=" * 70)
        print("✅ TOP 5 HOLDINGS ANALYSIS COMPLETE")
        print("=" * 70)
        print()
        
        # Update dashboard
        print("🎨 Updating dashboard...")
        dashboard = DashboardUpdater()
        if dashboard.update():
            print(f"✓ Dashboard ready at: {dashboard.dashboard_path}")
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
