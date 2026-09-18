"""
Lessons + suggestions store — the output of reflection, the input to the advisor.

- lessons.md : distilled, human-readable insights the advisor reads before
  proposing ("trend-pullbacks have edge at high conviction; stand aside in
  low-conviction chop"). This is how behavior changes — the advisor reasons
  with accumulated experience.
- risk_suggestions.json : bounded risk-parameter changes reflection *suggests*.
  These are NOT auto-applied — you apply them (via the copilot's guarded
  set_risk_parameter) so a human stays in the loop, consistent with the rest of
  the system.

Both live in the store (collections "lessons" and "risk_suggestions") — the
same files as before locally, Postgres in the cloud.
"""
from __future__ import annotations

from datetime import datetime, timezone

from store import store


def read_lessons() -> str:
    return store().load("lessons") or "(no lessons recorded yet)"


def set_lessons(text: str) -> None:
    store().save("lessons", text)


def list_suggestions() -> list[dict]:
    return store().load("risk_suggestions", []) or []


def add_suggestion(parameter: str, value: str, rationale: str) -> dict:
    entry = {
        "at": datetime.now(timezone.utc).isoformat(),
        "parameter": parameter,
        "value": str(value),
        "rationale": rationale,
        "status": "suggested",
    }
    s = list_suggestions()
    s.append(entry)
    store().save("risk_suggestions", s)
    return entry


def clear_suggestions() -> None:
    store().save("risk_suggestions", [])
