"""
Exploration budget — a MINIMUM quota of sim proposals that must be off-book:
against the engine's blended lean, a declared gut call, or an unproven
playbook idea. Past experience showed rule-following agents barely trade
because every checklist item has to line up; this is the counterweight — the
desk is told, every session, whether it's under- or over-exploring, so
off-book risk-taking is a deliberate, tracked habit rather than an accident
(and journal.summarize()'s exploration cohort split tells us whether it
actually has edge).
"""
from __future__ import annotations

from journal import TradeJournal
from risk_gate import load_overrides

DEFAULT_EPSILON = 0.25
MIN_EPSILON = 0.10
MAX_EPSILON = 0.40
WINDOW = 20

J = TradeJournal()


def get_epsilon() -> float:
    """Target exploration share, from risk_overrides.json (key
    'exploration_epsilon'), clamped to [0.10, 0.40]."""
    ov = load_overrides()
    try:
        eps = float(ov.get("exploration_epsilon", DEFAULT_EPSILON))
    except (TypeError, ValueError):
        eps = DEFAULT_EPSILON
    return max(MIN_EPSILON, min(eps, MAX_EPSILON))


def _recent_sim_proposals(n: int = WINDOW) -> list[dict]:
    sim = [e for e in J._load() if (e.get("mode") or "live") == "sim"]
    return sim[-n:]


def status() -> dict:
    recent = _recent_sim_proposals()
    n = len(recent)
    n_explore = sum(1 for e in recent if e.get("origin") == "exploration")
    return {
        "window": n,
        "exploration": n_explore,
        "share": round(n_explore / n, 2) if n else None,
        "target": get_epsilon(),
    }


def status_text() -> str:
    s = status()
    if s["window"] == 0:
        return f"Exploration budget: no sim history yet (target {s['target']:.0%})."
    if s["share"] < s["target"] - 0.05:
        return (f"Exploration budget: UNDERWEIGHT — {s['exploration']}/{s['window']} "
                f"recent sim trades ({s['share']:.0%}) were exploratory, target "
                f"{s['target']:.0%}. This session, prefer a hunch, an "
                f"against-the-engine call, or a trial playbook idea over another "
                f"safe setup — set origin_reason accordingly if you do.")
    if s["share"] > s["target"] + 0.10:
        return (f"Exploration budget: OVERWEIGHT — {s['exploration']}/{s['window']} "
                f"recent sim trades ({s['share']:.0%}) were exploratory, target "
                f"{s['target']:.0%}. Prefer an evidence-backed proposal this session.")
    return (f"Exploration budget: on target — {s['exploration']}/{s['window']} "
            f"recent sim trades ({s['share']:.0%}), target {s['target']:.0%}.")
