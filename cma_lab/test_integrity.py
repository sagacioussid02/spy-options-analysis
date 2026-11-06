import tempfile
import unittest
from pathlib import Path

import integrity
from journal import TradeJournal


def _closed(j, sym, fill, exit_, mode="sim"):
    e = j.propose(thesis="t", conviction=0.5, regime="r", strategy="s", side="buy",
                  symbol=sym, quantity=1, entry_style="market", kill_criteria="k",
                  exit_plan={"target": fill * 1.02, "stop": fill * 0.98, "time_stop": "2026-12-01"},
                  mode=mode)
    j.open_sim(e.id, fill_price=fill, filled_qty=1)
    j.close(e.id, exit_price=exit_)
    return e.id


class IntegrityTests(unittest.TestCase):
    def setUp(self):
        self.j = TradeJournal(Path(tempfile.mkstemp(suffix=".json")[1]))

    def test_price_problem(self):
        self.assertIsNotNone(integrity.price_problem(77.05, 285.0))
        self.assertIsNone(integrity.price_problem(284.0, 285.0))

    def test_sim_limit_fill(self):
        self.assertEqual(integrity.sim_limit_fill(290, 285), 285)      # marketable -> quote
        self.assertEqual(integrity.sim_limit_fill(284, 285), 284)      # within touch
        self.assertIsNone(integrity.sim_limit_fill(270, 285))          # would not fill

    def test_audit_excludes_bad_trade_and_keeps_good(self):
        good = _closed(self.j, "SPXL", 285.0, 288.0)
        _closed(self.j, "SPXL", 284.0, 286.0)
        bad = _closed(self.j, "SPXL", 77.05, 289.82)
        flagged = integrity.audit(self.j)
        self.assertEqual([f["id"] for f in flagged], [bad])
        self.assertTrue(self.j.get(bad)["excluded"])
        self.assertFalse(self.j.get(good).get("excluded"))
        self.assertEqual(self.j.summarize()["closed_trades"], 2)
        self.assertEqual(integrity.audit(self.j), [])                   # idempotent

    def test_flagged_trade_is_not_a_peer_for_later_ones(self):
        _closed(self.j, "SPXL", 77.05, 289.82)          # bad, earliest
        ok = _closed(self.j, "SPXL", 285.9, 283.7)      # fine, later
        _closed(self.j, "SPXL", 284.0, 285.0)
        _closed(self.j, "SPXL", 286.0, 287.0)
        flagged = {f["id"] for f in integrity.audit(self.j)}
        self.assertNotIn(ok, flagged)
        self.assertEqual(len(flagged), 1)

    def test_bad_entry_on_open_trade_is_voided(self):
        _closed(self.j, "SPY", 750.0, 752.0)
        _closed(self.j, "SPY", 751.0, 753.0)
        _closed(self.j, "SPY", 749.0, 750.0)
        e = self.j.propose(thesis="t", conviction=0.5, regime="r", strategy="s", side="buy",
                           symbol="SPY", quantity=1, entry_style="limit", limit_price=343.0,
                           kill_criteria="k", exit_plan={"target": 350, "stop": 340,
                           "time_stop": "2026-12-01"}, mode="sim")
        self.j.open_sim(e.id, fill_price=343.0, filled_qty=1)
        integrity.audit(self.j)
        self.assertEqual(self.j.get(e.id)["status"], "voided")
        self.assertEqual(self.j.open_positions(), [])


if __name__ == "__main__":
    unittest.main()
