"""
Chunk 5 — the full pipeline: engine -> TradeIntent -> guarded equity agent.

This ties everything together:
    final_decision.json  (your existing SPY engine output)
        -> build_equity_intent()            (chunk 5: canonical intent)
        -> guarded CMA agent                (chunk 4: risk gate + your approval)
        -> review_equity_order via MCP      (chunk 3: Robinhood, simulated)

Reuses, unchanged:
    - the guarded agent + two-layer approval from chunk4_trade.py
    - the risk gate (equity-only, SPY whitelist, size caps)
    - LAB_BLOCK_PLACEMENT (no real order is placed)

Run it:
    .venv/bin/python cma_lab/chunk5_engine_to_agent.py

It reads your latest engine decision, prints the TradeIntent it derived, and —
if the intent is an actionable buy — asks the guarded agent to SIMULATE it.
"""
from __future__ import annotations

import json

from chunk4_trade import RISK, get_or_create_agent, guarded_approve
from lab import (
    client,
    console_url,
    drive_session_with_approval,
    ensure_robinhood_credential,
    get_or_create_environment,
    get_or_create_vault,
)
from trade_intent import build_equity_intent, load_decision


def intent_to_kickoff(intent) -> str:
    """Render the TradeIntent as a precise instruction for the agent."""
    bullets = "\n".join(f"- {r}" for r in intent.rationale[:5])
    limit = f" at a limit of ${intent.limit_price:g}" if intent.limit_price else ""
    return (
        f"Trade intent from the SPY decision engine (id {intent.intent_id}):\n"
        f"  BUY {intent.quantity:g} share(s) of {intent.underlying} as a "
        f"{intent.entry_style} order{limit}.\n"
        f"  Engine score {intent.score:g}, confidence {intent.confidence}.\n"
        f"  Take-profit ~${intent.take_profit:g}, stop ~${intent.stop_loss:g}.\n"
        f"Rationale:\n{bullets}\n\n"
        "Steps: look up my account, then SIMULATE this buy with "
        "review_equity_order. Do NOT place a real order. Report the simulated "
        "quote and any pre-trade alerts."
    )


def main() -> None:
    decision = load_decision()
    intent = build_equity_intent(decision)

    print("[chunk5] engine decision:", decision.get("decision"),
          "| score:", decision.get("final_score"))
    print("[chunk5] derived TradeIntent:")
    print(json.dumps(intent.to_dict(), indent=2))
    print()

    if not intent.is_actionable():
        print("[chunk5] No actionable long signal — nothing to send. "
              "(On a long-only equity account, a non-BUY decision = no trade.)")
        return

    print(f"[chunk5] RISK={RISK}\n")

    env_id = get_or_create_environment()
    vault_id = get_or_create_vault()
    ensure_robinhood_credential(vault_id)
    agent_id = get_or_create_agent()

    session = client().beta.sessions.create(
        agent=agent_id,
        environment_id=env_id,
        vault_ids=[vault_id],
        title=f"chunk5 {intent.intent_id}",
    )
    print(f"[chunk5] session {session.id}")
    print(f"[chunk5] watch live: {console_url(session.id)}\n")

    drive_session_with_approval(
        session.id,
        kickoff_text=intent_to_kickoff(intent),
        approve_fn=guarded_approve,
    )

    print("\n[chunk5] done. That's the whole loop: your SPY engine's signal became "
          "a TradeIntent, passed the risk gate, asked your approval, and simulated "
          "an equity order through Robinhood — no money moved (LAB_BLOCK_PLACEMENT).")


if __name__ == "__main__":
    main()
