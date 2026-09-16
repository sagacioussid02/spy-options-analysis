#!/usr/bin/env python3
"""
Trade Recommendation Engine
Integrates behavioral analytics with market analysis to recommend trades
"""

import json
from pathlib import Path
from datetime import datetime
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from spy_decision_engine.utils.behavioral_analytics import BehavioralAnalytics


class TradeRecommendationEngine:
    """Recommends whether to take a trade based on your behavior + market data."""
    
    def __init__(self, reports_dir: str = None):
        """Initialize recommendation engine."""
        if reports_dir is None:
            reports_dir = str(Path(__file__).parent.parent / "reports")
        
        self.reports_dir = Path(reports_dir)
        self.analyzer = BehavioralAnalytics()
    
    def load_market_data(self) -> dict:
        """Load current market analysis."""
        data = {}
        
        try:
            with open(self.reports_dir / "final_decision.json") as f:
                data["decision"] = json.load(f)
        except:
            data["decision"] = None
        
        try:
            with open(self.reports_dir / "sentiment.json") as f:
                data["sentiment"] = json.load(f)
        except:
            data["sentiment"] = None
        
        try:
            with open(self.reports_dir / "momentum.json") as f:
                data["momentum"] = json.load(f)
        except:
            data["momentum"] = None
        
        return data
    
    def evaluate_trade_opportunity(self, trade_params: dict) -> dict:
        """Evaluate if a trade opportunity should be taken."""
        
        market_data = self.load_market_data()
        behavioral_prediction = self.analyzer.predict_trade_outcome(trade_params)
        
        # Extract key metrics
        market_sentiment = market_data.get("sentiment", {}).get("overall", {}).get("blended_score", 0.5)
        market_trend = market_data.get("momentum", {}).get("trend", "NEUTRAL")
        market_rsi = market_data.get("momentum", {}).get("rsi", 50)
        market_decision = market_data.get("decision", {}).get("decision", "HOLD")
        market_score = market_data.get("decision", {}).get("final_score", 50)
        
        # Behavioral edge
        behavioral_win_rate = behavioral_prediction.get("historical_win_rate", 0)
        expected_value = behavioral_prediction.get("expected_value", 0)
        confidence = behavioral_prediction.get("confidence", 0)
        
        # Calculate recommendation score
        scores = {
            "market_alignment": self._score_market_alignment(market_decision, trade_params),
            "behavioral_edge": self._score_behavioral_edge(behavioral_win_rate, expected_value),
            "volatility_fitness": self._score_volatility_fitness(market_rsi, trade_params),
            "risk_reward": self._score_risk_reward(trade_params),
        }
        
        overall_score = (
            scores["market_alignment"] * 0.35 +
            scores["behavioral_edge"] * 0.35 +
            scores["volatility_fitness"] * 0.20 +
            scores["risk_reward"] * 0.10
        )
        
        # Generate recommendation
        if overall_score >= 0.70:
            recommendation = "✅ STRONG BUY - High conviction based on market + behavior"
            action = "TAKE_TRADE"
        elif overall_score >= 0.50:
            recommendation = "🟡 CAUTIOUS BUY - Decent opportunity, manage risk"
            action = "TAKE_TRADE_SMALL"
        elif overall_score >= 0.30:
            recommendation = "⚠️  SKIP - Not enough edge to justify"
            action = "SKIP"
        else:
            recommendation = "❌ AVOID - Works against your proven strategies"
            action = "SKIP"
        
        return {
            "recommendation": recommendation,
            "action": action,
            "overall_score": overall_score,
            "component_scores": scores,
            "market_analysis": {
                "sentiment": market_sentiment,
                "trend": market_trend,
                "rsi": market_rsi,
                "decision": market_decision,
                "score": market_score,
            },
            "behavioral_analysis": {
                "historical_win_rate": behavioral_win_rate,
                "expected_value": expected_value,
                "confidence": confidence,
                "strategy": behavioral_prediction.get("strategy", "UNKNOWN"),
            },
            "reasoning": self._generate_reasoning(scores, market_data, trade_params),
        }
    
    def _score_market_alignment(self, market_decision: str, trade_params: dict) -> float:
        """Score how well the trade aligns with current market decision."""
        if market_decision in ["BUY", "BUY_SMALL", "BUY SMALL"]:
            if trade_params.get("predicted_direction", "UP") == "UP":
                return 1.0
            else:
                return 0.3
        elif market_decision in ["SELL", "SELL_COVERED", "SELL PUT"]:
            if trade_params.get("predicted_direction", "UP") == "DOWN":
                return 1.0
            else:
                return 0.2
        else:  # HOLD
            return 0.5
    
    def _score_behavioral_edge(self, win_rate: float, expected_value: float) -> float:
        """Score how strong your behavioral edge is."""
        if win_rate == 0:
            return 0.0  # No historical data
        
        if win_rate >= 0.70 and expected_value > 0:
            return 1.0  # Proven edge
        elif win_rate >= 0.50 and expected_value > 0:
            return 0.7  # Likely edge
        elif win_rate >= 0.40:
            return 0.5  # Marginal edge
        else:
            return 0.1  # Negative edge
    
    def _score_volatility_fitness(self, rsi: float, trade_params: dict) -> float:
        """Score if current volatility is good for this trade type."""
        reason = trade_params.get("reason", "").lower()
        
        # Momentum trades work best when RSI not extreme
        if "momentum" in reason:
            if 40 < rsi < 70:
                return 1.0
            elif 30 < rsi < 80:
                return 0.7
            else:
                return 0.3
        
        # Contrarian trades work best when RSI IS extreme
        if "contrarian" in reason:
            if rsi > 70 or rsi < 30:
                return 1.0
            elif rsi > 65 or rsi < 35:
                return 0.7
            else:
                return 0.3
        
        return 0.6  # Default to moderate
    
    def _score_risk_reward(self, trade_params: dict) -> float:
        """Score the risk/reward of the proposed trade."""
        entry = trade_params.get("entry_premium", 0)
        upside_target = trade_params.get("upside_target", 0)
        stop_loss = trade_params.get("stop_loss", 0)
        
        if entry == 0:
            return 0.5  # Can't evaluate
        
        # If they provided targets, use them
        if upside_target and stop_loss:
            max_profit = upside_target - entry
            max_loss = entry - stop_loss
            
            if max_loss <= 0:
                return 0.2  # Stop loss too tight
            
            ratio = max_profit / max_loss
            
            if ratio >= 3:
                return 1.0
            elif ratio >= 2:
                return 0.8
            elif ratio >= 1:
                return 0.6
            else:
                return 0.3
        
        return 0.5  # No targets provided
    
    def _generate_reasoning(self, scores: dict, market_data: dict, trade_params: dict) -> str:
        """Generate human-readable reasoning for recommendation."""
        reasoning = []
        
        # Market alignment
        if scores["market_alignment"] > 0.8:
            reasoning.append("✓ Aligns well with current market decision")
        elif scores["market_alignment"] < 0.3:
            reasoning.append("✗ Goes against current market signal")
        
        # Behavioral
        if scores["behavioral_edge"] > 0.8:
            reasoning.append("✓ You have proven edge on this strategy type")
        elif scores["behavioral_edge"] == 0:
            reasoning.append("⚠ No historical data - tracking new strategy")
        elif scores["behavioral_edge"] < 0.3:
            reasoning.append("✗ You typically lose on this strategy type")
        
        # Volatility
        if scores["volatility_fitness"] > 0.8:
            reasoning.append("✓ Market volatility is ideal for this trade")
        elif scores["volatility_fitness"] < 0.3:
            reasoning.append("✗ Market volatility not favorable for this trade")
        
        return " | ".join(reasoning)


