"""
Computes the Desk Report digest — the same summary shown on the published
"Desk Report" artifact (https://claude.ai/artifact/HbN214FDTDqcu8WJC6p4oC).
The artifact's page reads live from its own db capability, not from the
Neon store directly (the artifact sandbox's CSP blocks fetch/XHR to any
host outside a small CDN allowlist, so the page cannot call store_proxy
itself). Refreshing the report is therefore two steps: run this script to
recompute the digest from the real store, then write its output to the
artifact's "reports/latest" document via the Artifact tool's write_db
action (db_op="set"), which replaces the whole document.

Output is a compact JSON digest, not raw collections — distilled so it
comfortably fits the artifact db's 256 KiB per-document cap.

Run:
    .venv/bin/python cma_lab/reporting/compute_report.py > /tmp/report.json
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

_CMA_LAB_DIR = Path(__file__).resolve().parent.parent
if str(_CMA_LAB_DIR) not in sys.path:
    sys.path.insert(0, str(_CMA_LAB_DIR))

import events  # noqa: E402
import sleeve  # noqa: E402
from committee import load_debates  # noqa: E402
from journal import TradeJournal  # noqa: E402
from playbook import Playbook  # noqa: E402
from store import store  # noqa: E402


def _parse(s):
    try:
        return datetime.fromisoformat(s)
    except Exception:  # noqa: BLE001
        return None


def compute_report() -> dict:
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)
    twoweek_ago = now - timedelta(days=14)

    J = TradeJournal()
    journal = J._load()

    opened_7d = [e for e in journal if (t := _parse(e.get("created_at") or "")) and t >= week_ago]
    closed_7d = [e for e in journal if (t := _parse(e.get("closed_at") or "")) and t >= week_ago]
    live_opened = sum(1 for e in opened_7d if e.get("mode") == "live")
    sim_opened = sum(1 for e in opened_7d if e.get("mode") == "sim")
    wins_7d = sum(1 for e in closed_7d if (e.get("pnl") or 0) > 0)

    debates = load_debates()
    debates_7d = [d for d in debates if (t := _parse(d.get("created_at") or "")) and t >= week_ago]
    by_decision: dict = defaultdict(int)
    by_ticker: dict = defaultdict(lambda: defaultdict(int))
    for d in debates_7d:
        dec = (d.get("pm_decision") or {}).get("decision", "unclear")
        by_decision[dec] += 1
        by_ticker[d.get("ticker", "?")][dec] += 1

    week = {
        "opened": len(opened_7d), "opened_live": live_opened, "opened_sim": sim_opened,
        "closed": len(closed_7d), "wins": wins_7d,
        "debates": len(debates_7d), "by_decision": dict(by_decision),
        "by_ticker": {k: dict(v) for k, v in by_ticker.items()},
    }

    sleeve_state = sleeve._load()
    sv = sleeve.sleeve_value()
    open_live = [e for e in journal if e.get("status") == "open" and e.get("mode") == "live"]
    open_notional = sum((e.get("fill_price") or 0) * (e.get("filled_qty") or 0) for e in open_live)

    all_events = events.recent(1000)
    events_14d = [e for e in all_events if (t := _parse(e.get("at") or "")) and t >= twoweek_ago]
    cap_blocks_14d = [e for e in events_14d if e.get("kind") == "cap_blocked"]
    topups_14d = [e for e in events_14d if e.get("kind") == "sleeve_topup"]

    funding = {
        "sleeve_value": round(sv, 2), "sleeve_base": sleeve_state.get("base"),
        "accrued_since_topup": sleeve_state.get("realized_pnl_since_topup"),
        "last_topup_at": sleeve_state.get("last_topup_at"),
        "open_live_notional": round(open_notional, 2),
        "open_live_positions": len(open_live),
        "cap_blocks_14d": len(cap_blocks_14d),
        "topups_14d": topups_14d,
    }

    alerts = sorted(events_14d, key=lambda e: e.get("at", ""), reverse=True)[:30]

    usage = store().load("usage_log", []) or []
    usage_7d = [u for u in usage if (t := _parse(u.get("at") or "")) and t >= week_ago]
    total_cost_7d = sum(u.get("cost", 0) for u in usage_7d)
    by_model: dict = defaultdict(lambda: {"n": 0, "cost": 0.0, "fresh_in": 0, "cache_read": 0, "output": 0})
    for u in usage_7d:
        b = by_model[u.get("model", "?")]
        b["n"] += 1
        b["cost"] += u.get("cost", 0)
        b["fresh_in"] += u.get("fresh_in", 0)
        b["cache_read"] += u.get("cache_read", 0)
        b["output"] += u.get("output", 0)
    by_label_prefix: dict = defaultdict(lambda: {"n": 0, "cost": 0.0})
    for u in usage_7d:
        label = u.get("label", "") or "unlabeled"
        prefix = label.split(":")[-1].rsplit("-", 1)[-1] if ":" in label else label
        b = by_label_prefix[prefix]
        b["n"] += 1
        b["cost"] += u.get("cost", 0)

    total_fresh = sum(u.get("fresh_in", 0) for u in usage_7d)
    total_cached = sum(u.get("cache_read", 0) for u in usage_7d)

    usage_summary = {
        "total_cost_7d": round(total_cost_7d, 4),
        "n_sessions_7d": len(usage_7d),
        "by_model": {k: {"n": v["n"], "cost": round(v["cost"], 4), "fresh_in": v["fresh_in"],
                         "cache_read": v["cache_read"], "output": v["output"]}
                    for k, v in by_model.items()},
        "by_role": {k: {"n": v["n"], "cost": round(v["cost"], 4)} for k, v in by_label_prefix.items()},
        "fresh_vs_cached_pct": (round(100 * total_cached / (total_fresh + total_cached), 1)
                                if (total_fresh + total_cached) else None),
        "all_time_rows": len(usage),
    }

    playbook = Playbook()._load()
    return {
        "generated_at": now.isoformat(),
        "week": week,
        "funding": funding,
        "alerts": alerts,
        "usage": usage_summary,
        "playbook_totals": {
            "trial": sum(1 for h in playbook if h["status"] == "trial"),
            "active": sum(1 for h in playbook if h["status"] == "active"),
            "retired": sum(1 for h in playbook if h["status"] == "retired"),
        },
    }


if __name__ == "__main__":
    print(json.dumps(compute_report(), indent=2, default=str))
