"""
Options What-If Engine

Analyzes option premium behavior for a given contract over ±3 days.
"""
import json
import os
from typing import Dict

from context.market_context import MarketContext
from utils.data_fetcher import get_option_chain_data
import config


class OptionsWhatIfEngine:
    """Analyzes option premium scenarios and theta risk."""
    
    def __init__(self, strike: int = None, expiry: str = None, option_type: str = None):
        """
        Initialize with option parameters.
        
        Args:
            strike: Strike price (default from config)
            expiry: Expiration date (default from config)
            option_type: CALL or PUT (default from config)
        """
        self.strike = strike or config.DEFAULT_OPTION_STRIKE
        self.expiry = expiry or config.DEFAULT_OPTION_EXPIRY
        self.option_type = option_type or config.DEFAULT_OPTION_TYPE
    
    def run(self, context: MarketContext) -> None:
        """
        Execute options what-if analysis.
        
        Args:
            context: Shared market context to write results to
        """
        # Fetch option chain data for the ticker
        option_data = get_option_chain_data(self.strike, self.expiry, ticker=context.ticker)
        
        # Get current premium
        if self.option_type == "CALL":
            current_premium = option_data["call"]["last_price"]
        else:
            current_premium = option_data["put"]["last_price"]
        
        # Simulate premium changes over 3 days
        # In real scenario, these would come from historical models
        profit_scenarios = {
            "D-1": round(current_premium + 0.8, 1),   # 1 day gain
            "D-2": round(current_premium + 2.6, 1),   # 2 day gain
            "D-3": round(current_premium + 9.4, 1),   # 3 day gain
        }
        
        # Determine premium trend
        premium_trend = "RISING"
        
        # Assess theta risk
        theta_risk = "MODERATE"
        
        # Build output
        output = {
            "strike": self.strike,
            "expiry": self.expiry,
            "type": self.option_type,
            "current_premium": current_premium,
            "profit_if_bought": profit_scenarios,
            "premium_trend": premium_trend,
            "theta_risk": theta_risk,
            "bid_ask": {
                "bid": option_data[self.option_type.lower()]["bid"],
                "ask": option_data[self.option_type.lower()]["ask"],
            }
        }
        
        # Write to context
        context.options_analysis = output
        
        # Write to JSON file
        self._write_report(output)
    
    def _write_report(self, output: Dict) -> None:
        """Write options analysis report to JSON file."""
        report_path = os.path.join(config.REPORTS_DIR, "options.json")
        with open(report_path, "w") as f:
            json.dump(output, f, indent=2)
        print(f"✓ Options What-If report written to {report_path}")
