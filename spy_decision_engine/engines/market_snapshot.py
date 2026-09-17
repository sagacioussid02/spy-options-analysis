"""
Market Snapshot Engine

Pulls last 10-15 min intraday data and tracks top SPY contributors.
Outputs market alignment score.
"""
import json
import os
from typing import Dict

from context.market_context import MarketContext
from utils.data_fetcher import get_market_data
from utils.indicators import calculate_alignment_score
import config


class MarketSnapshotEngine:
    """Analyzes current market snapshot for top SPY contributor stocks."""
    
    def run(self, context: MarketContext) -> None:
        """
        Execute market snapshot analysis.
        
        Args:
            context: Shared market context to write results to
        """
        # Alignment (how many top-index contributors are green) is an INDEX
        # concept — get_market_data() always fetches the SPY-basket
        # regardless of ticker, so for a single non-index stock this would
        # silently score against the wrong basket. Skip it and stay neutral.
        if context.ticker not in config.INDEX_TICKERS:
            output = {
                "timestamp": "",
                "stocks": {},
                "green_count": 0,
                "red_count": 0,
                "alignment_score": 0.5,
                "skipped": f"{context.ticker} is not an index ticker — "
                           f"alignment only applies to {sorted(config.INDEX_TICKERS)}",
            }
            context.market_snapshot = output
            self._write_report(output)
            print(f"  (skipped: alignment is index-only, {context.ticker} is not an index)")
            return

        # Fetch market data
        market_data = get_market_data()
        
        # Extract stock changes
        stock_changes = {
            ticker: data["change_pct"]
            for ticker, data in market_data["stocks"].items()
        }
        
        # Count green/red stocks
        green_count = sum(1 for change in stock_changes.values() if change > 0)
        red_count = len(stock_changes) - green_count
        
        # Calculate alignment score
        alignment_score = calculate_alignment_score(stock_changes)
        
        # Build output
        output = {
            "timestamp": market_data["timestamp"],
            "stocks": market_data["stocks"],
            "green_count": green_count,
            "red_count": red_count,
            "alignment_score": round(alignment_score, 2),
        }
        
        # Write to context
        context.market_snapshot = output
        
        # Write to JSON file
        self._write_report(output)
    
    def _write_report(self, output: Dict) -> None:
        """Write snapshot report to JSON file."""
        report_path = os.path.join(config.REPORTS_DIR, "snapshot.json")
        with open(report_path, "w") as f:
            json.dump(output, f, indent=2)
        print(f"✓ Market Snapshot report written to {report_path}")
