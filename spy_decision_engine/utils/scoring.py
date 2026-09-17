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
    holdings_score: float = 0.5,
    is_index_ticker: bool = True
) -> float:
    """
    Calculate final decision score using weighted formula.

    Index formula (is_index_ticker=True — alignment/event_driven/holdings
    are all derived from index composition, e.g. SPY's top holdings):
    final_score = 0.28 * momentum + 0.18 * alignment + 0.18 * event_driven +
                  0.14 * sentiment + 0.14 * (1 - volatility_penalty) + 0.08 * holdings

    Single-stock formula (is_index_ticker=False — alignment/event_driven/
    holdings don't apply to an individual stock, so they're dropped and the
    remaining three weights (momentum:sentiment:volatility = 2:1:1) are
    renormalized to sum to 1):
    final_score = 0.5 * momentum + 0.25 * sentiment + 0.25 * (1 - volatility_penalty)

    Args:
        momentum_score: Momentum score (0-1)
        alignment_score: Market alignment score (0-1) — index-only
        sentiment_score: News sentiment score (0-1)
        volatility_penalty: Volatility penalty (0-1, subtracted from score)
        event_driven_score: Event-driven bias score (0-1) — index-only
        holdings_score: Top holdings aggregate score (0-1) — index-only
        is_index_ticker: Whether the analyzed ticker is an index (e.g. SPY)

    Returns:
        Final score (0-100 scale)
    """
    if is_index_ticker:
        weighted_score = (
            0.28 * momentum_score +
            0.18 * alignment_score +
            0.18 * event_driven_score +
            0.14 * sentiment_score +
            0.14 * (1 - volatility_penalty) +
            0.08 * holdings_score
        )
    else:
        weighted_score = (
            0.5 * momentum_score +
            0.25 * sentiment_score +
            0.25 * (1 - volatility_penalty)
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
