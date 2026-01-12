"""
Volatility Filter Engine

Penalizes options buying in high volatility environments.
Uses VIX and implied volatility percentile.
"""
import json
import os
from typing import Dict

from context.market_context import MarketContext
from utils.data_fetcher import get_vix, get_spy_iv_percentile
import config


class VolatilityFilterEngine:
    """Analyzes volatility and applies penalties for options trading."""
    
    def run(self, context: MarketContext) -> None:
        """
        Execute volatility filter analysis.
        
        Args:
            context: Shared market context to write results to
        """
        # Fetch volatility data
        vix = get_vix()
        iv_percentile = get_spy_iv_percentile()
        
        # Calculate penalty
        penalty = 0.0
        options_favorable = True
        
        # VIX penalty
        if vix > config.VIX_HIGH_THRESHOLD:
            penalty += (vix - config.VIX_HIGH_THRESHOLD) * 0.01
            options_favorable = False
        
        # IV percentile penalty
        if iv_percentile > config.IV_PERCENTILE_HIGH_THRESHOLD:
            penalty += 0.15
            options_favorable = False
        
        # Cap penalty at 0.4
        penalty = min(penalty, 0.4)
        
        # Build output
        output = {
            "vix": round(vix, 1),
            "iv_percentile": round(iv_percentile, 1),
            "options_favorable": options_favorable,
            "penalty": round(penalty, 2),
        }
        
        # Write to context
        context.volatility = output
        
        # Write to JSON file
        self._write_report(output)
    
    def _write_report(self, output: Dict) -> None:
        """Write volatility report to JSON file."""
        report_path = os.path.join(config.REPORTS_DIR, "volatility.json")
        with open(report_path, "w") as f:
            json.dump(output, f, indent=2)
        print(f"✓ Volatility Filter report written to {report_path}")
