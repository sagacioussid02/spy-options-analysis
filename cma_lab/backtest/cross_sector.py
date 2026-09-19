"""
Cross-sector backtest sweep — runs the full strategy library across a
diversified basket (one ticker per GICS sector already in cli.py's
SECTOR_ETF map) and writes per-ticker-per-strategy summaries to a single
JSON file. This is the dataset the bandit/weighting learning layer (see
the "Design sketch only" section of the strategy-library plan) needs
before it has anything real to learn from — a single ticker's backtest
can't distinguish "this strategy works" from "this strategy works on
AAPL specifically."

Run:
    .venv/bin/python cma_lab/backtest/cross_sector.py --start 2023-09-01 --end 2025-09-01
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_CMA_LAB_DIR = Path(__file__).resolve().parent.parent
if str(_CMA_LAB_DIR) not in sys.path:
    sys.path.insert(0, str(_CMA_LAB_DIR))

from backtest.engine import fetch_earnings, fetch_history, run_backtest, summarize  # noqa: E402
from backtest.strategies import NEEDS_EARNINGS, NEEDS_REFERENCE, STRATEGIES  # noqa: E402

# One representative ticker per sector already in cli.py's SECTOR_ETF map —
# deliberately not every ticker in that map, just enough to cover distinct
# sector behavior (tech, financials, energy, healthcare, discretionary,
# staples, industrials) without an excessive number of yfinance calls.
DEFAULT_BASKET = {
    "AAPL": "XLK",   # Technology
    "JPM": "XLF",    # Financials
    "XOM": "XLE",    # Energy
    "UNH": "XLV",    # Healthcare
    "AMZN": "XLY",   # Consumer Discretionary
    "PG": "XLP",     # Consumer Staples
    "CAT": "XLI",    # Industrials
}


def run_ticker(ticker: str, sector_ticker: str, start: str, end: str,
               spy_bars, earnings_needed: bool) -> dict:
    print(f"\n{ticker} ({sector_ticker}) {start}..{end}")
    bars = fetch_history(ticker, start, end)
    print(f"  {len(bars)} daily bars")

    reference = {"spy": spy_bars}
    if sector_ticker == "SPY":
        reference["sector"] = spy_bars
    else:
        reference["sector"] = fetch_history(sector_ticker, start, end)

    earnings = fetch_earnings(ticker) if earnings_needed else []
    if earnings_needed:
        print(f"  {len(earnings)} reported earnings events")

    per_strategy = {}
    for name, fn in STRATEGIES.items():
        if name in NEEDS_REFERENCE and "sector" not in reference:
            continue
        result = run_backtest(fn, bars, ticker=ticker, reference=reference, earnings=earnings)
        summary = summarize(result)
        per_strategy[name] = summary
        n = summary.get("n", 0)
        if n:
            print(f"  {name:<30} n={n:<4} win_rate={summary['win_rate']:<6} "
                  f"expectancy={summary['expectancy_per_trade']:<8} total_pnl={summary['total_pnl']}")
        else:
            print(f"  {name:<30} n=0 (no trades)")
    return per_strategy


def main() -> None:
    ap = argparse.ArgumentParser(description="Backtest the full strategy library across a "
                                              "diversified cross-sector ticker basket.")
    ap.add_argument("--start", required=True, help="YYYY-MM-DD")
    ap.add_argument("--end", required=True, help="YYYY-MM-DD")
    ap.add_argument("--tickers", nargs="*", help="Override the default basket, e.g. --tickers AAPL JPM XOM. "
                                                  "Sector ETF is looked up from cli.py's SECTOR_ETF map.")
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent / "results" / "cross_sector.json"),
                    help="Where to write the consolidated JSON.")
    args = ap.parse_args()

    if args.tickers:
        from backtest.cli import SECTOR_ETF
        basket = {t.upper(): SECTOR_ETF.get(t.upper(), "SPY") for t in args.tickers}
    else:
        basket = DEFAULT_BASKET

    earnings_needed = bool(NEEDS_EARNINGS & set(STRATEGIES))
    reference_needed = bool(NEEDS_REFERENCE & set(STRATEGIES))

    spy_bars = None
    if reference_needed:
        print("Fetching SPY reference series (shared across all tickers) ...")
        spy_bars = fetch_history("SPY", args.start, args.end)
        print(f"  {len(spy_bars)} daily bars")

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "start": args.start,
        "end": args.end,
        "basket": basket,
        "results": {},
    }
    for ticker, sector_ticker in basket.items():
        out["results"][ticker] = run_ticker(ticker, sector_ticker, args.start, args.end,
                                            spy_bars, earnings_needed)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2))
    print(f"\nWrote {out_path}")

    # Roll up per-strategy stats across the whole basket — this is what the
    # bandit layer's priors will be seeded from.
    print("\n=== Cross-sector rollup (sum across basket) ===")
    rollup = {}
    for ticker_results in out["results"].values():
        for name, summary in ticker_results.items():
            r = rollup.setdefault(name, {"n": 0, "total_pnl": 0.0, "wins": 0})
            n = summary.get("n", 0)
            r["n"] += n
            r["total_pnl"] += summary.get("total_pnl", 0.0)
            r["wins"] += round(summary.get("win_rate", 0.0) * n)
    for name, r in sorted(rollup.items(), key=lambda kv: -kv[1]["total_pnl"]):
        win_rate = r["wins"] / r["n"] if r["n"] else 0.0
        print(f"  {name:<30} n={r['n']:<5} win_rate={win_rate:.3f}  total_pnl={r['total_pnl']:.2f}")


if __name__ == "__main__":
    main()
