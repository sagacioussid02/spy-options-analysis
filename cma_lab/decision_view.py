"""
Decision view — engine signal + live read-only briefing, side by side.

This is the "feed the briefing alongside the engine" step. It:
  1. loads your engine's latest decision (final_decision.json) and derives the
     equity TradeIntent (chunk 5),
  2. runs the HOSTED read-only agent (chunk 6) with that engine context, asking
     it to CROSS-CHECK the engine's lean against live account + market reality,
  3. prints one combined view for you to act on.

The agent is still strictly read-only (allowlisted read tools). It never trades —
it grounds the engine's signal in live truth so YOU can decide.

Run:
    .venv/bin/python cma_lab/decision_view.py
    .venv/bin/python cma_lab/decision_view.py --run-engine   # run main.py first (slow)
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from chunk6_read_agent import deploy_agent
from lab import (
    TICKER,
    client,
    console_url,
    drive_session_with_approval,
    ensure_robinhood_credential,
    get_or_create_environment,
    get_or_create_vault,
    report_cost,
)
from trade_intent import build_equity_intent, load_decision

REPO_ROOT = Path(__file__).resolve().parent.parent


def maybe_run_engine() -> None:
    """Optionally run the engine first to refresh final_decision.json."""
    print("[engine] running spy_decision_engine/main.py (this can take a while)...")
    try:
        subprocess.run(
            [sys.executable, "main.py"],
            cwd=str(REPO_ROOT / "spy_decision_engine"),
            check=True,
            env={**os.environ, "TICKER": TICKER},
        )
    except subprocess.CalledProcessError as e:
        print(f"[engine] run failed ({e}); falling back to existing final_decision.json")


def print_engine_header(decision: dict, intent) -> None:
    print("=" * 64)
    print("DECISION VIEW")
    print("=" * 64)
    print("ENGINE SIGNAL (from final_decision.json)")
    print(f"  decision : {decision.get('decision')}  "
          f"(score {decision.get('final_score')}, "
          f"confidence {decision.get('confidence')})")
    print(f"  snapshot : SPY ${decision.get('market_conditions', {}).get('spy_price')} "
          f"at {decision.get('timestamp')}  (trend "
          f"{decision.get('market_conditions', {}).get('trend')})")
    print(f"  intent   : {intent.side} {intent.quantity:g} {intent.underlying} "
          f"{intent.entry_style}"
          + (f" @ ${intent.limit_price:g}" if intent.limit_price else "")
          + f"  (TP ${intent.take_profit:g}, stop ${intent.stop_loss:g})")
    print("-" * 64)


def engine_context_kickoff(decision: dict, intent) -> str:
    mc = decision.get("market_conditions", {})
    return (
        "Here is my SPY decision engine's latest signal (snapshot may be stale):\n"
        f"- decision: {decision.get('decision')} "
        f"(score {decision.get('final_score')}, confidence {decision.get('confidence')})\n"
        f"- snapshot SPY price: ${mc.get('spy_price')} at {decision.get('timestamp')}\n"
        f"- derived intent: {intent.side} {intent.quantity:g} {intent.underlying} "
        f"{intent.entry_style}"
        + (f" at a limit of ${intent.limit_price:g}" if intent.limit_price else "")
        + f"; take-profit ${intent.take_profit:g}, stop ${intent.stop_loss:g}\n\n"
        "Using ONLY your read tools, fetch live account + market data and write a "
        "SHORT briefing that CROSS-CHECKS this engine lean against reality:\n"
        "- Is the live SPY quote close to the engine's snapshot price, or has it "
        "drifted (is the signal stale)?\n"
        f"- Would the suggested entry"
        + (f" (limit ${intent.limit_price:g})" if intent.limit_price else "")
        + " plausibly fill at the live price, or not?\n"
        "- Does my buying power and current SPY position support acting on this?\n"
        "- Any tradability restrictions, or unusual recent order activity?\n"
        "Do NOT trade. End with 'Your call.'"
    )


def main() -> None:
    if "--run-engine" in sys.argv:
        maybe_run_engine()

    decision = load_decision()
    intent = build_equity_intent(decision)
    print_engine_header(decision, intent)

    agent_id = deploy_agent()  # ensure the hosted read-only agent exists

    env_id = get_or_create_environment()
    vault_id = get_or_create_vault()
    ensure_robinhood_credential(vault_id)

    session = client().beta.sessions.create(
        agent=agent_id,
        environment_id=env_id,
        vault_ids=[vault_id],
        title="decision view",
    )
    print(f"LIVE BRIEFING (read-only agent {agent_id})")
    print(f"  watch live: {console_url(session.id)}\n")

    # verbose=False => print only the agent's briefing text, not raw events.
    drive_session_with_approval(
        session.id,
        kickoff_text=engine_context_kickoff(decision, intent),
        approve_fn=lambda name, inp: (False, "Read-only: no actions permitted."),
        verbose=False,
    )

    print("\n" + "=" * 64)
    report_cost(session.id, model="claude-haiku-4-5", label=f"{TICKER}:decision_view")
    print("Engine said WHAT to consider; the agent grounded it in your LIVE "
          "account + market. Your call.")


if __name__ == "__main__":
    main()
