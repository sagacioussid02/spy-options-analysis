#!/usr/bin/env python3
"""
Enhanced Trade Analysis with Volume/Liquidity Integration
Analyzes if trades with good liquidity perform better
"""

import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from spy_decision_engine.experimental.volume_liquidity_tracker import VolumeLiquidityTracker


class EnhancedBehavioralAnalysis:
    """Combines behavioral analytics with volume/liquidity data."""
    
    def __init__(self, trades_file: str = None, data_dir: str = None):
        """Initialize enhanced analysis."""
        if trades_file is None:
            trades_file = str(Path(__file__).parent.parent / "data" / "trades.json")
        if data_dir is None:
            data_dir = str(Path(__file__).parent.parent / "data")
        
        self.trades_file = Path(trades_file)
        self.data_dir = Path(data_dir)
        self.tracker = VolumeLiquidityTracker(data_dir=str(self.data_dir))
    
    def analyze_trades_by_liquidity(self) -> dict:
        """Analyze if high-liquidity trades perform better."""
        with open(self.trades_file) as f:
            trades_data = json.load(f)
        
        high_liquidity_trades = []
        low_liquidity_trades = []
        unknown_liquidity_trades = []
        
        for trade in trades_data.get("trades", []):
            # Only analyze closed trades
            if not trade.get("exit"):
                continue
            
            ticker = trade.get("instrument", "SPY").split()[0]  # Extract ticker from "SPY Call"
            strike = trade.get("strike", 0)
            trade_type = "CALL" if "Call" in trade.get("instrument", "") else "PUT"
            
            # Get liquidity analysis
            liquidity_analysis = self.tracker.analyze_volume_for_trade(ticker, strike, trade_type)
            
            trade_record = {
                "trade_id": trade.get("trade_id"),
                "strike": strike,
                "profit": trade.get("exit", {}).get("profit", 0),
                "profit_pct": trade.get("exit", {}).get("profit_pct", 0),
                "liquidity_score": liquidity_analysis.get("liquidity_score", 0),
                "volume_trend": liquidity_analysis.get("volume_trend", "UNKNOWN"),
                "oi_trend": liquidity_analysis.get("oi_trend", "UNKNOWN"),
            }
            
            if liquidity_analysis.get("analysis") == "FAVORABLE":
                high_liquidity_trades.append(trade_record)
            elif liquidity_analysis.get("analysis") == "UNFAVORABLE":
                low_liquidity_trades.append(trade_record)
            else:
                unknown_liquidity_trades.append(trade_record)
        
        # Calculate statistics
        stats = {
            "high_liquidity": self._calculate_stats(high_liquidity_trades),
            "low_liquidity": self._calculate_stats(low_liquidity_trades),
            "unknown_liquidity": self._calculate_stats(unknown_liquidity_trades),
            "trades": {
                "high_liquidity": high_liquidity_trades,
                "low_liquidity": low_liquidity_trades,
                "unknown_liquidity": unknown_liquidity_trades,
            }
        }
        
        return stats
    
    def _calculate_stats(self, trades: list) -> dict:
        """Calculate statistics for a group of trades."""
        if not trades:
            return {
                "count": 0,
                "wins": 0,
                "losses": 0,
                "win_rate": 0,
                "avg_profit": 0,
                "total_pnl": 0
            }
        
        wins = len([t for t in trades if t["profit"] > 0])
        total_pnl = sum([t["profit"] for t in trades])
        avg_profit = total_pnl / len(trades) if trades else 0
        
        return {
            "count": len(trades),
            "wins": wins,
            "losses": len(trades) - wins,
            "win_rate": wins / len(trades) if trades else 0,
            "avg_profit": avg_profit,
            "total_pnl": total_pnl,
        }
    
    def generate_liquidity_performance_report(self) -> str:
        """Generate report showing liquidity impact on performance."""
        stats = self.analyze_trades_by_liquidity()
        
        high_stats = stats["high_liquidity"]
        low_stats = stats["low_liquidity"]
        
        report = f"""
╔═══════════════════════════════════════════════════════════════════╗
║       LIQUIDITY IMPACT ON TRADE PERFORMANCE ANALYSIS              ║
╚═══════════════════════════════════════════════════════════════════╝

📊 TRADES WITH HIGH LIQUIDITY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Total: {high_stats['count']}
  Wins: {high_stats['wins']}
  Losses: {high_stats['losses']}
  Win Rate: {high_stats['win_rate']:.1%}
  Avg Profit: ${high_stats['avg_profit']:.2f}
  Total P&L: ${high_stats['total_pnl']:+.2f}
  Status: {'✅ FAVORABLE' if high_stats['win_rate'] > 0.5 else '⚠️ MARGINAL'}

📊 TRADES WITH LOW LIQUIDITY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Total: {low_stats['count']}
  Wins: {low_stats['wins']}
  Losses: {low_stats['losses']}
  Win Rate: {low_stats['win_rate']:.1%}
  Avg Profit: ${low_stats['avg_profit']:.2f}
  Total P&L: ${low_stats['total_pnl']:+.2f}
  Status: {'❌ AVOID' if low_stats['win_rate'] < 0.3 else '⚠️ RISKY'}

📈 KEY INSIGHTS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
        
        if high_stats['count'] > 0 and low_stats['count'] > 0:
            win_rate_diff = high_stats['win_rate'] - low_stats['win_rate']
            profit_diff = high_stats['avg_profit'] - low_stats['avg_profit']
            
            report += f"""
  Win Rate Difference: {win_rate_diff:+.1%} (high vs low liquidity)
  Profit Difference: ${profit_diff:+.2f} (high vs low liquidity)
"""
            
            if win_rate_diff > 0.1:
                report += f"  → Liquidity HELPS: Trade high-liquidity contracts\n"
            elif win_rate_diff < -0.1:
                report += f"  → Liquidity HURTS: Avoid high-liquidity contracts\n"
            else:
                report += f"  → Liquidity NEUTRAL: Similar performance\n"
        
        if stats["trades"]["high_liquidity"]:
            report += f"""

🟢 HIGH LIQUIDITY TRADES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
            for trade in stats["trades"]["high_liquidity"]:
                status = "✅" if trade["profit"] > 0 else "❌"
                report += f"  {status} {trade['trade_id']}: ${trade['profit']:+.2f} ({trade['profit_pct']:+.1f}%)\n"
        
        if stats["trades"]["low_liquidity"]:
            report += f"""

🔴 LOW LIQUIDITY TRADES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
            for trade in stats["trades"]["low_liquidity"]:
                status = "✅" if trade["profit"] > 0 else "❌"
                report += f"  {status} {trade['trade_id']}: ${trade['profit']:+.2f} ({trade['profit_pct']:+.1f}%)\n"
        
        return report


if __name__ == "__main__":
    analyzer = EnhancedBehavioralAnalysis()
    print(analyzer.generate_liquidity_performance_report())
