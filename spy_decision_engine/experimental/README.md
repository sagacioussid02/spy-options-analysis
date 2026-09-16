# experimental/ — parked, not in the decision path

These modules were moved out of `spy_decision_engine/utils/` on 2026-06-08 during
a deliberate simplification. **Nothing in `main.py` or the engines imports them** —
they produced numbers and reports that never reached the actual BUY/SELL decision,
so they were pure complexity around an 87-line scoring core.

They are parked here (not deleted) so they remain available, but they no longer
clutter the live decision logic.

| Module | What it did | Why parked |
|---|---|---|
| `quantum_monte_carlo.py` | Qiskit-based Monte-Carlo option pricing | Never fed the decision; heavy/opaque |
| `quantum_enhanced_mc.py` | Variant of the above | Never fed the decision |
| `option_pricing.py` | Black-Scholes / Greeks helpers | Not used by the decision; equity-first now |
| `volume_liquidity_tracker.py` | Options volume/OI tracking | Never fed the decision |
| `volume_data_fetcher.py` | Fetches volume/OI for the tracker | Never fed the decision |
| `liquidity_enhanced_analysis.py` | Liquidity scoring on top of volume/OI | Never fed the decision |

## To revive one

Move it back to `utils/` and re-add its import to whatever consumes it. The
intra-cluster imports here use `spy_decision_engine.experimental.<module>`.

## Still in `utils/` on purpose

`behavioral_analytics.py` and `trade_recommendation_engine.py` were **kept** — they
track *your* trading behavior and are the seed of the human-in-the-loop layer, not
black-box market quant.
