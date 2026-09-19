"""
Backtest CLI — replay the strategy library (strategies.py) against real
historical data and, optionally, seed cma_lab/playbook.py with the results
so the committee sees backtested track record as context, the same way it
already sees live track record.

Run:
    .venv/bin/python cma_lab/backtest/cli.py AAPL --start 2023-01-01 --end 2026-09-01
    .venv/bin/python cma_lab/backtest/cli.py AAPL --start 2023-01-01 --end 2026-09-01 --seed-playbook
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_CMA_LAB_DIR = Path(__file__).resolve().parent.parent
if str(_CMA_LAB_DIR) not in sys.path:
    sys.path.insert(0, str(_CMA_LAB_DIR))

from engine import fetch_earnings, fetch_history, run_backtest, summarize  # noqa: E402
from strategies import NEEDS_EARNINGS, NEEDS_REFERENCE, STRATEGIES  # noqa: E402

_RULE_TEXT = {
    "trend_follow": "EMA9>EMA21, price>VWAP20, RSI14 in 50-70. Target 1.5xATR, "
                    "stop 1.0xATR, time_stop 10 sessions.",
    "pullback_buy": "Established uptrend (EMA9>EMA21 x5 sessions), RSI14 dipped "
                    "<45 in last 3 sessions then recovered. Target 1.3xATR, "
                    "stop 0.9xATR, time_stop 8 sessions.",
    "breakout": "Close > 20-session high on volume >=1.2x 20-session average. "
               "Target 2.0xATR, stop 1.2xATR, time_stop 12 sessions.",
    "mean_reversion": "RSI14<30 and close < 20-day mean - 2*stdev. Target 1.2xATR, "
                      "stop 0.7xATR, time_stop 6 sessions.",
    "anchoring_momentum": "Close within 5% of 252-session high, sustained >=90% "
                          "nearness over last 5 sessions, positive 6mo return. "
                          "Target = high (no premium), stop 12% below entry, time_stop 90 sessions.",
    "volume_conditioned_momentum": "6mo return>0, price>SMA200, new 20-session high, "
                                   "but 20d/252d relative volume <=0.85. Target 2.0xATR, "
                                   "stop 1.3xATR, time_stop 60 sessions.",
    "relative_strength_rotation": "3mo return beats sector ETF's 3mo return, own 3mo "
                                  "return>0, SPY>SMA200 (risk-on). Target 4.0xATR, "
                                  "stop 2.5xATR, time_stop 63 sessions.",
    "panic_reversal": "Close>SMA200 (uptrend) and RSI(2)<5 (panic dip). Target 1.0xATR, "
                      "stop 0.6xATR, time_stop 4 sessions.",
    "turn_of_month": "Entry on/near the last trading day of the month, close>SMA50. "
                     "Target 3.0xATR, stop 3.0xATR, time_stop 4 sessions.",
    "post_earnings_drift": "Earnings surprise >=+5% reported within the last 5 sessions. "
                           "Target 2.5xATR, stop 1.5xATR, time_stop 30 sessions.",
}

SECTOR_ETF = {
    "AAPL": "XLK", "MSFT": "XLK", "NVDA": "XLK", "GOOGL": "XLK", "GOOG": "XLK",
    "META": "XLK", "AVGO": "XLK", "AMD": "XLK", "CRM": "XLK", "ORCL": "XLK",
    "JPM": "XLF", "BAC": "XLF", "WFC": "XLF", "GS": "XLF", "MS": "XLF",
    "XOM": "XLE", "CVX": "XLE", "COP": "XLE",
    "JNJ": "XLV", "UNH": "XLV", "PFE": "XLV", "LLY": "XLV", "ABBV": "XLV",
    "AMZN": "XLY", "TSLA": "XLY", "HD": "XLY", "MCD": "XLY", "NKE": "XLY",
    "PG": "XLP", "KO": "XLP", "PEP": "XLP", "WMT": "XLP", "COST": "XLP",
    "BA": "XLI", "CAT": "XLI", "GE": "XLI", "UPS": "XLI",
    "SPY": "SPY",
}


def _print_table(rows: list[dict]) -> None:
    cols = ["strategy", "n", "win_rate", "avg_win", "avg_loss",
            "expectancy_per_trade", "total_pnl", "profit_factor", "max_drawdown"]
    widths = {c: max(len(c), *(len(str(r.get(c, ""))) for r in rows)) for c in cols}
    header = "  ".join(c.ljust(widths[c]) for c in cols)
    print(header)
    print("-" * len(header))
    for r in rows:
        print("  ".join(str(r.get(c, "")).ljust(widths[c]) for c in cols))


def _seed_playbook(ticker: str, strategy_name: str, result) -> None:
    from playbook import Playbook
    pb = Playbook()
    h = pb.register(name=f"{strategy_name} ({ticker}, backtest)",
                    rule=_RULE_TEXT[strategy_name],
                    rationale=f"Backtested over {len(result.trades)} historical trades before any live use.",
                    proposed_by="backtest", min_trials=10)
    for t in sorted(result.trades, key=lambda t: t.entry_date):
        pb.update_from_close({"hypothesis_id": h["id"], "pnl": t.pnl})
    final = pb.get(h["id"])
    print(f"  seeded playbook hypothesis {h['id']} ({strategy_name}, {ticker}) "
          f"-> status={final['status']}, n={final['trials']['n']}, "
          f"wins={final['trials']['wins']}, pnl={final['trials']['pnl']}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Backtest the strategy library against real history.")
    ap.add_argument("ticker")
    ap.add_argument("--start", required=True, help="YYYY-MM-DD")
    ap.add_argument("--end", required=True, help="YYYY-MM-DD")
    ap.add_argument("--seed-playbook", action="store_true",
                    help="Register each strategy as a playbook hypothesis and replay "
                         "its backtested trades through the real graduation rule.")
    ap.add_argument("--sector", help="Sector ETF ticker to use for relative_strength_rotation "
                                     "(overrides the built-in SECTOR_ETF map).")
    args = ap.parse_args()

    print(f"Fetching {args.ticker} {args.start}..{args.end} ...")
    bars = fetch_history(args.ticker, args.start, args.end)
    print(f"  {len(bars)} daily bars\n")

    reference = {}
    if any(name in NEEDS_REFERENCE for name in STRATEGIES):
        sector_ticker = args.sector or SECTOR_ETF.get(args.ticker.upper())
        print("Fetching reference series for relative_strength_rotation ...")
        spy_bars = fetch_history("SPY", args.start, args.end)
        reference["spy"] = spy_bars
        if sector_ticker:
            reference["sector"] = spy_bars if sector_ticker == "SPY" else fetch_history(sector_ticker, args.start, args.end)
            print(f"  spy: {len(reference['spy'])} bars, sector({sector_ticker}): {len(reference['sector'])} bars\n")
        else:
            print(f"  no sector ETF mapping for {args.ticker} — relative_strength_rotation will sit out "
                  f"(pass --sector to supply one)\n")

    earnings = []
    if any(name in NEEDS_EARNINGS for name in STRATEGIES):
        print(f"Fetching earnings history for {args.ticker} ...")
        earnings = fetch_earnings(args.ticker)
        print(f"  {len(earnings)} reported earnings events\n")

    rows = []
    results = {}
    for name, fn in STRATEGIES.items():
        if name in NEEDS_REFERENCE and "sector" not in reference:
            print(f"  skipping {name}: no sector reference available")
            continue
        result = run_backtest(fn, bars, ticker=args.ticker, reference=reference, earnings=earnings)
        results[name] = result
        rows.append(summarize(result))

    _print_table(rows)

    if args.seed_playbook:
        print("\nSeeding playbook (real, non-temp — this affects what the committee sees):")
        for name, result in results.items():
            if result.trades:
                _seed_playbook(args.ticker, name, result)
            else:
                print(f"  skipping {name}: 0 backtested trades, nothing to seed")


if __name__ == "__main__":
    main()
