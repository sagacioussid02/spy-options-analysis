"""
Technical indicator calculations.
"""
from typing import List, Tuple


def calculate_ema(prices: List[float], period: int) -> List[float]:
    """
    Calculate Exponential Moving Average.
    
    Args:
        prices: List of price values
        period: EMA period (e.g., 9, 21)
    
    Returns:
        List of EMA values
    """
    if len(prices) < period:
        return []
    
    ema = []
    multiplier = 2 / (period + 1)
    
    # First EMA is simple average
    sma = sum(prices[:period]) / period
    ema.append(sma)
    
    # Subsequent EMAs use exponential smoothing
    for price in prices[period:]:
        ema_value = (price - ema[-1]) * multiplier + ema[-1]
        ema.append(ema_value)
    
    return ema


def calculate_rsi(prices: List[float], period: int = 14) -> float:
    """
    Calculate Relative Strength Index.
    
    Args:
        prices: List of price values
        period: RSI period (default 14)
    
    Returns:
        RSI value (0-100)
    """
    if len(prices) < period + 1:
        return 50.0
    
    deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]
    
    gains = [d if d > 0 else 0 for d in deltas[-period:]]
    losses = [-d if d < 0 else 0 for d in deltas[-period:]]
    
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    
    return rsi


def calculate_vwap(prices: List[float], volumes: List[float]) -> float:
    """
    Calculate Volume Weighted Average Price.
    
    Args:
        prices: List of price values
        volumes: List of volume values
    
    Returns:
        VWAP value
    """
    if len(prices) != len(volumes) or len(prices) == 0:
        return prices[-1] if prices else 0.0
    
    cumulative_pv = sum(p * v for p, v in zip(prices, volumes))
    cumulative_v = sum(volumes)
    
    if cumulative_v == 0:
        return prices[-1]
    
    return cumulative_pv / cumulative_v


def calculate_alignment_score(stock_changes: dict) -> float:
    """
    Calculate market alignment score based on individual stock changes.
    
    Args:
        stock_changes: Dict with stock ticker as key, change_pct as value
    
    Returns:
        Alignment score (0.0 to 1.0)
    """
    if not stock_changes:
        return 0.5
    
    positive_count = sum(1 for change in stock_changes.values() if change > 0)
    total_count = len(stock_changes)
    
    alignment = positive_count / total_count
    return alignment
