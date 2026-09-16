"""
Trade journal — the memory the system learns from.

This is what separates "a trader" from "a rules machine": every proposal and
trade is recorded WITH its thesis, conviction, regime, and (after it closes) a
reflection. The reflection loop reads this to adjust behavior; the advisor reads
recent entries + lessons to reason like someone who remembers what happened.

Storage is a human-readable JSON list (cma_lab/journal.json) so you can read it
yourself — the journal is for you as much as for the agent.

Lifecycle of an entry:
    proposed -> approved -> executed -> closed (+reflection)
    proposed -> rejected
"""
from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

JOURNAL_PATH = Path(__file__).parent / "journal.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class JournalValidationError(ValueError):
    """Raised when a proposal is missing a required falsifiable-proposal field."""


@dataclass
class JournalEntry:
    id: str
    created_at: str
    status: str                       # proposed|approved|rejected|executed|closed
    # --- the thinking ---
    thesis: str                       # why, in plain language
    conviction: float                 # 0..1 — drives (bounded) size
    regime: str                       # e.g. "bullish_trend", "chop", "high_vol"
    strategy: str                     # named playbook, e.g. "pullback_buy"
    # --- the proposed trade ---
    side: str                         # "buy"
    symbol: str                       # "SPY"
    quantity: float
    entry_style: str                  # "limit" | "market"
    limit_price: Optional[float]
    # --- falsifiability (required on every proposal — see openspec falsifiable-proposals) ---
    kill_criteria: str = ""           # pre-registered: what would prove this wrong
    exit_plan: dict = field(default_factory=dict)  # {target, stop, time_stop}
    # --- lane / provenance ---
    mode: str = "live"                # "sim" | "live"
    origin: str = "advisor"           # "advisor" | "committee" | "exploration"
    debate_id: Optional[str] = None
    hypothesis_id: Optional[str] = None
    # --- context snapshot from the engine ---
    engine_score: Optional[float] = None
    snapshot_price: Optional[float] = None
    # --- human + execution + outcome (filled in over time) ---
    human_notes: str = ""             # tweaks / approval or rejection comment
    fill_price: Optional[float] = None
    filled_qty: Optional[float] = None
    executed_at: Optional[str] = None
    exit_price: Optional[float] = None
    pnl: Optional[float] = None
    closed_at: Optional[str] = None
    reflection: str = ""              # what I expected / what happened / the lesson
    thesis_grade: Optional[str] = None  # right_win|right_loss|wrong_win|wrong_loss

    def to_dict(self) -> dict:
        return asdict(self)


