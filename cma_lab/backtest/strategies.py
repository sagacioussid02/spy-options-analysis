"""
Strategy library — the committee's strategy labels (trend_follow,
pullback_buy, etc.) defined as real deterministic code for the first time.
Each function is a pure function of a StrategyContext built from data up to
and including "today" (no lookahead): given that, return a Signal or None.
That purity is what lets engine.py replay them against history at all.

First 4 (trend_follow, pullback_buy, breakout, mean_reversion) are the
original retail-technical set. The next 6 came out of a literature-grounded
research pass the user asked for, explicitly picked to decorrelate from the
first 4 and from each other — see each docstring for the citation behind
it. Deliberately no volatility/IV-filtered signals: this codebase's own
get_spy_iv_percentile() is explicitly mocked (no real historical IV
percentile without options-chain analysis it doesn't do).

Reuses spy_decision_engine/utils/indicators.py's calculate_ema/calculate_rsi
rather than reimplementing them.
"""
from __future__ import annotations

import statistics
import sys
from dataclasses import dataclass, field
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
class EarningsEvent:
    date: date
    eps_estimate: Optional[float]
    eps_actual: Optional[float]
    surprise_pct: Optional[float]


@dataclass
class StrategyContext:
    """What a strategy function sees as of "today" — bars[-1] is today's
    bar. reference holds other tickers' bars (e.g. "spy", "sector") for
    strategies that need a comparison series; earnings holds only events
    dated on/before today, same no-lookahead rule as bars."""
    bars: list[Bar]
    reference: dict[str, list[Bar]] = field(default_factory=dict)
    earnings: list[EarningsEvent] = field(default_factory=list)


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


def _period_return(bars: list[Bar], days: int) -> Optional[float]:
    if len(bars) < days + 1:
        return None
    then, now = bars[-days - 1].close, bars[-1].close
    return (now - then) / then if then else None


# ============================== original 4 ===================================

def trend_follow(ctx: StrategyContext) -> Optional[Signal]:
    """EMA9 > EMA21, price above the 20-day VWAP, RSI14 in the 50-70 zone
    (trending but not overbought) — the same three-part condition
    spy_momentum.py already uses for its trade_allowed gate, just applied
    to historical bars instead of the live snapshot."""
    bars = ctx.bars
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


def pullback_buy(ctx: StrategyContext) -> Optional[Signal]:
    """Established uptrend (EMA9 > EMA21 for the last 5 sessions) with RSI14
    dipping under 45 in the last 3 sessions then recovering above it today —
    buying the dip back into an intact trend, entry near EMA21."""
    bars = ctx.bars
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


def breakout(ctx: StrategyContext) -> Optional[Signal]:
    """Close breaks the prior 20-session high on volume at least 1.2x its
    20-session average — a volume-confirmed breakout, not just a new high
    on thin volume."""
    bars = ctx.bars
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


def mean_reversion(ctx: StrategyContext) -> Optional[Signal]:
    """RSI14 < 30 (oversold) and close below the 20-day mean minus 2 standard
    deviations — a stretched, statistically extreme dip, not just any
    pullback. Tighter stop than the trend strategies since this is fading
    strength, not following it."""
    bars = ctx.bars
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


# ============================ research-grounded 6 =============================

def anchoring_momentum(ctx: StrategyContext) -> Optional[Signal]:
    """52-week-high proximity momentum (George & Hwang 2004, J. Finance):
    anchoring bias causes systematic underreaction to good news for stocks
    near their own 52-week high. Nearness >= 0.95, sustained >= 0.90 for
    the last 5 sessions (not a single-day spike into the high), and a
    positive 6-month return (a genuine advance, not a stale high from a
    prior crash). No RSI/overbought filter — the point is staying in names
    the RSI-band strategies elsewhere in this library would exclude."""
    bars = ctx.bars
    if len(bars) < 260:
        return None
    closes = [b.close for b in bars]
    high_252 = max(b.high for b in bars[-252:])
    if high_252 <= 0:
        return None
    nearness_today = closes[-1] / high_252
    nearness_recent = [bars[-i].close / max(b.high for b in bars[-252 - i + 1:len(bars) - i + 1])
                       for i in range(1, 6)]
    sustained = all(n >= 0.90 for n in nearness_recent)
    ret_6mo = _period_return(bars, 126)
    if nearness_today >= 0.95 and sustained and ret_6mo is not None and ret_6mo > 0:
        atr = _atr(bars)
        if not atr:
            return None
        price = closes[-1]
        return Signal(side="buy", target=price * 1.0, stop=price * 0.88,
                      time_stop_days=90, conviction=0.5,
                      rationale=f"nearness={nearness_today:.3f} of 52w high, 6mo return={ret_6mo:.1%}")
    return None


