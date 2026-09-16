#!/usr/bin/env python3
"""
Behavioral Analytics - Track trading behavior patterns and predict future outcomes
Analyzes your trading decisions to identify which conditions lead to wins
"""

import json
from pathlib import Path
from datetime import datetime
from collections import defaultdict
import statistics


class BehavioralAnalytics:
    """Tracks and analyzes your trading behavior patterns."""
    
    def __init__(self, trades_file: str = None, reports_dir: str = None):
        """Initialize behavioral analytics."""
        if trades_file is None:
            trades_file = str(Path(__file__).parent.parent / "data" / "trades.json")
        if reports_dir is None:
            reports_dir = str(Path(__file__).parent.parent / "reports")
        
        self.trades_file = Path(trades_file)
        self.reports_dir = Path(reports_dir)
        self.behavior_file = self.reports_dir / "behavioral_analysis.json"
    
    def extract_trade_conditions(self, trade: dict, market_data: dict = None) -> dict:
        """Extract the conditions that existed when trade was made."""
        entry = trade.get("entry", {})
        
        # Basic conditions
        conditions = {
            "trade_id": trade.get("trade_id"),
            "date": trade.get("date"),
            "strike": trade.get("strike"),
            "instrument": trade.get("instrument"),
            "contracts": entry.get("contracts", 1),
            "entry_premium": entry.get("premium_paid", 0),
            "reason": entry.get("reason", ""),
            "engine_confidence": entry.get("engine_confidence", 0),
            "predicted_direction": entry.get("predicted_direction", "UNKNOWN"),
        }
        
        # Outcome (if trade is closed)
        exit_data = trade.get("exit")
        if exit_data:
            conditions["exit_premium"] = exit_data.get("premium_sold", 0)
            conditions["profit"] = exit_data.get("profit", 0)
            conditions["profit_pct"] = exit_data.get("profit_pct", 0)
            conditions["win"] = conditions["profit"] > 0
            conditions["days_held"] = self._estimate_days_held(trade.get("date"), 
                                                               exit_data.get("date", trade.get("date")))
        else:
            conditions["exit_premium"] = None
            conditions["profit"] = None
            conditions["profit_pct"] = None
            conditions["win"] = None
            conditions["days_held"] = None
            conditions["status"] = "OPEN"
        
        return conditions
    
    def classify_strategy(self, reason: str, confidence: float) -> str:
        """Classify the trading strategy used."""
        reason_lower = reason.lower()
        
        # Recovery / Mean reversion plays
        if "recovery" in reason_lower or "reversion" in reason_lower or "bounce" in reason_lower:
            return "RECOVERY"
        
        # Contrarian plays
        if "contrarian" in reason_lower or "divergence" in reason_lower:
            return "CONTRARIAN"
        
        # Momentum plays
        if "momentum" in reason_lower or "trend" in reason_lower or "bullish" in reason_lower:
            return "MOMENTUM"
        
        # Sentiment plays
        if "sentiment" in reason_lower or "news" in reason_lower:
            return "SENTIMENT"
        
        # News-based
        if "event" in reason_lower or "earnings" in reason_lower:
            return "EVENT"
        
        return "MIXED"
    
    def analyze_behavior_patterns(self) -> dict:
        """Analyze your trading behavior patterns and success rates."""
        if not self.trades_file.exists():
            return {}
        
        with open(self.trades_file) as f:
            trades_data = json.load(f)
        
        trades = trades_data.get("trades", [])
        
        # Group trades by strategy
        strategies = defaultdict(list)
        all_conditions = []
        
        for trade in trades:
            conditions = self.extract_trade_conditions(trade)
            all_conditions.append(conditions)
            
            # Only analyze closed trades
            if conditions.get("win") is not None:
                strategy = self.classify_strategy(
                    conditions.get("reason", ""),
                    conditions.get("engine_confidence", 0)
                )
                strategies[strategy].append(conditions)
        
        # Calculate statistics by strategy
        stats = {}
        for strategy, conditions_list in strategies.items():
            wins = [c for c in conditions_list if c.get("win")]
            losses = [c for c in conditions_list if not c.get("win")]
            
            win_rate = len(wins) / len(conditions_list) if conditions_list else 0
            avg_profit = statistics.mean([c["profit"] for c in conditions_list]) if conditions_list else 0
            days_held_list = [c.get("days_held", 1) for c in conditions_list if c.get("days_held")]
            avg_days = statistics.mean(days_held_list) if days_held_list else 1
            
            stats[strategy] = {
                "total_trades": len(conditions_list),
                "wins": len(wins),
                "losses": len(losses),
                "win_rate": win_rate,
                "avg_profit": avg_profit,
                "avg_loss": statistics.mean([c["profit"] for c in losses]) if losses else 0,
                "avg_days_held": avg_days,
                "total_pnl": sum([c["profit"] for c in conditions_list]),
                "profit_factor": (
                    sum([c["profit"] for c in wins]) / abs(sum([c["profit"] for c in losses]))
                    if losses and sum([c["profit"] for c in losses]) != 0
                    else float('inf')
                ),
            }
        
        # Overall stats
        closed_trades = [c for c in all_conditions if c.get("win") is not None]
        open_trades = [c for c in all_conditions if c.get("status") == "OPEN"]
        wins = [c for c in closed_trades if c.get("win")]
        
        analysis = {
            "timestamp": datetime.now().isoformat(),
            "total_closed_trades": len(closed_trades),
            "total_open_trades": len(open_trades),
            "total_wins": len(wins),
            "total_losses": len(closed_trades) - len(wins),
            "overall_win_rate": len(wins) / len(closed_trades) if closed_trades else 0,
            "overall_pnl": sum([c["profit"] for c in closed_trades]),
            "avg_profit_per_trade": statistics.mean([c["profit"] for c in closed_trades]) if closed_trades else 0,
            "strategy_breakdown": stats,
            "recent_trades": all_conditions[-10:],  # Last 10 trades
        }
        
        return analysis
    
    def predict_trade_outcome(self, conditions: dict) -> dict:
        """Predict likelihood of success based on your historical behavior."""
        analysis = self.analyze_behavior_patterns()
        
        if not analysis.get("strategy_breakdown"):
            return {"prediction": "INSUFFICIENT_DATA", "confidence": 0}
        
        # Classify the potential trade
        strategy = self.classify_strategy(
            conditions.get("reason", ""),
            conditions.get("confidence", 50)
        )
        
        if strategy not in analysis["strategy_breakdown"]:
            return {
                "prediction": "UNKNOWN_STRATEGY",
                "strategy": strategy,
                "confidence": 0,
                "message": f"No historical data for {strategy} trades"
            }
        
        strategy_stats = analysis["strategy_breakdown"][strategy]
        
        # Prediction logic
        prediction = {
            "strategy": strategy,
            "historical_win_rate": strategy_stats["win_rate"],
            "similar_trades": strategy_stats["total_trades"],
            "avg_profit": strategy_stats["avg_profit"],
            "avg_days_held": strategy_stats["avg_days_held"],
            "expected_value": (
                strategy_stats["win_rate"] * strategy_stats["avg_profit"] +
                (1 - strategy_stats["win_rate"]) * strategy_stats["avg_loss"]
            ),
            "profit_factor": strategy_stats["profit_factor"],
            "confidence": min(strategy_stats["total_trades"] / 5, 1.0),  # More trades = more confidence
        }
        
        # Determine prediction
        if prediction["expected_value"] > 0 and prediction["historical_win_rate"] > 0.5:
            prediction["recommendation"] = "✅ FAVORABLE (based on your history)"
        elif prediction["historical_win_rate"] < 0.3:
            prediction["recommendation"] = "❌ UNFAVORABLE (you lose on these)"
        else:
            prediction["recommendation"] = "⚠️ NEUTRAL (mixed results)"
        
        return prediction
    
    def detect_behavioral_biases(self) -> dict:
        """Detect your behavioral trading biases."""
        analysis = self.analyze_behavior_patterns()
        biases = []
        
        closed_trades = [c for c in analysis.get("recent_trades", []) if c.get("win") is not None]
        if not closed_trades:
            return {"biases": [], "message": "Not enough closed trades to detect biases"}
        
        # Check for loss-aversion (holding winners too long, cutting losses early)
        wins = [c for c in closed_trades if c.get("win")]
        losses = [c for c in closed_trades if not c.get("win")]
        
        if wins and losses:
            avg_win_days = statistics.mean([c.get("days_held", 1) for c in wins])
            avg_loss_days = statistics.mean([c.get("days_held", 1) for c in losses])
            
            if avg_win_days > avg_loss_days * 1.5:
                biases.append({
                    "bias": "LOSS_AVERSION",
                    "description": "You hold winners longer than losers",
                    "impact": "Could lead to overconfidence"
                })
        
        # Check for overconfidence in certain strategies
        strategies = analysis.get("strategy_breakdown", {})
        high_confidence_plays = [
            (s, stats) for s, stats in strategies.items()
            if stats["total_trades"] >= 2 and stats["win_rate"] > 0.7
        ]
        
        if high_confidence_plays:
            biases.append({
                "bias": "HIGH_CONFIDENCE_STRATEGIES",
                "strategies": [s for s, _ in high_confidence_plays],
                "description": "You excel at these specific strategies",
                "impact": "Lean into these for better risk-adjusted returns"
            })
        
        # Check for recency bias
        last_3_trades = closed_trades[-3:]
        if last_3_trades:
            recent_win_rate = len([c for c in last_3_trades if c.get("win")]) / len(last_3_trades)
            overall_win_rate = analysis.get("overall_win_rate", 0)
            
            if recent_win_rate > overall_win_rate + 0.2:
                biases.append({
                    "bias": "RECENCY_BIAS",
                    "description": "Your recent trades are doing better than average",
                    "impact": "Stay disciplined - past performance doesn't guarantee future results"
                })
        
        return {
            "biases": biases,
            "timestamp": datetime.now().isoformat(),
            "trades_analyzed": len(closed_trades)
        }
    
    def _estimate_days_held(self, entry_date: str, exit_date: str) -> int:
        """Estimate days between entry and exit."""
        try:
            entry = datetime.strptime(entry_date, "%Y-%m-%d")
            exit = datetime.strptime(exit_date, "%Y-%m-%d")
            return (exit - entry).days
        except:
            return 1
    
    def generate_report(self) -> str:
        """Generate a readable behavioral analysis report."""
        analysis = self.analyze_behavior_patterns()
        biases = self.detect_behavioral_biases()
        
        report = f"""
╔══════════════════════════════════════════════════════════════╗
║          YOUR TRADING BEHAVIOR ANALYSIS REPORT               ║
║                  {datetime.now().strftime('%Y-%m-%d %H:%M')}                          
╚══════════════════════════════════════════════════════════════╝

📊 OVERALL PERFORMANCE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Total Trades: {analysis.get('total_closed_trades', 0)} closed + {analysis.get('total_open_trades', 0)} open
  Win Rate: {analysis.get('overall_win_rate', 0):.1%}
  Total P&L: ${analysis.get('overall_pnl', 0):,.2f}
  Avg Profit/Trade: ${analysis.get('avg_profit_per_trade', 0):,.2f}

🎯 STRATEGY BREAKDOWN
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
        
        for strategy, stats in analysis.get("strategy_breakdown", {}).items():
            report += f"""
  {strategy}:
    • Trades: {stats['total_trades']} (W:{stats['wins']} L:{stats['losses']})
    • Win Rate: {stats['win_rate']:.1%}
    • Avg Profit: ${stats['avg_profit']:.2f}
    • Profit Factor: {stats['profit_factor']:.2f}x
