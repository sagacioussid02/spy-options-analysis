"""
Chunk 5 — the TradeIntent: a broker-agnostic, canonical description of "what the
strategy wants to do", built from your engine's final_decision.json.

This is the seam your migration plan calls for: the decision engine stays
broker-agnostic and emits a TradeIntent; the broker/agent layer turns that intent
into an actual (gated, approved) order. Keeping this object in the middle means
the engine never needs to know about Robinhood, and the agent never needs to know
about RSI/EMA/sentiment.

Equity-flavored for the initial start (stocks, not options). When you turn options
back on, add option_type/strike/expiry fields here and a build_option_intent().
"""
from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

# spy_decision_engine/reports/final_decision.json, relative to repo root.
DEFAULT_DECISION_PATH = (
    Path(__file__).resolve().parent.parent
    / "spy_decision_engine" / "reports" / "final_decision.json"
)


@dataclass
class TradeIntent:
    intent_id: str
    strategy_name: str
    underlying: str
    asset_type: str            # "equity" for now
    side: str                  # "buy" | "none"  (long-only equity => no short)
    quantity: float            # shares
    entry_style: str           # "limit" | "market"
    limit_price: float | None
    take_profit: float | None
    stop_loss: float | None
    confidence: str            # engine's confidence label, e.g. "HIGH"
    score: float               # engine final_score
    generated_at: str
    rationale: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    def is_actionable(self) -> bool:
        return self.side == "buy" and self.quantity > 0


def load_decision(path: Path | str = DEFAULT_DECISION_PATH) -> dict:
    return json.loads(Path(path).read_text())


def build_equity_intent(decision: dict, *, max_shares: int = 2) -> TradeIntent:
    """
    Map the engine's decision dict into an equity TradeIntent.

    Long-only mapping:
      - a BUY/bullish decision  -> side="buy", a small share count
      - anything else           -> side="none" (we can't short a long-only acct)

    Quantity is deliberately tiny for the initial start (1, or 2 on a STRONG
    signal) and is capped here AND again by the risk gate's max_quantity.
    """
    mc = decision.get("market_conditions", {})
    rec = decision.get("recommendation", {})
    rr = decision.get("risk_reward", {})
    entry = decision.get("entry_strategy", {})

    decision_str = str(decision.get("decision", "")).upper()
    buy_decision = str(rec.get("buy_decision", {}).get("decision", "")).upper()
    is_buy = ("BUY" in decision_str) or (buy_decision == "BUY")

    side = "buy" if is_buy else "none"
    quantity = 0
    if is_buy:
        quantity = 2 if "STRONG" in decision_str else 1
        quantity = min(quantity, max_shares)

    recommended_entry = entry.get("recommended_entry")
    rationale = list(rec.get("explanation", [])) or list(decision.get("bullish_factors", []))

    return TradeIntent(
        intent_id="ti_" + uuid.uuid4().hex[:10],
        strategy_name="spy_decision_engine",
        underlying="SPY",
        asset_type="equity",
        side=side,
        quantity=quantity,
        entry_style="limit" if recommended_entry else "market",
        limit_price=recommended_entry,
        take_profit=rr.get("take_profit_target"),
        stop_loss=rr.get("stop_loss_level"),
        confidence=str(decision.get("confidence", "")),
        score=float(decision.get("final_score", 0) or 0),
        generated_at=datetime.now(timezone.utc).isoformat(),
        rationale=rationale,
    )


if __name__ == "__main__":
    intent = build_equity_intent(load_decision())
    print(json.dumps(intent.to_dict(), indent=2))
    print("\nactionable:", intent.is_actionable())
