"""Tests for Sutra buy/sell (sutra_trading.py and its place in sutra_api.py).

Mocks only: the desk's execute_confirmed_trade, the trade review lookup and
lab._mcp_call are all replaced. No test reaches Robinhood, places, previews or
simulates an order, or touches SPY_LIVE.

Run from the cma_lab/ dir:  ../.venv/bin/python -m unittest test_sutra_trading
"""
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

import lab
import mcp_server
import sutra_api
import sutra_trading

TOKEN = "desk-test-token"
PORT = 8790
AUTH = {sutra_api.TOKEN_HEADER: TOKEN}
CAPS = {
    sutra_trading.ENABLE_ENV: "1",
    sutra_trading.MAX_ORDER_ENV: "1000",
    sutra_trading.MAX_DAILY_ENV: "1500",
}


def review(quantity=2, limit_price=300.0, side="buy", ticker="SPY"):
    return {"review_id": "rev_1", "status": "complete",
            "request": {"ticker": ticker, "side": side, "quantity": quantity,
                        "entry_style": "limit" if limit_price else "market",
                        "limit_price": limit_price}}


class TradingTestCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.ledger = Path(tmp.name) / "sutra_orders.json"
        patches = [mock.patch.object(sutra_trading, "LEDGER_PATH", self.ledger)]

        self.env = dict(CAPS)
        patches.append(mock.patch("lab.lab_env", lambda key, default=None: self.env.get(key, default)))

        self.review = review()
        patches.append(mock.patch("trade_analyst.get_trade_review", lambda rid: dict(self.review)))

        self.executed = []

        def fake_execute(review_id, confirm, acknowledge_doubts=False, proceed_without_analysis=False):
            self.executed.append({"review_id": review_id, "confirm": confirm,
                                  "acknowledge_doubts": acknowledge_doubts,
                                  "proceed_without_analysis": proceed_without_analysis})
            return self.execute_result

        self.execute_result = {"status": "submitted", "order_submitted": True}
        self.execute = mock.patch.object(mcp_server, "execute_confirmed_trade", side_effect=fake_execute)
        patches.append(self.execute)

        self._real_mcp_call = lab._mcp_call
        self.addCleanup(setattr, lab, "_mcp_call", self._real_mcp_call)
        self.broker_calls = []

        async def recorder(name, arguments):
            self.broker_calls.append(name)
            return "{}"

        lab._mcp_call = recorder
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        sutra_api.install_broker_guard()

    def ledger_entries(self):
        return json.loads(self.ledger.read_text()) if self.ledger.exists() else []

    def client(self, trading=True):
        return TestClient(sutra_api.build_app(TOKEN, port=PORT, trading=trading),
                          base_url=f"http://127.0.0.1:{PORT}")


class ManifestTests(TradingTestCase):
    def test_order_tool_is_off_by_default(self):
        self.env = {}
        client = TestClient(sutra_api.build_app(TOKEN, port=PORT), base_url=f"http://127.0.0.1:{PORT}")
        names = {t["name"] for t in client.get("/.well-known/sutra-agent.json").json()["tools"]}
        self.assertNotIn("place_desk_order", names)
        self.assertEqual(client.post("/api/place_desk_order", headers=AUTH,
                                     json={"review_id": "rev_1"}).status_code, 404)

    def test_order_tool_listed_when_enabled_as_confirm_first(self):
        tools = {t["name"]: t for t in self.client().get("/.well-known/sutra-agent.json").json()["tools"]}
        tool = tools["place_desk_order"]
        self.assertEqual(tool["tier_hint"], "confirm-first")
        self.assertEqual(tool["method"], "POST")
        self.assertEqual({a["name"]: a["type"] for a in tool["args"]},
                         {"review_id": "string", "acknowledge_doubts": "boolean",
                          "proceed_without_analysis": "boolean"})
        for name in sutra_api.NEVER_LISTED:
            self.assertNotIn(name, tools)

    def test_manifest_never_mentions_live_switch(self):
        text = self.client().get("/.well-known/sutra-agent.json").text
        self.assertNotIn("SPY_LIVE", text)
        self.assertNotIn("SPY_SIM_ONLY", text)


