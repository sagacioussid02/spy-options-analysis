"""
Trade Analyzer Module

Learns from historical trades to improve future recommendations.
Calculates win rates by entry price, DTE, confidence, sentiment, etc.
"""
import json
import os
from typing import Dict, List, Tuple
from collections import defaultdict
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TradeAnalyzer:
    """Analyzes historical trades to identify winning patterns."""
    
    def __init__(self, trades_file: str = "spy_decision_engine/data/trades.json"):
        """
        Initialize analyzer.
        
        Args:
            trades_file: Path to trades history JSON file
        """
        self.trades_file = trades_file
        self.trades = self._load_trades()
        self.closed_trades = [t for t in self.trades.get("trades", []) if t.get("exit")]
    
    def _load_trades(self) -> Dict:
        """Load trades from file."""
        if os.path.exists(self.trades_file):
            with open(self.trades_file, 'r') as f:
                return json.load(f)
        return {"trades": []}
    
    def analyze_win_rate_by_entry_price(self) -> Dict[str, float]:
        """
        Calculate win rate for different entry price ranges.
        
        Returns:
            Dict of price ranges to win rates
        """
        price_buckets = defaultdict(lambda: {"wins": 0, "total": 0})
        
        for trade in self.closed_trades:
            entry_price = trade["entry"]["price"]
            is_winning = trade["exit"]["profit"] > 0
            
            # Bucket by $1 ranges
            bucket_key = f"${int(entry_price)}-{int(entry_price)+1}"
            price_buckets[bucket_key]["total"] += 1
            if is_winning:
                price_buckets[bucket_key]["wins"] += 1
        
        return {
            bucket: (bucket_data["wins"] / bucket_data["total"] * 100)
            if bucket_data["total"] > 0 else 0
            for bucket, bucket_data in price_buckets.items()
        }
    
    def analyze_win_rate_by_dte(self) -> Dict[int, float]:
        """
        Calculate win rate for each DTE (1, 2, 3, 4).
        
        Returns:
            Dict of DTE to win rate percentage
        """
        dte_buckets = defaultdict(lambda: {"wins": 0, "total": 0})
        
        for trade in self.closed_trades:
            dte = trade["expiry_dte"]
            is_winning = trade["exit"]["profit"] > 0
            
            dte_buckets[dte]["total"] += 1
            if is_winning:
                dte_buckets[dte]["wins"] += 1
        
        return {
            dte: (dte_data["wins"] / dte_data["total"] * 100)
            if dte_data["total"] > 0 else 0
            for dte, dte_data in sorted(dte_buckets.items())
        }
    
    def analyze_win_rate_by_confidence(self) -> Dict[str, Tuple[float, int]]:
        """
        Calculate win rate for different confidence score ranges.
        
        Returns:
            Dict of confidence ranges to (win_rate%, sample_size)
        """
        confidence_buckets = defaultdict(lambda: {"wins": 0, "total": 0})
        
        for trade in self.closed_trades:
            confidence = trade["entry"]["engine_confidence"]
            is_winning = trade["exit"]["profit"] > 0
            
            # Bucket: 60-70, 70-80, 80-90, 90+
            if confidence < 70:
                bucket = "Low (< 70%)"
            elif confidence < 80:
                bucket = "Medium (70-80%)"
            elif confidence < 90:
                bucket = "High (80-90%)"
            else:
                bucket = "Very High (90%+)"
            
            confidence_buckets[bucket]["total"] += 1
            if is_winning:
                confidence_buckets[bucket]["wins"] += 1
        
        return {
            bucket: (
                (confidence_data["wins"] / confidence_data["total"] * 100),
                confidence_data["total"]
            )
            for bucket, confidence_data in confidence_buckets.items()
        }
    
    def analyze_win_rate_by_instrument(self) -> Dict[str, float]:
        """
        Calculate win rate for calls vs puts.
        
        Returns:
            Dict of instrument type to win rate
        """
        instrument_buckets = defaultdict(lambda: {"wins": 0, "total": 0})
        
        for trade in self.closed_trades:
            instrument = trade["instrument"]  # "SPY Call" or "SPY Put"
            is_winning = trade["exit"]["profit"] > 0
            
            instrument_buckets[instrument]["total"] += 1
            if is_winning:
                instrument_buckets[instrument]["wins"] += 1
        
        return {
            instrument: (data["wins"] / data["total"] * 100)
            if data["total"] > 0 else 0
            for instrument, data in instrument_buckets.items()
        }
    
    def analyze_prediction_accuracy(self) -> Dict[str, float]:
        """
        Calculate how often engine's direction prediction was correct.
        
        Returns:
            Dict of accuracy metrics
        """
        if not self.closed_trades:
            return {"prediction_accuracy": 0, "sample_size": 0}
        
        correct_predictions = sum(
            1 for trade in self.closed_trades
            if trade.get("analysis", {}).get("prediction_correct")
        )
        
        return {
            "prediction_accuracy_pct": (correct_predictions / len(self.closed_trades) * 100),
            "correct_predictions": correct_predictions,
            "sample_size": len(self.closed_trades)
        }
    
    def find_best_entry_price(self) -> Dict:
        """
        Identify which price ranges have highest win rates.
        
        Returns:
            Dict with best entry price ranges and their stats
        """
        win_rates = self.analyze_win_rate_by_entry_price()
        
        if not win_rates:
            return {"recommendation": "No trades yet", "sample_size": 0}
        
        sorted_prices = sorted(win_rates.items(), key=lambda x: x[1], reverse=True)
        
        best_price_range = sorted_prices[0] if sorted_prices else None
        
        return {
            "best_entry_price": best_price_range[0] if best_price_range else "N/A",
            "win_rate_at_best": round(best_price_range[1], 1) if best_price_range else 0,
            "all_price_ranges": {k: round(v, 1) for k, v in sorted_prices},
            "recommendation": f"Enter at support ({best_price_range[0]}) - {best_price_range[1]:.0f}% win rate"
            if best_price_range else "Need more data"
        }
    
    def find_best_dte(self) -> Dict:
        """
        Identify which DTE has highest win rate.
        
        Returns:
            Dict with best DTE and stats
        """
        win_rates = self.analyze_win_rate_by_dte()
        
        if not win_rates:
            return {"recommendation": "No trades yet"}
        
        best_dte = max(win_rates.items(), key=lambda x: x[1])
        
        return {
            "best_dte": best_dte[0],
            "win_rate_at_best_dte": round(best_dte[1], 1),
            "all_dte_win_rates": {k: round(v, 1) for k, v in win_rates.items()},
            "recommendation": f"Use {best_dte[0]} DTE - {best_dte[1]:.0f}% win rate"
        }
    
    def find_best_confidence_threshold(self) -> Dict:
        """
        Identify minimum confidence needed for profitable trading.
        
        Returns:
            Dict with recommended confidence threshold
        """
        confidence_stats = self.analyze_win_rate_by_confidence()
        
        if not confidence_stats:
            return {"recommendation": "No trades yet", "recommended_threshold": 75}
        
        # Find threshold where win rate exceeds 60%
        for bucket in ["Very High (90%+)", "High (80-90%)", "Medium (70-80%)", "Low (< 70%)"]:
            if bucket in confidence_stats:
                win_rate, count = confidence_stats[bucket]
                if win_rate > 60:
                    # Extract the lower bound of the range
                    if "Very High" in bucket:
                        threshold = 90
                    elif "High" in bucket:
                        threshold = 80
                    elif "Medium" in bucket:
                        threshold = 70
                    else:
                        threshold = 60
                    
                    return {
                        "recommended_threshold": threshold,
                        "expected_win_rate": round(win_rate, 1),
                        "sample_size": count,
                        "recommendation": f"Only trade when confidence > {threshold}% ({win_rate:.0f}% win rate)"
                    }
        
        return {
            "recommended_threshold": 75,
            "recommendation": "Build more trade history to determine optimal threshold"
        }
    
    def generate_report(self) -> Dict:
        """
        Generate comprehensive analysis report.
        
        Returns:
            Dict with all analysis results
        """
        return {
            "total_trades": len(self.closed_trades),
            "win_rate_summary": self.analyze_win_rate_by_confidence(),
            "by_dte": self.analyze_win_rate_by_dte(),
            "by_instrument": self.analyze_win_rate_by_instrument(),
            "prediction_accuracy": self.analyze_prediction_accuracy(),
            "best_entry_price": self.find_best_entry_price(),
            "best_dte": self.find_best_dte(),
            "confidence_threshold": self.find_best_confidence_threshold(),
            "summary": {
                "total_profit": self.trades.get("summary", {}).get("net_profit", 0),
                "win_rate": self.trades.get("summary", {}).get("win_rate", 0),
                "profit_factor": self.trades.get("summary", {}).get("profit_factor", 0),
            }
        }
    
    def print_report(self) -> None:
        """Print comprehensive analysis report."""
        report = self.generate_report()
        
        print("\n" + "=" * 70)
        print("TRADE ANALYSIS REPORT - WHAT WORKS FOR YOU")
        print("=" * 70)
        
        print(f"\n📊 OVERVIEW")
        print(f"  Total Closed Trades: {report['total_trades']}")
        print(f"  Overall Win Rate: {report['summary']['win_rate']}%")
        print(f"  Total Profit: ${report['summary']['total_profit']:.2f}")
        print(f"  Profit Factor: {report['summary']['profit_factor']}")
        
        print(f"\n🎯 BEST ENTRY PRICE")
        entry = report['best_entry_price']
        print(f"  Recommendation: {entry.get('recommendation', 'N/A')}")
        print(f"  All ranges: {entry.get('all_price_ranges', {})}")
        
        print(f"\n📅 BEST DTE (Days to Expiry)")
        dte = report['best_dte']
        print(f"  Recommendation: {dte.get('recommendation', 'N/A')}")
        print(f"  All DTEs: {dte.get('all_dte_win_rates', {})}")
        
        print(f"\n💪 CONFIDENCE THRESHOLD")
        conf = report['confidence_threshold']
        print(f"  Recommendation: {conf.get('recommendation', 'N/A')}")
        
        print(f"\n🔮 PREDICTION ACCURACY")
        pred = report['prediction_accuracy']
        print(f"  Overall Accuracy: {pred.get('prediction_accuracy_pct', 0):.1f}%")
        print(f"  Correct Predictions: {pred.get('correct_predictions', 0)}/{pred.get('sample_size', 0)}")
        
        print(f"\n📈 BY INSTRUMENT")
        for instrument, win_rate in report['by_instrument'].items():
            print(f"  {instrument}: {win_rate:.1f}% win rate")
        
        print("\n" + "=" * 70)
    
    def get_recommendations(self) -> Dict[str, any]:
        """
        Get actionable trading recommendations based on historical analysis.
        
        Returns:
            Dict with recommendations for next trade
        """
        entry_analysis = self.find_best_entry_price()
        dte_analysis = self.find_best_dte()
        confidence_analysis = self.find_best_confidence_threshold()
        accuracy = self.analyze_prediction_accuracy()
        
        return {
            "next_trade_recommendations": {
                "entry_price": entry_analysis.get("recommendation"),
                "expiry_dte": dte_analysis.get("recommendation"),
                "confidence_threshold": confidence_analysis.get("recommendation"),
            },
            "trading_rules": [
                f"Only trade when engine confidence > {confidence_analysis.get('recommended_threshold', 75)}%",
                f"Prefer entry at support (${entry_analysis.get('best_entry_price', 'N/A')})",
                f"Use {dte_analysis.get('best_dte', 2)} DTE for best results",
                f"Direction accuracy is {accuracy.get('prediction_accuracy_pct', 0):.0f}% - track this",
            ],
            "current_stats": {
                "trades_analyzed": len(self.closed_trades),
                "overall_win_rate": self.trades.get("summary", {}).get("win_rate", 0),
                "need_more_trades": len(self.closed_trades) < 20,
            }
        }


if __name__ == "__main__":
    analyzer = TradeAnalyzer()
    analyzer.print_report()
    
    recommendations = analyzer.get_recommendations()
    print("\n\n📝 NEXT TRADE RECOMMENDATIONS")
    for rule in recommendations['trading_rules']:
        print(f"  • {rule}")