class TradeJournal:
    def __init__(self, path: Path = JOURNAL_PATH):
        self.path = path

    # ---------------------------- storage ----------------------------
    def _load(self) -> list[dict]:
        if self.path.exists():
            try:
                return json.loads(self.path.read_text())
            except (json.JSONDecodeError, OSError):
                return []
        return []

    def _save(self, entries: list[dict]) -> None:
        self.path.write_text(json.dumps(entries, indent=2))

    # ---------------------------- writes -----------------------------
    def propose(self, *, thesis: str, conviction: float, regime: str, strategy: str,
                side: str, symbol: str, quantity: float, entry_style: str,
                kill_criteria: str, exit_plan: dict,
                limit_price: Optional[float] = None, engine_score: Optional[float] = None,
                snapshot_price: Optional[float] = None, mode: str = "live",
                origin: str = "advisor", debate_id: Optional[str] = None,
                hypothesis_id: Optional[str] = None) -> JournalEntry:
        """Record a proposal. Raises JournalValidationError (no entry written) if
        thesis, kill_criteria, conviction, or a full exit_plan are missing — every
        proposal must be falsifiable before it exists."""
        exit_plan = exit_plan or {}
        missing = []
        if not thesis or not str(thesis).strip():
            missing.append("thesis")
        if not kill_criteria or not str(kill_criteria).strip():
            missing.append("kill_criteria")
        for k in ("target", "stop", "time_stop"):
            if exit_plan.get(k) in (None, ""):
                missing.append(f"exit_plan.{k}")
        if conviction is None:
            missing.append("conviction")
        if missing:
            raise JournalValidationError(
                "missing required field(s): " + ", ".join(missing) + " — a proposal "
                "needs thesis, kill_criteria, conviction, and a full exit_plan "
                "(target, stop, time_stop)."
            )
        entry = JournalEntry(
            id="je_" + uuid.uuid4().hex[:10], created_at=_now(), status="proposed",
            thesis=str(thesis).strip(), conviction=float(conviction), regime=regime,
            strategy=strategy, side=side, symbol=symbol.upper(), quantity=float(quantity),
            entry_style=entry_style, limit_price=limit_price,
            kill_criteria=str(kill_criteria).strip(), exit_plan=exit_plan,
            mode=mode, origin=origin, debate_id=debate_id, hypothesis_id=hypothesis_id,
            engine_score=engine_score, snapshot_price=snapshot_price,
        )
        entries = self._load()
        entries.append(entry.to_dict())
        self._save(entries)
        return entry

    def _update(self, entry_id: str, **changes) -> Optional[dict]:
        entries = self._load()
        for e in entries:
            if e["id"] == entry_id:
                e.update(changes)
                self._save(entries)
                return e
        return None

    def approve(self, entry_id: str, *, quantity: Optional[float] = None,
                limit_price: Optional[float] = None, note: str = "") -> Optional[dict]:
        """Approve a proposal, optionally tweaking size/limit at approval time."""
        changes: dict = {"status": "approved", "human_notes": note}
        if quantity is not None:
            changes["quantity"] = float(quantity)
        if limit_price is not None:
            changes["limit_price"] = float(limit_price)
        return self._update(entry_id, **changes)

    def reject(self, entry_id: str, note: str = "") -> Optional[dict]:
        return self._update(entry_id, status="rejected", human_notes=note)

    def mark_executed(self, entry_id: str, *, fill_price: float,
                      filled_qty: float) -> Optional[dict]:
        return self._update(entry_id, status="executed", fill_price=fill_price,
                            filled_qty=filled_qty, executed_at=_now())

    def open_sim(self, entry_id: str, *, fill_price: float,
                 filled_qty: float) -> Optional[dict]:
        """Sim lane: proposal -> open directly, no human approve/execute step."""
        return self._update(entry_id, status="open", fill_price=fill_price,
                            filled_qty=filled_qty, executed_at=_now())

    def close(self, entry_id: str, *, exit_price: float, reflection: str = "") -> Optional[dict]:
        entries = self._load()
        for e in entries:
            if e["id"] == entry_id:
                pnl = None
                if e.get("fill_price") is not None and e.get("filled_qty"):
                    pnl = (exit_price - e["fill_price"]) * e["filled_qty"]
                e.update(status="closed", exit_price=exit_price, pnl=pnl,
                         closed_at=_now(), reflection=reflection)
                self._save(entries)
                return e
        return None

    # ---------------------------- reads ------------------------------
    def get(self, entry_id: str) -> Optional[dict]:
        return next((e for e in self._load() if e["id"] == entry_id), None)

    def recent(self, n: int = 10) -> list[dict]:
        return self._load()[-n:]

    def pending_proposals(self) -> list[dict]:
        return [e for e in self._load() if e["status"] == "proposed"]

    def open_positions(self) -> list[dict]:
        return [e for e in self._load() if e["status"] == "open"]

    def summarize(self) -> dict:
        """The learning view: edge by strategy / regime / conviction bucket.
        Reports COUNTS alongside win rates so the reflection loop can refuse to
        over-learn from tiny samples. Live trades are weighted 3x sim trades —
        live outcomes are real-money evidence; sim gives volume but weaker signal.
        Sample counts are always broken out by lane so nothing sim-only gets
        reported as if it were live-confirmed edge."""
        closed = [e for e in self._load() if e["status"] == "closed" and e.get("pnl") is not None]

        def _weight(e) -> float:
            return 3.0 if (e.get("mode") or "live") == "live" else 1.0

        def bucketize(key_fn) -> dict:
            out: dict = {}
            for e in closed:
                k = key_fn(e)
                b = out.setdefault(k, {"n": 0, "n_sim": 0, "n_live": 0, "wins": 0,
                                       "pnl": 0.0, "_w_pnl": 0.0, "_w_wins": 0.0, "_w_total": 0.0})
                w = _weight(e)
                win = 1 if e["pnl"] > 0 else 0
                b["n"] += 1
                b["n_live" if (e.get("mode") or "live") == "live" else "n_sim"] += 1
                b["wins"] += win
                b["pnl"] += e["pnl"]
                b["_w_pnl"] += e["pnl"] * w
                b["_w_wins"] += win * w
                b["_w_total"] += w
            for b in out.values():
                b["win_rate"] = round(b["wins"] / b["n"], 2) if b["n"] else 0.0
                b["pnl"] = round(b["pnl"], 2)
                b["weighted_pnl"] = round(b.pop("_w_pnl"), 2)
                w_total = b.pop("_w_total")
                b["weighted_win_rate"] = round(b.pop("_w_wins") / w_total, 2) if w_total else 0.0
            return out

        def conv_bucket(e) -> str:
            c = e.get("conviction") or 0
            return "high(>=0.7)" if c >= 0.7 else ("med(0.4-0.7)" if c >= 0.4 else "low(<0.4)")

        n_live = sum(1 for e in closed if (e.get("mode") or "live") == "live")
        n_sim = len(closed) - n_live
        return {
            "closed_trades": len(closed),
            "closed_live": n_live,
            "closed_sim": n_sim,
            "total_pnl": round(sum(e["pnl"] for e in closed), 2),
            "by_strategy": bucketize(lambda e: e.get("strategy", "?")),
            "by_regime": bucketize(lambda e: e.get("regime", "?")),
            "by_conviction": bucketize(conv_bucket),
            "by_origin": bucketize(lambda e: "exploration" if e.get("origin") == "exploration"
                                    else "on_book"),
            "by_thesis_grade": bucketize(lambda e: e.get("thesis_grade") or "ungraded"),
        }


