"""Tests for the Sutra adapter (sutra_api.py): auth and host checks, the
manifest's tool set, the broker guard, background runs and /api/health.

Nothing here reaches Robinhood, the engine or the network: tool functions are
replaced with stubs and lab._mcp_call with a recorder.

Run from the cma_lab/ dir:  ../.venv/bin/python -m unittest test_sutra_api
"""
import os
import time
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from fastapi.testclient import TestClient

import lab
import mcp_server
import sutra_api

TOKEN = "desk-test-token"
PORT = 8790
LOCAL = f"http://127.0.0.1:{PORT}"
AUTH = {sutra_api.TOKEN_HEADER: TOKEN}

READ_TOOLS = {
    "get_engine_signal", "get_recent_debates", "get_journal_summary", "get_recent_trades",
    "get_open_positions", "get_unreconciled_orders", "get_broker_account",
    "get_broker_positions", "get_broker_orders", "get_ticker_trade_status",
    "get_risk_settings", "get_lessons", "get_trade_analysis_details",
    "get_trading_analyst_status", "preview_sweep", "get_engine_run",
}
CONFIRM_FIRST = {"run_engine", "analyze_trade_request"}


class _Env:
    """A stand-in for lab.lab_env backed by a dict."""

    def __init__(self, values):
        self.values = values

    def __call__(self, key, default=None):
        return self.values.get(key, default)


class SutraApiTestCase(unittest.TestCase):
    def setUp(self):
        self._real_mcp_call = lab._mcp_call
        self.addCleanup(setattr, lab, "_mcp_call", self._real_mcp_call)
        self.broker_calls = []

        async def recorder(name, arguments):
            self.broker_calls.append(name)
            return "{}"

        lab._mcp_call = recorder
        self.runs = sutra_api.Runs()
        self.app = sutra_api.build_app(TOKEN, port=PORT, runs=self.runs)
        self.client = TestClient(self.app, base_url=LOCAL)


class ManifestTests(SutraApiTestCase):
    def test_manifest_is_open_and_lists_only_read_and_analysis_tools(self):
        res = self.client.get("/.well-known/sutra-agent.json")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["sutra_manifest_version"], 1)
        tools = {t["name"]: t for t in body["tools"]}
        self.assertEqual(set(tools), READ_TOOLS | CONFIRM_FIRST)
        for name in sutra_api.NEVER_LISTED:
            self.assertNotIn(name, tools)
        for name in READ_TOOLS:
            self.assertEqual(tools[name]["tier_hint"], "read-only")
            self.assertEqual(tools[name]["method"], "GET")
        for name in CONFIRM_FIRST:
            self.assertEqual(tools[name]["tier_hint"], "confirm-first")
            self.assertEqual(tools[name]["method"], "POST")
        for tool in tools.values():
            self.assertEqual(tool["path"], f"/api/{tool['name']}")
            self.assertTrue(tool["generic_callable"])
            for arg in tool["args"]:
                self.assertFalse(arg["secret"])
                self.assertEqual(arg["in"], "query" if tool["method"] == "GET" else "body")

    def test_manifest_never_mentions_live_trading_switch(self):
        text = self.client.get("/.well-known/sutra-agent.json").text
        self.assertNotIn("SPY_LIVE", text)
        self.assertNotIn("execute_confirmed_trade", text)
        self.assertNotIn("place_equity_order", text)

    def test_every_listed_path_is_routed(self):
        routed = {route.path for route in self.app.routes}
        for tool in self.client.get("/.well-known/sutra-agent.json").json()["tools"]:
            self.assertIn(tool["path"], routed)


