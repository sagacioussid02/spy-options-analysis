"""
Backtest replay engine — walks a strategy function forward through history
one bar at a time, exactly the way it would see live bars arrive, and
applies the same target/stop/time_stop exit discipline sweep.py already
uses for real positions (see _should_close there; ported here rather than
imported since sweep.py's version reads live journal entries + MCP quotes,
not a bar list).

Lookahead discipline: a signal computed from bars[:i+1] (i.e. known at the
close of bar i) fills at bars[i+1].open — never at bar i's own close/high/low.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Callable, Optional

from strategies import Bar, Signal


@dataclass
class Trade:
    entry_date: date
    exit_date: date
    entry_price: float
    exit_price: float
    pnl: float          # per share
    pnl_pct: float
    exit_reason: str    # "target" | "stop" | "time_stop"
    rationale: str


@dataclass
class BacktestResult:
    strategy: str
    ticker: str
    trades: list[Trade] = field(default_factory=list)


def fetch_history(ticker: str, start: str, end: str) -> list[Bar]:
    """Daily OHLCV via yfinance for an arbitrary historical range — the
    existing get_historical_spy_data() only fetches the last 3 months, not
    enough for a real backtest."""
    import yfinance as yf
    df = yf.download(ticker, start=start, end=end, interval="1d",
                     auto_adjust=True, progress=False)
    if df.empty:
        raise ValueError(f"No historical data returned for {ticker} {start}..{end}")
    if hasattr(df.columns, "nlevels") and df.columns.nlevels > 1:
        df.columns = df.columns.get_level_values(0)
    bars = []
    for idx, row in df.iterrows():
        bars.append(Bar(
            date=idx.date(),
            open=float(row["Open"]), high=float(row["High"]),
            low=float(row["Low"]), close=float(row["Close"]),
            volume=float(row["Volume"]),
        ))
    return bars


def _exit_reason(signal: Signal, bar: Bar, days_held: int) -> Optional[str]:
    """Same precedence sweep.py._should_close uses: target/stop before
    time_stop, and between target/stop on the same bar, stop wins (the
    conservative assumption sweep.py itself doesn't need, since it never
    sees both touched on one already-closed bar — here with OHLC we can,
    so we resolve the ambiguity conservatively)."""
    if bar.low <= signal.stop:
        return "stop"
    if bar.high >= signal.target:
        return "target"
    if days_held >= signal.time_stop_days:
        return "time_stop"
    return None


def run_backtest(strategy_fn: Callable[[list[Bar]], Optional[Signal]],
                 bars: list[Bar], *, ticker: str = "", min_lookback: int = 30) -> BacktestResult:
    result = BacktestResult(strategy=strategy_fn.__name__, ticker=ticker)
    i = min_lookback
    n = len(bars)
    while i < n - 1:  # need a next bar to fill on
        window = bars[:i + 1]
        signal = strategy_fn(window)
        if signal is None:
            i += 1
            continue

        entry_bar = bars[i + 1]
        entry_price = entry_bar.open
        entry_idx = i + 1
        j = entry_idx
        exit_price = None
        exit_reason = None
        exit_date = None
        while j < n:
            reason = _exit_reason(signal, bars[j], days_held=j - entry_idx)
            if reason:
                exit_reason = reason
                exit_date = bars[j].date
                exit_price = {"stop": signal.stop, "target": signal.target,
                              "time_stop": bars[j].close}[reason]
                break
            j += 1
        if exit_reason is None:
            # ran off the end of history still open — close at last known price
            exit_reason = "time_stop"
            exit_date = bars[-1].date
            exit_price = bars[-1].close
            j = n - 1

        pnl = exit_price - entry_price
        result.trades.append(Trade(
            entry_date=entry_bar.date, exit_date=exit_date,
            entry_price=entry_price, exit_price=exit_price,
            pnl=round(pnl, 4), pnl_pct=round(pnl / entry_price, 4) if entry_price else 0.0,
            exit_reason=exit_reason, rationale=signal.rationale,
        ))
        i = j + 1  # flat again from the bar after exit — no pyramiding/overlap
    return result


def summarize(result: BacktestResult) -> dict:
    trades = result.trades
    n = len(trades)
    if n == 0:
        return {"strategy": result.strategy, "ticker": result.ticker, "n": 0}

    wins = [t for t in trades if t.pnl > 0]
    losses = [t for t in trades if t.pnl <= 0]
    gross_win = sum(t.pnl for t in wins)
    gross_loss = -sum(t.pnl for t in losses)  # positive number
    total_pnl = sum(t.pnl for t in trades)
    avg_win = gross_win / len(wins) if wins else 0.0
    avg_loss = gross_loss / len(losses) if losses else 0.0
    expectancy = total_pnl / n

    cum = 0.0
    peak = 0.0
    max_dd = 0.0
    for t in trades:
        cum += t.pnl
        peak = max(peak, cum)
        max_dd = max(max_dd, peak - cum)

    return {
        "strategy": result.strategy,
        "ticker": result.ticker,
        "n": n,
        "win_rate": round(len(wins) / n, 3),
        "avg_win": round(avg_win, 3),
        "avg_loss": round(avg_loss, 3),
        "expectancy_per_trade": round(expectancy, 3),
        "total_pnl": round(total_pnl, 2),
        "total_return_pct": round(sum(t.pnl_pct for t in trades), 4),
        "profit_factor": round(gross_win / gross_loss, 2) if gross_loss > 0 else float("inf"),
        "max_drawdown": round(max_dd, 2),
    }
