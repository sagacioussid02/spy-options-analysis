"""
Prediction ledger — probabilistic forecasts, scored for calibration.

Predictions are cheap and plentiful; trades are expensive and rare. Logging a
falsifiable forecast every session builds a track record even in weeks with
no trade, and Brier scores tell the PM which persona to trust under
disagreement (see committee.py's calibration text and get_regret_stats-style
context injection).

Price predictions carry structured resolution fields (symbol/level/direction)
so sweep.py can auto-resolve them from quotes deterministically — no NLP, no
LLM judgment in the resolution itself. Non-price predictions (macro/industry/
stock) are resolved by the reflection agent with web_search + a one-line
justification, or overridden by the human via advisor.py's /resolve command.
"""
from __future__ import annotations

import json
import re
import uuid
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

from store import store

PREDICTIONS_PATH = Path(__file__).parent / "predictions.json"  # legacy file location
VALID_CATEGORIES = ("price", "macro", "industry", "stock")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class PredictionValidationError(ValueError):
    """Raised when a prediction isn't falsifiable/measurable enough to log."""


@dataclass
class Prediction:
    id: str
    created_at: str
    persona: str
    claim: str
    probability: float
    category: str
    horizon_date: str
    basis: str
    debate_id: Optional[str] = None
    symbol: Optional[str] = None       # price predictions only
    level: Optional[float] = None      # price predictions only
    direction: Optional[str] = None    # "above" | "below" — price only
    resolved: bool = False
    outcome: Optional[bool] = None
    resolution_note: str = ""
    resolved_at: Optional[str] = None
    brier: Optional[float] = None

    def to_dict(self) -> dict:
        return asdict(self)


# Hedge language that makes a claim unfalsifiable ("volatile-ish", "kind of a
# pullback") — reject it and make the proposer state a specific, measurable
# outcome instead.
_VAGUE_PATTERNS = [r"-ish\b", r"\bish\b", r"\bkind of\b", r"\bsort of\b",
                  r"\bsomewhat\b", r"\bmaybe\b", r"\bprobably\b", r"\ba bit\b",
                  r"\bsome\b", r"\baround\b(?!\s*\d)"]


def _is_vague(claim: str) -> bool:
    c = claim.lower()
    return any(re.search(p, c) for p in _VAGUE_PATTERNS)


def _validate(inp: dict) -> list[str]:
    missing = []
    claim = str(inp.get("claim", "")).strip()
    if len(claim) < 15:
        missing.append("claim (must be a specific, measurable statement — not a vague one)")
    elif _is_vague(claim):
        missing.append("claim (too vague/hedged — state a specific, measurable "
                       "outcome, e.g. a level, a date, or a named binary event, "
                       "not 'volatile-ish' style language)")
    try:
        prob = float(inp.get("probability"))
        if not (0.05 <= prob <= 0.95):
            missing.append("probability (must be between 0.05 and 0.95)")
    except (TypeError, ValueError):
        missing.append("probability")
    category = str(inp.get("category", "")).strip().lower()
    if category not in VALID_CATEGORIES:
        missing.append(f"category (must be one of {', '.join(VALID_CATEGORIES)})")
    try:
        date.fromisoformat(str(inp.get("horizon_date")))
    except (ValueError, TypeError):
        missing.append("horizon_date (must be a resolvable ISO date, e.g. 2026-07-31)")
    if category == "price":
        if not inp.get("symbol"):
            missing.append("symbol (required for price predictions, for auto-resolution)")
        if inp.get("level") is None:
            missing.append("level (required for price predictions, for auto-resolution)")
        if str(inp.get("direction", "")).lower() not in ("above", "below"):
            missing.append("direction ('above' or 'below', required for price predictions)")
    return missing


class PredictionStore:
    def __init__(self, path: Optional[Path] = None):
        self.path = path  # explicit path = legacy file mode (tests); else store()

    def _load(self) -> list[dict]:
        if self.path is None:
            return store().load("predictions", []) or []
        if self.path.exists():
            try:
                return json.loads(self.path.read_text())
            except (json.JSONDecodeError, OSError):
                return []
        return []

    def _save(self, entries: list[dict]) -> None:
        if self.path is None:
            store().save("predictions", entries)
        else:
            self.path.write_text(json.dumps(entries, indent=2))

    def log(self, *, persona: str, debate_id: Optional[str] = None, **fields) -> dict:
        missing = _validate(fields)
        if missing:
            raise PredictionValidationError(
                "not falsifiable enough — missing/invalid: " + "; ".join(missing))
        category = str(fields["category"]).strip().lower()
        p = Prediction(
            id="p_" + uuid.uuid4().hex[:10], created_at=_now(), persona=persona,
            claim=str(fields["claim"]).strip(), probability=float(fields["probability"]),
            category=category, horizon_date=str(fields["horizon_date"]),
            basis=str(fields.get("basis", "")).strip(), debate_id=debate_id,
            symbol=(str(fields["symbol"]).upper() if category == "price" else None),
            level=(float(fields["level"]) if category == "price" else None),
            direction=(str(fields["direction"]).lower() if category == "price" else None),
        )
        entries = self._load()
        entries.append(p.to_dict())
        self._save(entries)
        return p.to_dict()

    def get(self, pred_id: str) -> Optional[dict]:
        return next((e for e in self._load() if e["id"] == pred_id), None)

    def open_entries(self) -> list[dict]:
        return [e for e in self._load() if not e["resolved"]]

    def matured(self, today: Optional[date] = None) -> list[dict]:
        today = today or datetime.now(timezone.utc).date()
        out = []
        for e in self.open_entries():
            try:
                if today >= date.fromisoformat(e["horizon_date"]):
                    out.append(e)
            except ValueError:
                continue
        return out

    def resolve(self, pred_id: str, *, outcome: bool, note: str = "") -> Optional[dict]:
        entries = self._load()
        for e in entries:
            if e["id"] == pred_id:
                brier = (e["probability"] - (1.0 if outcome else 0.0)) ** 2
                e.update(resolved=True, outcome=outcome, resolution_note=note,
                         resolved_at=_now(), brier=round(brier, 4))
                self._save(entries)
                return e
        return None

    def resolve_price_predictions(self, quote_fn) -> list[dict]:
        """quote_fn(symbol) -> float|None. Auto-resolves matured price
        predictions deterministically from quotes."""
        resolved = []
        for e in self.matured():
            if e["category"] != "price":
                continue
            quote = quote_fn(e["symbol"])
            if quote is None:
                continue
            outcome = quote > e["level"] if e["direction"] == "above" else quote < e["level"]
            note = f"auto-resolved from quote {quote:g} vs level {e['level']:g} ({e['direction']})"
            resolved.append(self.resolve(e["id"], outcome=outcome, note=note))
        return resolved

    def calibration_table(self) -> dict:
        """Mean Brier score per persona x category, with sample counts — lower
        Brier is better calibrated. Only resolved predictions count."""
        resolved = [e for e in self._load() if e["resolved"] and e.get("brier") is not None]
        agg: dict = {}
        for e in resolved:
            key = (e["persona"], e["category"])
            b = agg.setdefault(key, {"n": 0, "sum_brier": 0.0})
            b["n"] += 1
            b["sum_brier"] += e["brier"]
        table: dict = {}
        for (persona, category), stats in agg.items():
            table.setdefault(persona, {})[category] = {
                "n": stats["n"], "mean_brier": round(stats["sum_brier"] / stats["n"], 4),
            }
        return table
