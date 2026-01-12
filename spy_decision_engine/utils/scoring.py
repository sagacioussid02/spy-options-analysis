"""
Scoring utilities for final decision aggregation.
"""
from typing import Dict


def calculate_final_score(
    momentum_score: float,
    alignment_score: float,
    sentiment_score: float,
    volatility_penalty: float,
    event_driven_score: float = 0.5,
    holdings_score: float = 0.5
) -> float:
    """
    Calculate final decision score using weighted formula.
    
    Formula:
    final_score = 0.28 * momentum + 0.18 * alignment + 0.18 * event_driven + 
                  0.14 * sentiment + 0.14 * (1 - volatility_penalty) + 0.08 * holdings
    
    Args:
        momentum_score: SPY momentum score (0-1)
        alignment_score: Market alignment score (0-1)
        sentiment_score: News sentiment score (0-1)
        volatility_penalty: Volatility penalty (0-1, subtracted from score)
        event_driven_score: Event-driven bias score (0-1)
        holdings_score: Top 5 holdings aggregate score (0-1)
    
    Returns:
        Final score (0-100 scale)
    """
    weighted_score = (
        0.28 * momentum_score +
        0.18 * alignment_score +
        0.18 * event_driven_score +
        0.14 * sentiment_score +
        0.14 * (1 - volatility_penalty) +
        0.08 * holdings_score
    )
    
    # Convert to 0-100 scale
    return max(0, min(100, weighted_score * 100))


def score_to_decision(score: float) -> tuple:
    """
    Convert numerical score to trading decision and confidence.
    
    Args:
        score: Final numerical score (0-100)
    
    Returns:
        Tuple of (decision: str, confidence: str)
    """
    if score >= 75:
        return "BUY SMALL", "HIGH"
    elif score >= 60:
        return "BUY MICRO", "MEDIUM"
    elif score >= 40:
        return "HOLD / PASS", "MEDIUM"
    elif score >= 25:
        return "AVOID", "MEDIUM"
    else:
        return "DO NOT TRADE", "HIGH"


def calculate_sentiment_score(positive_count: int, negative_count: int) -> float:
    """
    Calculate sentiment score from news sentiment counts.
    
    Args:
        positive_count: Number of positive keywords
        negative_count: Number of negative keywords
    
    Returns:
        Sentiment score (-1.0 to 1.0, normalized to 0-1 range)
    """
    total = positive_count + negative_count
    
    if total == 0:
        return 0.5
    
    raw_sentiment = (positive_count - negative_count) / total
    # Normalize from [-1, 1] to [0, 1]
    normalized = (raw_sentiment + 1) / 2
    return normalized