class CapTests(TradingTestCase):
    def test_refuses_when_trading_is_off_at_call_time(self):
        self.env.pop(sutra_trading.ENABLE_ENV)
        result = sutra_trading.place_desk_order("rev_1")
        self.assertFalse(result["order_submitted"])
        self.assertEqual(self.executed, [])

    def test_refuses_without_dollar_caps(self):
        for missing in (sutra_trading.MAX_ORDER_ENV, sutra_trading.MAX_DAILY_ENV):
            env = dict(CAPS)
            env.pop(missing)
            self.env = env
            result = sutra_trading.place_desk_order("rev_1")
            self.assertFalse(result["order_submitted"])
            self.assertIn(missing, result["error"])
        self.assertEqual(self.executed, [])
        self.assertEqual(self.ledger_entries(), [])

    def test_bad_cap_values_count_as_unset(self):
        self.env[sutra_trading.MAX_ORDER_ENV] = "-5"
        self.assertFalse(sutra_trading.place_desk_order("rev_1")["order_submitted"])
        self.env[sutra_trading.MAX_ORDER_ENV] = "lots"
        self.assertFalse(sutra_trading.place_desk_order("rev_1")["order_submitted"])
        self.assertEqual(self.executed, [])

    def test_per_order_cap(self):
        self.review = review(quantity=4, limit_price=300.0)  # $1,200 > $1,000
        result = sutra_trading.place_desk_order("rev_1")
        self.assertIn("per-order cap", result["error"])
        self.assertEqual(self.executed, [])

    def test_daily_dollar_cap(self):
        self.ledger.write_text(json.dumps([{"day": sutra_trading._today(), "review_id": "rev_0",
                                            "notional_usd": 1000, "counts": True}]))
        result = sutra_trading.place_desk_order("rev_1")  # 1000 + 600 > 1500
        self.assertIn("daily cap", result["error"])
        self.assertEqual(self.executed, [])

    def test_uncounted_and_old_entries_do_not_use_the_cap(self):
        self.ledger.write_text(json.dumps([
            {"day": sutra_trading._today(), "review_id": "rev_a", "notional_usd": 1400, "counts": False},
            {"day": "2000-01-03", "review_id": "rev_b", "notional_usd": 1400, "counts": True},
        ]))
        self.assertTrue(sutra_trading.place_desk_order("rev_1")["order_submitted"])

    def test_daily_order_count(self):
        self.env[sutra_trading.MAX_ORDERS_ENV] = "1"
        self.ledger.write_text(json.dumps([{"day": sutra_trading._today(), "review_id": "rev_0",
                                            "notional_usd": 1, "counts": True}]))
        result = sutra_trading.place_desk_order("rev_1")
        self.assertIn("order limit", result["error"])
        self.assertEqual(self.executed, [])

    def test_market_order_without_a_quote_is_refused(self):
        self.review = review(limit_price=None)
        with mock.patch("execution._live_price", return_value=None):
            result = sutra_trading.place_desk_order("rev_1")
        self.assertFalse(result["order_submitted"])
        self.assertEqual(self.executed, [])

    def test_market_order_uses_a_quote_for_the_cap(self):
        self.review = review(quantity=2, limit_price=None)
        with mock.patch("execution._live_price", return_value=600.0):  # $1,200
            result = sutra_trading.place_desk_order("rev_1")
        self.assertIn("per-order cap", result["error"])

    def test_unknown_review_is_refused(self):
        with mock.patch("trade_analyst.get_trade_review", return_value={"error": "Unknown review_id."}):
            result = sutra_trading.place_desk_order("rev_x")
        self.assertFalse(result["order_submitted"])
        self.assertEqual(self.executed, [])


