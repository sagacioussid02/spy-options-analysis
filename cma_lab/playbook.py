"""
Hypothesis playbook — "let's try this way!!"

Any persona can register a named strategy idea. It trials in the sim lane
ONLY until it earns live eligibility by a DETERMINISTIC rule (code, not an
LLM judgment call) — this is what lets genuinely novel ideas get tried
without letting an untested idea anywhere near real money.
"""
from __future__ import annotations

import json
import re
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

from store import store

PLAYBOOK_PATH = Path(__file__).parent / "playbook.json"  # legacy file location


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")


@dataclass
class Hypothesis:
    id: str
    name: str                  # human-readable
    slug: str                  # normalized, dedup key
    rule: str                  # plain-English entry/exit
    rationale: str
    proposed_by: str
    status: str = "trial"      # trial | active | retired
    min_trials: int = 10
    trials: dict = field(default_factory=lambda: {"n": 0, "wins": 0, "pnl": 0.0})
    trailing_pnls: list = field(default_factory=list)  # last min_trials closed pnls
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class Playbook:
    def __init__(self, path: Optional[Path] = None):
        self.path = path  # explicit path = legacy file mode (tests); else store()

    def _load(self) -> list[dict]:
        if self.path is None:
            return store().load("playbook", []) or []
        if self.path.exists():
            try:
                return json.loads(self.path.read_text())
            except (json.JSONDecodeError, OSError):
                return []
        return []

    def _save(self, entries: list[dict]) -> None:
        if self.path is None:
            store().save("playbook", entries)
        else:
            self.path.write_text(json.dumps(entries, indent=2))

    def register(self, *, name: str, rule: str, rationale: str = "",
                 proposed_by: str = "?", min_trials: int = 10) -> dict:
        """Dedupe by normalized name — registering an existing idea returns it
        unchanged rather than creating a duplicate."""
        slug = _slug(name)
        entries = self._load()
        existing = next((e for e in entries if e["slug"] == slug), None)
        if existing:
            return existing
        h = Hypothesis(id="h_" + uuid.uuid4().hex[:10], name=name.strip(), slug=slug,
                       rule=rule.strip(), rationale=rationale.strip(),
                       proposed_by=proposed_by, min_trials=max(1, int(min_trials or 10)))
        entries.append(h.to_dict())
        self._save(entries)
        return h.to_dict()

    def get(self, hypothesis_id: str) -> Optional[dict]:
        return next((e for e in self._load() if e["id"] == hypothesis_id), None)

    def all(self) -> list[dict]:
        return self._load()

    def update_from_close(self, journal_entry: dict) -> None:
        """Deterministic: update trial stats, then apply the graduation/
        retirement rule. Called by sweep.py whenever a journal entry with a
        hypothesis_id closes."""
        hyp_id = journal_entry.get("hypothesis_id")
        pnl = journal_entry.get("pnl")
        if not hyp_id or pnl is None:
            return
        entries = self._load()
        for e in entries:
            if e["id"] != hyp_id:
                continue
            e["trials"]["n"] += 1
            e["trials"]["wins"] += 1 if pnl > 0 else 0
            e["trials"]["pnl"] = round(e["trials"].get("pnl", 0.0) + pnl, 2)
            trailing = e.get("trailing_pnls", [])
            trailing.append(pnl)
            e["trailing_pnls"] = trailing[-e["min_trials"]:]

            old_status = e["status"]
            n, min_trials = e["trials"]["n"], e["min_trials"]
            if n >= min_trials:
                trailing_sum = sum(e["trailing_pnls"])
                win_rate = e["trials"]["wins"] / n if n else 0.0
                if e["status"] in ("trial", "active") and trailing_sum < 0:
                    e["status"] = "retired"
                elif e["status"] == "trial" and e["trials"]["pnl"] > 0 and win_rate >= 0.5:
                    e["status"] = "active"
            self._save(entries)
            if e["status"] != old_status:
                from events import log_event
                log_event("hypothesis_status_change", hypothesis_id=e["id"], name=e["name"],
                          from_status=old_status, to_status=e["status"],
                          n=e["trials"]["n"], pnl=e["trials"]["pnl"])
            return

    def context_view(self) -> str:
        """Compact text for committee context: trial/active expanded, retired
        collapsed to a one-line cautionary list."""
        entries = self._load()
        if not entries:
            return "(no hypotheses registered yet)"
        lines = []
        for e in entries:
            if e["status"] == "retired":
                continue
            t = e["trials"]
            lines.append(f"- [{e['status']}] {e['name']} (id={e['id']}): {e['rule']} "
                        f"— {t['n']}/{e['min_trials']} trials, {t['wins']} wins, "
                        f"pnl {t['pnl']:.2f}")
        retired = [e for e in entries if e["status"] == "retired"]
        if retired:
            lines.append("- retired (cautionary): " + ", ".join(e["name"] for e in retired))
        return "\n".join(lines) if lines else "(no active/trial hypotheses; some retired)"