if __name__ == "__main__":
    # Demo on a temp journal so it doesn't touch your real one.
    import tempfile
    j = TradeJournal(Path(tempfile.mkstemp(suffix=".json")[1]))

    e1 = j.propose(thesis="Pullback to VWAP in an uptrend; sentiment positive.",
                   conviction=0.72, regime="bullish_trend", strategy="pullback_buy",
                   side="buy", symbol="SPY", quantity=2, entry_style="limit",
                   kill_criteria="Breaks and closes below VWAP on volume.",
                   exit_plan={"target": 693.0, "stop": 684.0, "time_stop": "2026-07-10"},
                   limit_price=687.28, engine_score=81.3, snapshot_price=694.07)
    j.approve(e1.id, quantity=1, note="Halving size — chop risk into CPI.")
    j.mark_executed(e1.id, fill_price=688.10, filled_qty=1)
    j.close(e1.id, exit_price=693.0, reflection="Thesis right, sized down well; "
            "could've held longer.")

    e2 = j.propose(thesis="Fade the rip in choppy tape.", conviction=0.35,
                   regime="chop", strategy="pullback_buy", side="buy", symbol="SPY",
                   quantity=1, entry_style="market",
                   kill_criteria="Tape trends instead of chopping for 2 sessions.",
                   exit_plan={"target": 696.0, "stop": 692.5, "time_stop": "2026-07-08"})
    j.approve(e2.id); j.mark_executed(e2.id, fill_price=695.0, filled_qty=1)
    j.close(e2.id, exit_price=692.0, reflection="Low conviction in chop — should "
            "have stood aside.")

    print(json.dumps(j.summarize(), indent=2))