class AuthTests(SutraApiTestCase):
    def test_tool_call_without_token_is_refused(self):
        with mock.patch.object(mcp_server, "get_engine_signal") as fn:
            res = self.client.get("/api/get_engine_signal")
        self.assertEqual(res.status_code, 401)
        fn.assert_not_called()

    def test_tool_call_with_wrong_token_is_refused(self):
        res = self.client.get("/api/get_engine_signal", headers={sutra_api.TOKEN_HEADER: "nope"})
        self.assertEqual(res.status_code, 401)

    def test_foreign_host_is_refused_even_with_token(self):
        res = self.client.get("/api/get_engine_signal", headers={**AUTH, "host": "evil.example:8790"})
        self.assertEqual(res.status_code, 403)
        res = self.client.get("/.well-known/sutra-agent.json", headers={"host": "evil.example"})
        self.assertEqual(res.status_code, 403)

    def test_post_requires_json(self):
        res = self.client.post("/api/run_engine", headers=AUTH, content="ticker=SPY")
        self.assertEqual(res.status_code, 415)

    def test_build_app_requires_token(self):
        with self.assertRaises(ValueError):
            sutra_api.build_app("")

    def test_read_tool_with_token_returns_result(self):
        with mock.patch.object(mcp_server, "get_recent_debates", return_value=[{"id": 1}]) as fn:
            res = self.client.get("/api/get_recent_debates", params={"limit": "3"}, headers=AUTH)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {"result": [{"id": 1}]})
        fn.assert_called_once_with(limit=3)

    def test_unknown_and_missing_args_are_400(self):
        res = self.client.get("/api/get_engine_signal", params={"x": "1"}, headers=AUTH)
        self.assertEqual(res.status_code, 400)
        res = self.client.get("/api/get_ticker_trade_status", headers=AUTH)
        self.assertEqual(res.status_code, 400)

    def test_tool_crash_reports_only_the_type(self):
        with mock.patch.object(mcp_server, "get_engine_signal", side_effect=RuntimeError("secret-ish detail")):
            res = self.client.get("/api/get_engine_signal", headers=AUTH)
        self.assertEqual(res.status_code, 500)
        self.assertNotIn("secret-ish", res.text)


class BrokerGuardTests(SutraApiTestCase):
    def test_order_tools_are_blocked_for_the_whole_process(self):
        for name in ("place_equity_order", "review_equity_order", "cancel_equity_order",
                     "add_to_watchlist", "create_watchlist"):
            with self.assertRaises(sutra_api.BrokerWriteBlocked):
                lab.mcp_call_tool(name, {})
        self.assertEqual(self.broker_calls, [])

    def test_read_tools_pass_through(self):
        for name in sorted(sutra_api.BROKER_READ_TOOLS):
            lab.mcp_call_tool(name, {})
        self.assertEqual(sorted(self.broker_calls), sorted(sutra_api.BROKER_READ_TOOLS))

    def test_guard_is_installed_once(self):
        guarded = lab._mcp_call
        sutra_api.install_broker_guard()
        self.assertIs(lab._mcp_call, guarded)

    def test_execution_path_cannot_place_an_order_through_the_adapter_process(self):
        # Even code the adapter never lists (execution, sweep) is stopped,
        # because they call lab.mcp_call_tool, which reads lab._mcp_call.
        from execution import mcp_call_tool as imported_by_name
        with self.assertRaises(sutra_api.BrokerWriteBlocked):
            imported_by_name("place_equity_order", {"symbol": "SPY"})
        self.assertEqual(self.broker_calls, [])

    def test_broker_reads_through_listed_tools_stay_on_the_allowlist(self):
        with mock.patch.object(mcp_server, "ACCOUNT", "acct", create=True), \
                mock.patch("lab.lab_env", _Env({"ROBINHOOD_ACCOUNT_NUMBER": "acct"})):
            for path in ("/api/get_broker_positions", "/api/get_broker_orders",
                         "/api/get_broker_account"):
                self.client.get(path, headers=AUTH)
        self.assertTrue(set(self.broker_calls) <= sutra_api.BROKER_READ_TOOLS)


