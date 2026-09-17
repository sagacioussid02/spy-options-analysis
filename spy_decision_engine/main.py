#!/usr/bin/env python3
"""
SPY Options Decision Engine - Main Orchestrator

Local, modular decision support system for SPY options trading.
Runs all engines in sequence with context-based communication.
"""

import sys
import os

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from context.market_context import MarketContext
from engines.market_snapshot import MarketSnapshotEngine
from engines.news_sentiment import NewsSentimentEngine
from engines.event_driven import EventDrivenEngine
from engines.spy_momentum import SPYMomentumEngine
from engines.price_analysis import PriceAnalysisEngine
from engines.volatility_filter import VolatilityFilterEngine
from engines.options_whatif import OptionsWhatIfEngine
from engines.final_decision import FinalDecisionEngine
from database import DecisionDatabase
from utils.dashboard_updater import DashboardUpdater
import config


def main():
    """Execute the complete decision engine workflow."""
    
    print("=" * 70)
    print("SPY OPTIONS DECISION ENGINE")
    print("Local Analysis | January 6, 2026")
    print("=" * 70)
    print()
    
    # Initialize database
    db = DecisionDatabase()
    
    # Initialize shared context
    context = MarketContext(config.TICKER)
    
    try:
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
            print()
            return
        
        print("✅ MOMENTUM CONDITIONS MET - Proceeding to Stage 2")
        print()
        
        # Stage 3: Continue if momentum is bullish
        print("📊 Stage 3: Options Analysis")
        print("-" * 70)
        
        VolatilityFilterEngine().run(context)
        print()
        
        OptionsWhatIfEngine().run(context)
        print()
        
        # Stage 4: Final decision
        print("📊 Stage 4: Final Decision")
        print("-" * 70)
        
        FinalDecisionEngine().run(context)
        print()
        
        # Display summary
        print("=" * 70)
        print("DECISION SUMMARY")
        print("=" * 70)
        
        final = context.final_decision
        print(f"Final Score: {final['final_score']}/100")
        print(f"Decision: {final['decision']}")
        print(f"Confidence: {final['confidence']}")
        print()
        print("Reasoning:")
        for line in final['recommendation']['explanation']:
            print(f"  • {line}")
        print()
        
        print("All reports saved to /reports directory")
        print()
        
        # Save to database
        db.save_engine_run(context.final_decision)
        print("✓ Decision saved to database")
        print()
        
        # Update dashboard
        print("🎨 Updating dashboard...")
        dashboard = DashboardUpdater()
        if dashboard.update():
            print(f"✓ Dashboard ready at: {dashboard.dashboard_path}")
        print()
        
    except Exception as e:
        print(f"❌ Error during execution: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