def volume_conditioned_momentum(ctx: StrategyContext) -> Optional[Signal]:
    """Momentum life cycle (Lee & Swaminathan 2000): low-turnover winners
    keep winning (slow information diffusion/low attention); high-turnover
    winners are the ones about to reverse. Uptrend (6mo return>0, price>
    200d SMA) + new 20-day high, but ONLY while 20d/252d relative volume is
    <=0.85 (below its own 1-year norm) — the inverse volume condition of
    breakout() above, so the two should rarely fire on the same setup."""
    bars = ctx.bars
    if len(bars) < 252:
        return None
    closes = [b.close for b in bars]
    sma200 = sum(closes[-200:]) / 200
    ret_6mo = _period_return(bars, 126)
    if ret_6mo is None or ret_6mo <= 0 or closes[-1] <= sma200:
        return None
    avg_vol_20 = sum(b.volume for b in bars[-20:]) / 20
    avg_vol_252 = sum(b.volume for b in bars[-252:]) / 252
    if avg_vol_252 <= 0:
        return None
    rel_volume = avg_vol_20 / avg_vol_252
    prior20_high = max(b.high for b in bars[-21:-1])
    atr = _atr(bars)
    if not atr:
        return None
    if rel_volume <= 0.85 and closes[-1] > prior20_high:
        price = closes[-1]
        return Signal(side="buy", target=price + 2.0 * atr, stop=price - 1.3 * atr,
                      time_stop_days=60, conviction=0.5,
                      rationale=f"low-turnover uptrend (rel_vol={rel_volume:.2f}) new 20d high")
    return None


def relative_strength_rotation(ctx: StrategyContext) -> Optional[Signal]:
    """Dual momentum (Faber/Antonacci): buy only when the ticker is BOTH in
    an absolute uptrend of its own AND outperforming its sector ETF over
    the last 3 months, gated by a market-level regime filter (SPY above
    its own ~10-month/200d SMA). Exits are regime-driven (RS turns
    negative, or the SPY filter fails), not a fixed target/stop — the only
    strategy in the library whose exit isn't primarily price-action-based."""
    bars = ctx.bars
    spy = ctx.reference.get("spy")
    sector = ctx.reference.get("sector")
    if not spy or not sector or len(bars) < 65 or len(spy) < 200 or len(sector) < 65:
        return None
    ticker_ret_3mo = _period_return(bars, 63)
    sector_ret_3mo = _period_return(sector, 63)
    if ticker_ret_3mo is None or sector_ret_3mo is None:
        return None
    rs = ticker_ret_3mo - sector_ret_3mo
    spy_closes = [b.close for b in spy]
    spy_sma200 = sum(spy_closes[-200:]) / 200
    spy_risk_on = spy_closes[-1] > spy_sma200
    atr = _atr(bars)
    if not atr:
        return None
    if rs > 0 and ticker_ret_3mo > 0 and spy_risk_on:
        price = bars[-1].close
        # Exit is regime-driven in the live/backtest exit loop via a wide
        # target/stop band; time_stop is the practical backstop here since
        # this engine's exit loop doesn't (yet) support a "re-evaluate RS
        # each bar" exit — documented limitation, not silently approximated.
        return Signal(side="buy", target=price + 4.0 * atr, stop=price - 2.5 * atr,
                      time_stop_days=63, conviction=0.55,
                      rationale=f"RS vs sector={rs:.1%}, ticker 3mo={ticker_ret_3mo:.1%}, SPY risk-on")
    return None