def main():
    """Example usage of trade recommendation engine."""
    engine = TradeRecommendationEngine()
    
    # Evaluate the contrarian trade you want to make
    evaluation = engine.evaluate_trade_opportunity({
        "reason": "Contrarian play: Bullish sentiment vs bearish technicals",
        "confidence": 67,
        "strike": 700,
        "predicted_direction": "UP",
        "entry_premium": 0.61,
    })
    
    print("\n🎯 TRADE RECOMMENDATION ENGINE")
    print("=" * 70)
    print(f"\nRecommendation: {evaluation['recommendation']}")
    print(f"Overall Score: {evaluation['overall_score']:.1%}")
    
    print(f"\nComponent Scores:")
    for component, score in evaluation['component_scores'].items():
        print(f"  • {component.upper()}: {score:.0%}")
    
    print(f"\nMarket Status:")
    market = evaluation['market_analysis']
    print(f"  • Decision: {market['decision']} (Score: {market['score']:.0f}/100)")
    print(f"  • Trend: {market['trend']} (RSI: {market['rsi']:.1f})")
    print(f"  • Sentiment: {'Bullish' if market['sentiment'] > 0.55 else 'Bearish'}")
    
    print(f"\nYour Behavioral Edge:")
    behavior = evaluation['behavioral_analysis']
    print(f"  • Strategy: {behavior['strategy']}")
    print(f"  • Historical Win Rate: {behavior['historical_win_rate']:.0%}")
    print(f"  • Expected Value: ${behavior['expected_value']:.2f}")
    
    print(f"\nReasoning:")
    print(f"  {evaluation['reasoning']}")


if __name__ == "__main__":
    main()