class BackgroundRunTests(SutraApiTestCase):
    def _wait(self, run_id, timeout=5):
        deadline = time.time() + timeout
        while time.time() < deadline:
            run = self.client.get("/api/get_engine_run", params={"run_id": run_id}, headers=AUTH).json()["result"]
            if run["status"] != "running":
                return run
            time.sleep(0.02)
        self.fail("run did not finish")

    def _whitelist(self, *symbols):
        cfg = mock.Mock(symbol_whitelist=list(symbols))
        return mock.patch("risk_gate.load_risk_config", return_value=cfg)

    def test_run_engine_returns_at_once_and_finishes_in_background(self):
        started = time.time()

        def slow_engine(ticker):
            time.sleep(0.3)
            return {"ticker": ticker, "verdict": "hold"}

        with self._whitelist("SPY"), mock.patch.object(mcp_server, "run_engine", side_effect=slow_engine):
            res = self.client.post("/api/run_engine", json={"ticker": "spy"}, headers=AUTH)
            self.assertLess(time.time() - started, 0.25)
            self.assertEqual(res.status_code, 200)
            body = res.json()["result"]
            self.assertEqual(body["status"], "running")
            run = self._wait(body["run_id"])
        self.assertEqual(run["status"], "done")
        self.assertEqual(run["report"], {"ticker": "SPY", "verdict": "hold"})
        self.assertIn("finished_at", run)

    def test_engine_error_marks_run_failed(self):
        with self._whitelist("SPY"), mock.patch.object(
                mcp_server, "run_engine", return_value={"error": "engine exited 1"}):
            run_id = self.client.post("/api/run_engine", json={"ticker": "SPY"}, headers=AUTH).json()["result"]["run_id"]
            run = self._wait(run_id)
        self.assertEqual(run["status"], "failed")
        self.assertEqual(run["error"], "engine exited 1")

    def test_engine_crash_marks_run_failed_without_detail(self):
        with self._whitelist("SPY"), mock.patch.object(
                mcp_server, "run_engine", side_effect=OSError("/private/path")):
            run_id = self.client.post("/api/run_engine", json={"ticker": "SPY"}, headers=AUTH).json()["result"]["run_id"]
            run = self._wait(run_id)
        self.assertEqual(run["status"], "failed")
        self.assertNotIn("/private/path", run["error"])

    def test_ticker_outside_whitelist_is_refused_without_a_run(self):
        with self._whitelist("SPY"), mock.patch.object(mcp_server, "run_engine") as engine:
            body = self.client.post("/api/run_engine", json={"ticker": "TSLA"}, headers=AUTH).json()["result"]
        self.assertIn("error", body)
        self.assertNotIn("run_id", body)
        engine.assert_not_called()

    def test_unknown_run_id(self):
        body = self.client.get("/api/get_engine_run", params={"run_id": "run_x"}, headers=AUTH).json()["result"]
        self.assertIn("error", body)

    def test_analyze_trade_request_does_not_wait(self):
        captured = {}

        def fake(ticker, side, quantity, entry_style="market", limit_price=None, wait_seconds=120):
            captured["wait_seconds"] = wait_seconds
            return {"review_id": "rev_1", "status": "running", "message": "taking over two minutes"}

        with mock.patch.object(mcp_server, "analyze_trade_request", side_effect=fake):
            res = self.client.post("/api/analyze_trade_request", headers=AUTH,
                                   json={"ticker": "SPY", "side": "buy", "quantity": 1})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(captured["wait_seconds"], 0)
        body = res.json()["result"]
        self.assertEqual(body["review_id"], "rev_1")
        self.assertIn("get_trade_analysis_details", body["message"])

    def test_analyze_cache_hit_and_errors_pass_through(self):
        cached = {"review_id": "rev_2", "status": "complete", "cache_hit": True}
        with mock.patch.object(mcp_server, "analyze_trade_request", return_value=cached):
            body = self.client.post("/api/analyze_trade_request", headers=AUTH,
                                    json={"ticker": "SPY", "side": "buy", "quantity": 1}).json()["result"]
        self.assertEqual(body, cached)

    def test_quantity_must_be_a_number(self):
        res = self.client.post("/api/analyze_trade_request", headers=AUTH,
                               json={"ticker": "SPY", "side": "buy", "quantity": "lots"})
        self.assertEqual(res.status_code, 400)


