import unittest
from concurrent.futures import Future, TimeoutError as FutureTimeout
from unittest.mock import patch

import mcp_server
from trade_analyst import _make_judgment, start_trade_review


class TradeAnalystTests(unittest.TestCase):
    def test_momentum_gate_failure_is_a_doubt_not_a_stale_buy(self):
        review = _make_judgment(
            {"ticker": "AAPL", "side": "buy"},
            {
                "momentum": {"trade_allowed": False, "trend": "BEARISH", "rsi": 37},
                "sentiment": {"overall": {"blended_score": 0.62}},
                "final_decision": None,
                "final_decision_fresh": False,
            },
            {"strategies": []},
        )
        self.assertEqual(review["label"], "doubt")
        self.assertEqual(review["engine_signal"], "NO_TRADE_MOMENTUM_GATE")
        self.assertTrue(any("momentum gate" in reason.lower() for reason in review["doubts"]))

    def test_buy_supported_by_engine_and_backtest_can_be_confident(self):
        review = _make_judgment(
            {"ticker": "AAPL", "side": "buy"},
            {
                "momentum": {"trade_allowed": True, "trend": "BULLISH"},
                "sentiment": {"overall": {"blended_score": 0.7}},
                "final_decision": {"decision": "BUY SMALL"},
                "final_decision_fresh": True,
            },
            {"strategies": [{"strategy": "trend_follow", "n": 30,
                              "expectancy_per_trade": 1.2, "win_rate": 0.6}]},
        )
        self.assertEqual(review["label"], "confident")

    def test_slow_engine_returns_review_id_and_wait_choice(self):
        class SlowFuture:
            def result(self, timeout=None):
                raise FutureTimeout()

        from risk_gate import RiskConfig

        with patch("risk_gate.load_risk_config", return_value=RiskConfig(symbol_whitelist=("AAPL",))), \
                patch("trade_analyst._all_reviews", return_value={}), \
                patch("trade_analyst._save_review"), \
                patch("trade_analyst._executor.submit", return_value=SlowFuture()):
            result = start_trade_review("AAPL", "buy", 0.01, wait_seconds=120)
        self.assertEqual(result["status"], "running")
        self.assertTrue(result["review_id"].startswith("rev_"))
        self.assertIn("wait", result["message"].lower())

    def test_fractional_limit_request_is_rejected(self):
        from risk_gate import RiskConfig

        with patch("risk_gate.load_risk_config", return_value=RiskConfig(symbol_whitelist=("AAPL",))):
            result = start_trade_review("AAPL", "buy", 0.02, "limit", 100.0)
        self.assertIn("fractional-share limit", result["error"])

    def test_recent_identical_review_is_reused(self):
        from datetime import datetime, timezone
        from risk_gate import RiskConfig

        request = {"ticker": "AAPL", "side": "buy", "quantity": 0.01,
                   "entry_style": "market", "limit_price": None}
        cached = {"review_id": "rev_cached", "status": "complete", "request": request,
                  "created_at": datetime.now(timezone.utc).isoformat(),
                  "judgment": {"label": "confident"}}
        with patch("risk_gate.load_risk_config", return_value=RiskConfig(symbol_whitelist=("AAPL",))), \
                patch("trade_analyst._all_reviews", return_value={"rev_cached": cached}), \
                patch("trade_analyst._executor.submit") as submit:
            result = start_trade_review("AAPL", "buy", 0.01)
        self.assertEqual(result["review_id"], "rev_cached")
        self.assertTrue(result["cache_hit"])
        submit.assert_not_called()

    def test_execution_requires_confirmation_before_any_broker_call(self):
        result = mcp_server.execute_confirmed_trade("rev_missing", confirm=False)
        self.assertFalse(result["order_submitted"])
        self.assertIn("confirm=true", result["error"])

    def test_running_analysis_cannot_execute_without_proceed_override(self):
        running = {"review_id": "rev_running", "status": "running",
                   "request": {"ticker": "AAPL", "side": "buy", "quantity": 0.01,
                               "entry_style": "market", "limit_price": None}}
        with patch("trade_analyst.get_trade_review", return_value=running):
            result = mcp_server.execute_confirmed_trade("rev_running", confirm=True)
        self.assertFalse(result["order_submitted"])
        self.assertIn("still running", result["error"])

    def test_doubt_requires_separate_acknowledgement(self):
        doubtful = {"review_id": "rev_doubt", "status": "complete",
                    "request": {"ticker": "AAPL", "side": "buy", "quantity": 0.01,
                                "entry_style": "market", "limit_price": None},
                    "judgment": {"label": "doubt", "doubts": ["Momentum failed"]}}
        with patch("trade_analyst.get_trade_review", return_value=doubtful):
            result = mcp_server.execute_confirmed_trade("rev_doubt", confirm=True)
        self.assertFalse(result["order_submitted"])
        self.assertIn("acknowledge_doubts=true", result["error"])

    def test_explicit_slow_analysis_override_is_allowed_to_reach_next_gate(self):
        running = {"review_id": "rev_slow", "status": "running",
                   "request": {"ticker": "AAPL", "side": "buy", "quantity": 0.01,
                               "entry_style": "market", "limit_price": None}}
        with patch("trade_analyst.get_trade_review", return_value=running), \
                patch("execution.ACCOUNT", "test-account"), \
                patch("execution.LIVE_EXECUTION", False), \
                patch("risk_gate.load_risk_config") as load_cfg, \
                patch("mcp_server._review_exit_plan", return_value={"target": 110, "stop": 90, "time_stop": "2026-11-10"}), \
                patch("execution.J.propose") as propose, \
                patch("trade_analyst._save_review"):
            from risk_gate import RiskConfig
            load_cfg.return_value = RiskConfig(symbol_whitelist=("AAPL",))
            from journal import JournalEntry
            propose.return_value = JournalEntry(
                id="je_test", created_at="now", status="proposed", thesis="test",
                conviction=0.5, regime="test", strategy="trend_follow", side="buy",
                symbol="AAPL", quantity=0.01, entry_style="market", limit_price=None,
            )
            result = mcp_server.execute_confirmed_trade(
                "rev_slow", confirm=True, proceed_without_analysis=True,
            )
        self.assertEqual(result["status"], "recorded_sim_proposal")
        self.assertFalse(result["order_submitted"])
        self.assertNotIn("still running", result.get("error", ""))

    def test_analysis_worker_preserves_execution_written_while_running(self):
        import trade_analyst

        original = {"review_id": "rev_race", "status": "running",
                    "request": {"ticker": "AAPL", "side": "buy"}}
        current = {**original, "execution": {"status": "submitting", "attempted": True}}
        writes = []

        def fake_get(_review_id):
            return dict(current)

        def fake_save(value):
            writes.append(dict(value))
            current.update(value)

        engine = {"ticker": "AAPL", "momentum": {"trade_allowed": False},
                  "sentiment": {}, "final_decision": None,
                  "final_decision_fresh": False}
        with patch.object(trade_analyst, "_all_reviews", return_value={"rev_race": original}), \
                patch.object(trade_analyst, "_run_engine", return_value=engine), \
                patch.object(trade_analyst, "_backtest", return_value={"strategies": []}), \
                patch.object(trade_analyst, "_get_review", side_effect=fake_get), \
                patch.object(trade_analyst, "_save_review", side_effect=fake_save):
            trade_analyst._perform_review("rev_race")
        self.assertEqual(writes[-1]["execution"]["status"], "submitting")

    def test_sell_without_broker_owned_shares_is_rejected_before_proposal(self):
        review = {"review_id": "rev_sell", "status": "complete",
                  "request": {"ticker": "AAPL", "side": "sell", "quantity": 0.1,
                              "entry_style": "market", "limit_price": None},
                  "judgment": {"label": "doubt", "doubts": ["long only"]}}
        with patch("trade_analyst.get_trade_review", return_value=review), \
                patch("execution.ACCOUNT", "test-account"), \
                patch("execution.LIVE_EXECUTION", False), \
                patch("risk_gate.load_risk_config") as load_cfg, \
                patch("lab.mcp_call_tool", return_value='{"data":{"positions":[]}}'), \
                patch("execution.J.propose") as propose:
            from risk_gate import RiskConfig
            load_cfg.return_value = RiskConfig(symbol_whitelist=("AAPL",))
            result = mcp_server.execute_confirmed_trade(
                "rev_sell", confirm=True, acknowledge_doubts=True,
            )
        self.assertFalse(result["order_submitted"])
        self.assertIn("Shorting is disabled", result["error"])
        propose.assert_not_called()


if __name__ == "__main__":
    unittest.main()
