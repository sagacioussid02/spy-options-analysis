"""
Strategy library — the deterministic entry/exit rules `committee.py`'s
propose_trade `strategy` field has only ever named as free text, never
defined as code. Each function here is a pure function of price/volume
history: given bars up to and including "today" (no lookahead), return a
Signal or None. That purity is what makes engine.py able to replay them
against history at all.

Deliberately price/volume-only, no volatility/IV filter: this codebase's
own get_spy_iv_percentile() is explicitly mocked (no real historical IV
percentile without options-chain analysis it doesn't do), and VIX has real
history but no natural stop/target role here — see the backtest plan.

Reuses spy_decision_engine/utils/indicators.py's calculate_ema/calculate_rsi
rather than reimplementing them.
"""
from __future__ import annotations

import statistics
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

_ENGINE_DIR = Path(__file__).resolve().parent.parent.parent / "spy_decision_engine"
if str(_ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(_ENGINE_DIR))

from utils.indicators import calculate_ema, calculate_rsi  # noqa: E402


@dataclass
class Bar:
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class Signal:
    side: str                 # "buy" — long-only, matches risk_gate's allowed_sides
    target: float
    stop: float
    time_stop_days: int
    conviction: float         # 0..1, informational only — not used to gate the backtest
    rationale: str


def _atr(bars: list[Bar], period: int = 14) -> Optional[float]:
    """Average True Range over the last `period` bars. None if not enough history."""
    if len(bars) < period + 1:
        return None
    trs = []
    for i in range(len(bars) - period, len(bars)):
        prev_close = bars[i - 1].close
        b = bars[i]
        tr = max(b.high - b.low, abs(b.high - prev_close), abs(b.low - prev_close))
        trs.append(tr)
    return sum(trs) / len(trs)


def _vwap_20(bars: list[Bar]) -> Optional[float]:
    window = bars[-20:]
    if len(window) < 20:
        return None
    total_pv = sum(b.close * b.volume for b in window)
    total_v = sum(b.volume for b in window)
    return total_pv / total_v if total_v else None


def trend_follow(bars: list[Bar]) -> Optional[Signal]:
    """EMA9 > EMA21, price above the 20-day VWAP, RSI14 in the 50-70 zone
    (trending but not overbought) — the same three-part condition
    spy_momentum.py already uses for its trade_allowed gate, just applied
    to historical bars instead of the live snapshot."""
    closes = [b.close for b in bars]
    if len(bars) < 30:
        return None
    ema9 = calculate_ema(closes, 9)
    ema21 = calculate_ema(closes, 21)
    rsi = calculate_rsi(closes, 14)
    vwap20 = _vwap_20(bars)
    atr = _atr(bars)
    if not (ema9 and ema21 and vwap20 and atr):
        return None
    price = closes[-1]
    if ema9[-1] > ema21[-1] and price > vwap20 and 50 <= rsi <= 70:
        return Signal(side="buy", target=price + 1.5 * atr, stop=price - 1.0 * atr,
                      time_stop_days=10, conviction=0.55,
                      rationale=f"EMA9>{ema21[-1]:.2f}, price>VWAP20, RSI14={rsi:.1f}")
    return None


def pullback_buy(bars: list[Bar]) -> Optional[Signal]:
    """Established uptrend (EMA9 > EMA21 for the last 5 sessions) with RSI14
    dipping under 45 in the last 3 sessions then recovering above it today —
    buying the dip back into an intact trend, entry near EMA21."""
    closes = [b.close for b in bars]
    if len(bars) < 35:
        return None
    ema9 = calculate_ema(closes, 9)
    ema21 = calculate_ema(closes, 21)
    atr = _atr(bars)
    if len(ema9) < 6 or len(ema21) < 6 or not atr:
        return None
    uptrend = all(a > b for a, b in zip(ema9[-5:], ema21[-5:]))
    if not uptrend:
        return None
    rsi_today = calculate_rsi(closes, 14)
    rsi_recent = [calculate_rsi(closes[:-i] if i else closes, 14) for i in range(1, 4)]
    dipped = any(r < 45 for r in rsi_recent)
    recovered = rsi_today >= 45
    if dipped and recovered:
        price = closes[-1]
        return Signal(side="buy", target=price + 1.3 * atr, stop=price - 0.9 * atr,
                      time_stop_days=8, conviction=0.5,
                      rationale=f"uptrend intact, RSI14 dipped<45 then recovered to {rsi_today:.1f}")
    return None


def breakout(bars: list[Bar]) -> Optional[Signal]:
    """Close breaks the prior 20-session high on volume at least 1.2x its
    20-session average — a volume-confirmed breakout, not just a new high
    on thin volume."""
    if len(bars) < 21:
        return None
    prior20 = bars[-21:-1]
    today = bars[-1]
    prior_high = max(b.high for b in prior20)
    avg_vol20 = sum(b.volume for b in prior20) / len(prior20)
    atr = _atr(bars)
    if not atr or avg_vol20 <= 0:
        return None
    if today.close > prior_high and today.volume >= 1.2 * avg_vol20:
        price = today.close
        return Signal(side="buy", target=price + 2.0 * atr, stop=price - 1.2 * atr,
                      time_stop_days=12, conviction=0.6,
                      rationale=f"close {price:.2f} > 20d high {prior_high:.2f}, "
                                f"vol {today.volume:.0f} >= 1.2x avg {avg_vol20:.0f}")
    return None


def mean_reversion(bars: list[Bar]) -> Optional[Signal]:
    """RSI14 < 30 (oversold) and close below the 20-day mean minus 2 standard
    deviations — a stretched, statistically extreme dip, not just any
    pullback. Tighter stop than the trend strategies since this is fading
    strength, not following it."""
    closes = [b.close for b in bars]
    if len(bars) < 25:
        return None
    rsi = calculate_rsi(closes, 14)
    window = closes[-20:]
    mean20 = sum(window) / len(window)
    stdev20 = statistics.pstdev(window)
    atr = _atr(bars)
    if stdev20 == 0 or not atr:
        return None
    lower_band = mean20 - 2 * stdev20
    price = closes[-1]
    if rsi < 30 and price < lower_band:
        return Signal(side="buy", target=price + 1.2 * atr, stop=price - 0.7 * atr,
                      time_stop_days=6, conviction=0.45,
                      rationale=f"RSI14={rsi:.1f}<30, price {price:.2f} < lower band {lower_band:.2f}")
    return None


STRATEGIES = {
    "trend_follow": trend_follow,
    "pullback_buy": pullback_buy,
    "breakout": breakout,
    "mean_reversion": mean_reversion,
}
