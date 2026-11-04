"""Bounded JSON backtest runner for the asynchronous trade analyst."""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

CMA_DIR = Path(__file__).resolve().parent.parent
if str(CMA_DIR) not in sys.path:
    sys.path.insert(0, str(CMA_DIR))
BACKTEST_DIR = Path(__file__).resolve().parent
if str(BACKTEST_DIR) not in sys.path:
    sys.path.insert(0, str(BACKTEST_DIR))

from cli import SECTOR_ETF  # noqa: E402
from engine import fetch_earnings, fetch_history, run_backtest, summarize  # noqa: E402
from strategies import NEEDS_EARNINGS, NEEDS_REFERENCE, STRATEGIES  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    ticker = args.ticker.upper()
    bars = fetch_history(ticker, args.start, args.end)
    reference = {}
    sector_ticker = SECTOR_ETF.get(ticker)
    if NEEDS_REFERENCE:
        reference["spy"] = fetch_history("SPY", args.start, args.end)
        if sector_ticker:
            reference["sector"] = (reference["spy"] if sector_ticker == "SPY"
                                   else fetch_history(sector_ticker, args.start, args.end))

    earnings = fetch_earnings(ticker) if NEEDS_EARNINGS else []
    rows = []
    for name, strategy in STRATEGIES.items():
        if name in NEEDS_REFERENCE and "sector" not in reference:
            continue
        row = summarize(run_backtest(
            strategy, bars, ticker=ticker, reference=reference, earnings=earnings,
        ))
        for field in ("profit_factor",):
            value = row.get(field)
            if isinstance(value, float) and not math.isfinite(value):
                row[field] = None
        rows.append(row)

    report = {
        "period_start": args.start,
        "period_end": args.end,
        "daily_bars": len(bars),
        "strategies": rows,
        "data_source": "yfinance adjusted daily bars; no slippage/fees modeled",
    }
    Path(args.output).write_text(json.dumps(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
