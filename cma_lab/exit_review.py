"""
Discretionary exit review — the "should I still be in this?" half of trading.

sweep.py closes positions mechanically at stop/target/time_stop. This adds
judgment: for each held position that has NOT hit a mechanical exit, ask a
model whether the thesis is still intact given the entry's own
kill_criteria and fresh price data, and close early if not.

Bounded on purpose:
  * It can only SELL a position the journal already holds, for its full
    filled quantity, through sweep's existing close path (risk_gate
    evaluate_close: kill switch + whitelist + quantity ceiling).
  * It can never open, add, or size anything.
  * Any error, malformed answer, or missing data means HOLD.
  * EXIT_REVIEW=0 disables it.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from lab import client, lab_env

MODEL = "claude-sonnet-4-6"

SYSTEM = (
    "You manage exits for a small trading account. You are shown ONE open long "
    "position with the thesis and kill_criteria written when it was opened, its "
    "exit plan, and current market data. Decide HOLD or CLOSE. CLOSE only if a "
    "kill criterion has actually been met by the data shown, the thesis is "
    "clearly broken, or risk/reward has decayed so that the remaining upside to "
    "target no longer justifies the risk to stop. Do not close because of "
    "normal noise, a small loss, or boredom; the stop and target already cover "
    "those. If the data needed to judge a criterion is not shown, treat that "
    "criterion as not met. Reply with JSON only: "
    '{"action": "hold" | "close", "reason": "<one or two sentences>"}'
)


def _indicators(symbol: str) -> dict:
    """Daily-close context: last price, 9/21-day EMA, RSI14, 5d/20d change."""
    import yfinance as yf
    closes = yf.Ticker(symbol).history(period="3mo", interval="1d")["Close"].dropna()
    if len(closes) < 22:
        return {}
    delta = closes.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rsi = 100 - 100 / (1 + gain.iloc[-1] / loss.iloc[-1]) if loss.iloc[-1] else 100.0
    return {
        "last_close": round(float(closes.iloc[-1]), 2),
        "ema9": round(float(closes.ewm(span=9).mean().iloc[-1]), 2),
        "ema21": round(float(closes.ewm(span=21).mean().iloc[-1]), 2),
        "rsi14": round(float(rsi), 1),
        "chg_5d_pct": round(float(closes.iloc[-1] / closes.iloc[-6] - 1) * 100, 2),
        "chg_20d_pct": round(float(closes.iloc[-1] / closes.iloc[-21] - 1) * 100, 2),
    }


def review(entry: dict, quote: float) -> tuple[str, str]:
    """Returns ("hold" | "close", reason). Defaults to hold on any failure."""
    if (lab_env("EXIT_REVIEW", "1") or "1").lower() in ("0", "false", "no"):
        return "hold", "exit review disabled"
    try:
        fill = float(entry.get("fill_price") or 0)
        opened = entry.get("executed_at") or entry.get("created_at") or ""
        days = (datetime.now(timezone.utc) - datetime.fromisoformat(opened)).days if opened else None
        ctx = {
            "symbol": entry["symbol"],
            "entry_price": fill,
            "current_price": quote,
            "unrealized_pct": round((quote / fill - 1) * 100, 2) if fill else None,
            "days_held": days,
            "exit_plan": entry.get("exit_plan"),
            "thesis": entry.get("thesis"),
            "kill_criteria": entry.get("kill_criteria"),
            "market_data": _indicators(entry["symbol"]),
        }
        resp = client().messages.create(
            model=MODEL, max_tokens=300, system=SYSTEM,
            messages=[{"role": "user", "content": json.dumps(ctx, indent=2)}],
        )
        text = resp.content[0].text.strip()
        out = json.loads(text[text.index("{"): text.rindex("}") + 1])
        action = str(out.get("action", "hold")).lower()
        if action not in ("hold", "close"):
            return "hold", f"unrecognized action {action!r}"
        return action, str(out.get("reason", "")).strip() or "no reason given"
    except Exception as ex:  # noqa: BLE001
        return "hold", f"review failed ({type(ex).__name__}: {ex}) — holding"