"""
        
        report += f"""
⚠️  BEHAVIORAL BIASES DETECTED
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
        
        if biases.get("biases"):
            for bias in biases["biases"]:
                report += f"""
  • {bias['bias']}
    {bias.get('description', 'N/A')}
    Impact: {bias.get('impact', 'Unknown')}
"""
        else:
            report += "\n  ✓ No significant biases detected\n"
        
        return report
    
    def save_analysis(self):
        """Save analysis to file."""
        analysis = self.analyze_behavior_patterns()
        with open(self.behavior_file, 'w') as f:
            json.dump(analysis, f, indent=2)
        return str(self.behavior_file)


if __name__ == "__main__":
    analyzer = BehavioralAnalytics()
    
    # Generate and print report
    print(analyzer.generate_report())
    
    # Save analysis
    saved_path = analyzer.save_analysis()
    print(f"\n✓ Analysis saved to: {saved_path}")
    
    # Show prediction for a hypothetical contrarian trade
    test_conditions = {
        "reason": "Contrarian play: Bullish sentiment vs bearish technicals",
        "confidence": 67,
        "strike": 700,
    }
    
    prediction = analyzer.predict_trade_outcome(test_conditions)
    print(f"\n🔮 PREDICTION FOR YOUR CONTRARIAN TRADES:")
    for key, value in prediction.items():
        if isinstance(value, float):
            print(f"  {key}: {value:.2%}" if key in ["historical_win_rate", "confidence"] else f"  {key}: {value:.2f}")
        else:
            print(f"  {key}: {value}")
