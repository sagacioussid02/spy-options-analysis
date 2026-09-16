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
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

LESSONS_PATH = Path(__file__).parent / "lessons.md"
SUGGESTIONS_PATH = Path(__file__).parent / "risk_suggestions.json"


def read_lessons() -> str:
    return LESSONS_PATH.read_text() if LESSONS_PATH.exists() else "(no lessons recorded yet)"


def set_lessons(text: str) -> None:
    LESSONS_PATH.write_text(text)


def list_suggestions() -> list[dict]:
    if SUGGESTIONS_PATH.exists():
        try:
            return json.loads(SUGGESTIONS_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            return []
    return []


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
    SUGGESTIONS_PATH.write_text(json.dumps(s, indent=2))
    return entry


def clear_suggestions() -> None:
    SUGGESTIONS_PATH.write_text("[]")
