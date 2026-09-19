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

from engine import fetch_history, run_backtest, summarize  # noqa: E402
from strategies import STRATEGIES  # noqa: E402

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
    args = ap.parse_args()

    print(f"Fetching {args.ticker} {args.start}..{args.end} ...")
    bars = fetch_history(args.ticker, args.start, args.end)
    print(f"  {len(bars)} daily bars\n")

    rows = []
    results = {}
    for name, fn in STRATEGIES.items():
        result = run_backtest(fn, bars, ticker=args.ticker)
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