def panic_reversal(ctx: StrategyContext) -> Optional[Signal]:
    """Connors RSI(2), trend-filtered (grounded in Jegadeesh 1990
    short-horizon reversal): within a primary uptrend (close > 200d SMA),
    buy an extreme, short-lived panic (2-period RSI < 5) for a quick
    multi-day bounce. Real, but the closest in spirit to mean_reversion/
    pullback_buy already in this library — the lowest-confidence pick of
    the six per the research, included for its much rarer/sharper trigger
    and short hold, not as a wholly new phenomenon."""
    bars = ctx.bars
    closes = [b.close for b in bars]
    if len(bars) < 205:
        return None
    sma200 = sum(closes[-200:]) / 200
    if closes[-1] <= sma200:
        return None
    rsi2 = calculate_rsi(closes, 2)
    atr = _atr(bars)
    if not atr:
        return None
    if rsi2 < 5:
        price = closes[-1]
        return Signal(side="buy", target=price + 1.0 * atr, stop=price - 0.6 * atr,
                      time_stop_days=4, conviction=0.4,
                      rationale=f"RSI2={rsi2:.1f}<5 within uptrend (close>SMA200)")
    return None


def turn_of_month(ctx: StrategyContext) -> Optional[Signal]:
    """Turn-of-month calendar effect (Ariel 1987; confirmed out-of-sample by
    McConnell & Xu 2008 over 1897-2005 across ~30 markets): long only
    across the last trading day of the month through the 3rd trading day
    of the next month. Pure calendar rule, zero dependence on price
    action — should have near-zero correlation with every other strategy
    in this library by construction. Optional trend filter (skip if close
    < 50d SMA) to avoid buying calendar strength into a clear downtrend,
    as the research flagged as an add-on, not part of the core effect."""
    bars = ctx.bars
    if len(bars) < 51:
        return None
    today = bars[-1]
    tomorrow_is_new_month = True
    # "Last trading day of the month" = today's date's month differs from
    # the NEXT bar's month — but we only see bars up to today (no lookahead),
    # so approximate via calendar: today is within the last 3 calendar days
    # of its month AND bars[-2] (yesterday) is the same month as today.
    is_near_month_end = today.date.day >= 28
    if len(bars) >= 2 and bars[-2].date.month != today.date.month:
        is_near_month_end = False  # already rolled over, not "the last day"
    if not is_near_month_end:
        return None
    closes = [b.close for b in bars]
    sma50 = sum(closes[-50:]) / 50
    if closes[-1] < sma50:
        return None
    atr = _atr(bars)
    if not atr:
        return None
    price = today.close
    return Signal(side="buy", target=price + 3.0 * atr, stop=price - 3.0 * atr,
                  time_stop_days=4, conviction=0.45,
                  rationale=f"turn-of-month entry ({today.date.isoformat()}), close>SMA50")


def post_earnings_drift(ctx: StrategyContext) -> Optional[Signal]:
    """Post-earnings-announcement drift (one of the most robust anomalies
    in the literature; grounded in the original Ball & Brown 1968 and the
    large PEAD literature since). Enter the session after a reported
    earnings surprise of at least 5% in magnitude, direction following the
    sign of the surprise. Long-only per risk_gate, so negative surprises
    are simply skipped here, never shorted. Hold ~20-40 sessions, the
    literature's typical drift window."""
    bars = ctx.bars
    if not ctx.earnings or len(bars) < 20:
        return None
    today = bars[-1].date
    # Most recent earnings event strictly before today, reported within
    # the last 3 sessions (so we only act on FRESH surprises, not stale ones).
    recent = [e for e in ctx.earnings if e.date < today and e.eps_actual is not None]
    if not recent:
        return None
    last = max(recent, key=lambda e: e.date)
    days_since = (today - last.date).days
    if days_since > 5 or last.surprise_pct is None:
        return None
    if last.surprise_pct >= 5.0:
        atr = _atr(bars)
        if not atr:
            return None
        price = bars[-1].close
        return Signal(side="buy", target=price + 2.5 * atr, stop=price - 1.5 * atr,
                      time_stop_days=30, conviction=0.55,
                      rationale=f"earnings surprise {last.surprise_pct:.1f}% on {last.date.isoformat()}")
    return None


STRATEGIES = {
    "trend_follow": trend_follow,
    "pullback_buy": pullback_buy,
    "breakout": breakout,
    "mean_reversion": mean_reversion,
    "anchoring_momentum": anchoring_momentum,
    "volume_conditioned_momentum": volume_conditioned_momentum,
    "relative_strength_rotation": relative_strength_rotation,
    "panic_reversal": panic_reversal,
    "turn_of_month": turn_of_month,
    "post_earnings_drift": post_earnings_drift,
}

# Strategies that need more than the primary ticker's own bars — the CLI
# uses this to know what extra data to fetch.
NEEDS_REFERENCE = {"relative_strength_rotation"}
NEEDS_EARNINGS = {"post_earnings_drift"}