class OrderTests(TradingTestCase):
    def test_submits_through_the_desk_path_with_confirm(self):
        result = sutra_trading.place_desk_order("rev_1", acknowledge_doubts=True)
        self.assertEqual(self.executed, [{"review_id": "rev_1", "confirm": True,
                                          "acknowledge_doubts": True, "proceed_without_analysis": False}])
        self.assertTrue(result["order_submitted"])
        self.assertEqual(result["sutra_caps"]["order_usd"], 600.0)
        [entry] = self.ledger_entries()
        self.assertTrue(entry["counts"])
        self.assertEqual(entry["status"], "submitted")
        self.assertEqual(entry["notional_usd"], 600.0)

    def test_ledger_is_written_before_the_broker_is_called(self):
        seen = []

        def check_ledger(*args, **kwargs):
            seen.extend(self.ledger_entries())
            return {"status": "submitted", "order_submitted": True}

        self.execute.stop()
        with mock.patch.object(mcp_server, "execute_confirmed_trade", side_effect=check_ledger):
            sutra_trading.place_desk_order("rev_1")
        self.execute.start()
        self.assertEqual(seen[0]["status"], "submitting")

    def test_not_submitted_is_released_from_the_caps(self):
        self.execute_result = {"status": "recorded_sim_proposal", "order_submitted": False}
        result = sutra_trading.place_desk_order("rev_1")
        self.assertFalse(result["order_submitted"])
        [entry] = self.ledger_entries()
        self.assertFalse(entry["counts"])
        self.assertEqual(entry["status"], "recorded_sim_proposal")

    def test_ambiguous_submission_keeps_counting(self):
        self.execute_result = {"status": "reconciliation_required", "order_submitted": True}
        sutra_trading.place_desk_order("rev_1")
        [entry] = self.ledger_entries()
        self.assertTrue(entry["counts"])

    def test_crash_keeps_counting_and_reports_type_only(self):
        self.execute.stop()
        with mock.patch.object(mcp_server, "execute_confirmed_trade", side_effect=RuntimeError("acct 123")):
            res = self.client().post("/api/place_desk_order", headers=AUTH, json={"review_id": "rev_1"})
        self.execute.start()
        self.assertEqual(res.status_code, 500)
        self.assertNotIn("acct 123", res.text)
        [entry] = self.ledger_entries()
        self.assertTrue(entry["counts"])
        self.assertEqual(entry["status"], "error")

    def test_http_call_needs_token_and_json(self):
        client = self.client()
        self.assertEqual(client.post("/api/place_desk_order", json={"review_id": "rev_1"}).status_code, 401)
        self.assertEqual(client.post("/api/place_desk_order", headers=AUTH, content="review_id=rev_1").status_code, 415)
        self.assertEqual(self.executed, [])

    def test_http_booleans(self):
        client = self.client()
        res = client.post("/api/place_desk_order", headers=AUTH,
                          json={"review_id": "rev_1", "proceed_without_analysis": True})
        self.assertEqual(res.status_code, 200)
        self.assertTrue(self.executed[0]["proceed_without_analysis"])
        res = client.post("/api/place_desk_order", headers=AUTH,
                          json={"review_id": "rev_1", "acknowledge_doubts": "maybe"})
        self.assertEqual(res.status_code, 400)

    def test_never_touches_live_switch(self):
        before = {k: os.environ.get(k) for k in ("SPY_LIVE", "SPY_SIM_ONLY")}
        sutra_trading.place_desk_order("rev_1")
        self.assertEqual({k: os.environ.get(k) for k in before}, before)
        with open(sutra_trading.__file__, encoding="utf-8") as fh:
            source = fh.read()
        self.assertNotIn('environ["SPY_LIVE"]', source)
        self.assertNotIn("environ.setdefault", source)


class OrderWindowTests(TradingTestCase):
    """The guard lets order calls reach the (mocked) broker only inside place_desk_order."""

    def test_order_calls_blocked_outside_the_window(self):
        for name in sutra_trading.ORDER_TOOLS:
            with self.assertRaises(sutra_api.BrokerWriteBlocked):
                lab.mcp_call_tool(name, {})
        self.assertEqual(self.broker_calls, [])

    def test_order_calls_pass_inside_the_window_only(self):
        def desk_path(*args, **kwargs):
            lab.mcp_call_tool("review_equity_order", {})
            lab.mcp_call_tool("place_equity_order", {})
            with self.assertRaises(sutra_api.BrokerWriteBlocked):
                lab.mcp_call_tool("cancel_equity_order", {})
            return {"status": "submitted", "order_submitted": True}

        self.execute.stop()
        with mock.patch.object(mcp_server, "execute_confirmed_trade", side_effect=desk_path):
            sutra_trading.place_desk_order("rev_1")
        self.execute.start()
        self.assertEqual(self.broker_calls, ["review_equity_order", "place_equity_order"])
        with self.assertRaises(sutra_api.BrokerWriteBlocked):
            lab.mcp_call_tool("place_equity_order", {})

    def test_other_threads_stay_blocked_during_the_window(self):
        outcome = {}

        def other_thread():
            try:
                lab.mcp_call_tool("place_equity_order", {})
                outcome["result"] = "passed"
            except sutra_api.BrokerWriteBlocked:
                outcome["result"] = "blocked"

        def desk_path(*args, **kwargs):
            t = threading.Thread(target=other_thread)
            t.start()
            t.join()
            return {"status": "submitted", "order_submitted": True}

        self.execute.stop()
        with mock.patch.object(mcp_server, "execute_confirmed_trade", side_effect=desk_path):
            sutra_trading.place_desk_order("rev_1")
        self.execute.start()
        self.assertEqual(outcome["result"], "blocked")
        self.assertEqual(self.broker_calls, [])


class HealthTests(TradingTestCase):
    def test_health_reports_trading_state(self):
        body = self.client().get("/api/health").json()
        self.assertEqual(body["sutra_trading"], {"enabled": True, "caps_set": True})

    def test_trading_on_without_caps_is_degraded(self):
        self.env = {sutra_trading.ENABLE_ENV: "1", "ROBINHOOD_ACCESS_TOKEN": "at"}
        body = self.client().get("/api/health").json()
        self.assertEqual(body["status"], "degraded")
        self.assertIn("Sutra trading is on but its dollar caps are not set", body["problems"])


if __name__ == "__main__":
    unittest.main()