class HealthTests(SutraApiTestCase):
    def _health(self, env):
        with mock.patch("lab.lab_env", _Env(env)):
            res = self.client.get("/api/health")
        self.assertEqual(res.status_code, 200)
        return res.json()

    def test_health_is_open_and_ok_with_a_refreshable_token(self):
        body = self._health({"ROBINHOOD_ACCESS_TOKEN": "at-secret", "ROBINHOOD_REFRESH_TOKEN": "rt-secret",
                             "ROBINHOOD_CLIENT_ID": "cid-secret",
                             "ROBINHOOD_TOKEN_EXPIRES_AT": "2000-01-01T00:00:00+00:00"})
        self.assertEqual(body["status"], "ok")
        self.assertTrue(body["broker"]["token_present"])
        self.assertTrue(body["broker"]["refresh_available"])
        self.assertFalse(body["live_trading_armed"])

    def test_health_holds_no_secret_values(self):
        with mock.patch("lab.lab_env", _Env({"ROBINHOOD_ACCESS_TOKEN": "at-secret",
                                             "ROBINHOOD_REFRESH_TOKEN": "rt-secret",
                                             "ROBINHOOD_CLIENT_ID": "cid-secret",
                                             "SPY_DESK_TOKEN": TOKEN})):
            text = self.client.get("/api/health").text
        for secret in ("at-secret", "rt-secret", "cid-secret", TOKEN):
            self.assertNotIn(secret, text)

    def test_missing_token_is_degraded(self):
        body = self._health({})
        self.assertEqual(body["status"], "degraded")
        self.assertIn("broker token missing", body["problems"])

    def test_expiring_token_without_refresh_is_degraded(self):
        soon = (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat()
        body = self._health({"ROBINHOOD_ACCESS_TOKEN": "at", "ROBINHOOD_TOKEN_EXPIRES_AT": soon})
        self.assertEqual(body["status"], "degraded")

    def test_expired_token_without_refresh_is_degraded(self):
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        body = self._health({"ROBINHOOD_ACCESS_TOKEN": "at", "ROBINHOOD_TOKEN_EXPIRES_AT": past})
        self.assertEqual(body["status"], "degraded")
        self.assertIn("broker token expired and cannot refresh", body["problems"])

    def test_live_armed_is_reported_not_changed(self):
        before = os.environ.get("SPY_LIVE")
        body = self._health({"ROBINHOOD_ACCESS_TOKEN": "at", "SPY_LIVE": "1"})
        self.assertTrue(body["live_trading_armed"])
        body = self._health({"ROBINHOOD_ACCESS_TOKEN": "at", "SPY_LIVE": "1", "SPY_SIM_ONLY": "1"})
        self.assertFalse(body["live_trading_armed"])
        self.assertEqual(os.environ.get("SPY_LIVE"), before)

    def test_unreadable_settings_are_degraded(self):
        def broken(key, default=None):
            raise ConnectionError("db down")

        with mock.patch("lab.lab_env", broken):
            body = self.client.get("/api/health").json()
        self.assertEqual(body["status"], "degraded")


class SourceTests(unittest.TestCase):
    def test_adapter_never_writes_spy_live(self):
        with open(sutra_api.__file__, encoding="utf-8") as fh:
            source = fh.read()
        self.assertNotIn('os.environ["SPY_LIVE"]', source)
        self.assertNotIn("environ.setdefault(\"SPY_LIVE\"", source)
        self.assertNotIn("import execution", source)
        self.assertNotIn("from execution", source)


if __name__ == "__main__":
    unittest.main()
