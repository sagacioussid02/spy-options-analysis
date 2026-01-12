#!/usr/bin/env python3
"""
SPY Analysis with Holdings Breakdown

Runs both SPY aggregate analysis AND holdings-weighted analysis
to provide comprehensive trading signals.

Usage:
    python main_with_holdings.py [--spy-only] [--holdings-only]
"""

import sys
import os
import argparse
from pathlib import Path

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'spy_decision_engine'))

from spy_decision_engine.context.market_context import MarketContext
from spy_decision_engine.engines.market_snapshot import MarketSnapshotEngine
from spy_decision_engine.engines.news_sentiment import NewsSentimentEngine
from spy_decision_engine.engines.event_driven import EventDrivenEngine
from spy_decision_engine.engines.spy_momentum import SPYMomentumEngine
from spy_decision_engine.engines.price_analysis import PriceAnalysisEngine
from spy_decision_engine.engines.volatility_filter import VolatilityFilterEngine
from spy_decision_engine.engines.options_whatif import OptionsWhatIfEngine
from spy_decision_engine.engines.final_decision import FinalDecisionEngine
from spy_decision_engine.engines.holdings_analysis import HoldingsAnalysisEngine
from spy_decision_engine.database import DecisionDatabase
from spy_decision_engine.utils.dashboard_updater import DashboardUpdater


def run_spy_analysis(context, db):
    """Run standard SPY analysis."""
    print("=" * 70)
    print("SPY AGGREGATE ANALYSIS")
    print("=" * 70)
    print()
    
    # Stage 1: Always run these engines
    print("📊 Stage 1: Market Analysis")
    print("-" * 70)
    
    MarketSnapshotEngine().run(context)
    print()
    
    NewsSentimentEngine().run(context)
    print()
    
    SPYMomentumEngine().run(context)
    print()
    
    # Stage 1.6: Event-Driven Analysis
    print("📊 Stage 1.6: Event-Driven Analysis")
    print("-" * 70)
    
    EventDrivenEngine().run(context)
    print()
    
    # Stage 1.5: Price Analysis
    print("📊 Stage 1.5: Price Analysis")
    print("-" * 70)
    
    PriceAnalysisEngine().run(context)
    print()
    
    # Stage 2: Check critical gate
    print("📊 Stage 2: Momentum Gate Check")
    print("-" * 70)
    
    if not context.spy_momentum.get("trade_allowed", False):
        print("❌ MOMENTUM CONDITIONS FAILED - NO TRADE")
        print()
        print(f"Trend: {context.spy_momentum.get('trend', 'N/A')}")
        print(f"RSI: {context.spy_momentum.get('rsi', 'N/A')}")
        print(f"EMA Cross: {context.spy_momentum.get('ema_cross', False)}")
        print(f"Above VWAP: {context.spy_momentum.get('above_vwap', False)}")
        
        decision = FinalDecisionEngine().make_no_trade_decision(context)
        return decision
    
    print("✅ MOMENTUM CONDITIONS MET - Proceeding to Stage 2")
    print()
    
    # Stage 3: Options Analysis
    print("📊 Stage 3: Options Analysis")
    print("-" * 70)
    
    VolatilityFilterEngine().run(context)
    print()
    
    OptionsWhatIfEngine().run(context)
    print()
    
    # Stage 4: Final Decision
    print("📊 Stage 4: Final Decision")
    print("-" * 70)
    
    final_decision = FinalDecisionEngine().run(context)
    
    return final_decision


def run_holdings_analysis(context):
    """Run holdings-weighted analysis."""
    print()
    print("=" * 70)
    print("HOLDINGS COMPOSITION ANALYSIS")
    print("=" * 70)
    print()
    
    holdings_engine = HoldingsAnalysisEngine()
    holdings_results = holdings_engine.run(context)
    
    return holdings_results


def print_comparative_summary(spy_decision, holdings_results):
    """Print summary comparing SPY analysis to holdings analysis."""
    print()
    print("=" * 70)
    print("COMPARATIVE ANALYSIS SUMMARY")
    print("=" * 70)
    print()
    
    print("SPY AGGREGATE ANALYSIS:")
    print(f"  Decision: {spy_decision.get('decision', 'UNKNOWN')}")
    print(f"  Score: {spy_decision.get('final_score', 0)}/100")
    print(f"  Confidence: {spy_decision.get('confidence', 'UNKNOWN')}")
    print()
    
    print("HOLDINGS BREAKDOWN (Top 10):")
    print("  Weighted Average Score: Calculated above")
    print("  Key Holdings:")
    
    sorted_holdings = sorted(
        holdings_results.items(),
        key=lambda x: x[1]['weight'],
        reverse=True
    )
    
    for ticker, data in sorted_holdings[:5]:
        print(f"    • {ticker}: {data['weight']:.2f}% - {data['trend']}")
    
    print()
    print("💡 INTERPRETATION:")
    print("  If SPY and holdings scores diverge significantly, it suggests:")
    print("    - Market sentiment may be misleading")
    print("    - Check if specific sectors are pulling SPY")
    print("    - Consider hedging against individual stock movements")
    print()


def main():
    """Execute SPY analysis with optional holdings breakdown."""
    parser = argparse.ArgumentParser(description="SPY analysis with holdings breakdown")
    parser.add_argument("--spy-only", action="store_true", help="Run only SPY analysis")
    parser.add_argument("--holdings-only", action="store_true", help="Run only holdings analysis")
    args = parser.parse_args()
    
    # Initialize database and context
    db = DecisionDatabase()
    context = MarketContext()
    
    spy_decision = None
    holdings_results = None
    
    try:
        if not args.holdings_only:
            spy_decision = run_spy_analysis(context, db)
        
        if not args.spy_only:
            holdings_results = run_holdings_analysis(context)
        
        # Print comparative summary if running both
        if spy_decision and holdings_results:
            print_comparative_summary(spy_decision, holdings_results)
        
        # Update dashboard
        print("\n🎨 Updating dashboard...")
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
