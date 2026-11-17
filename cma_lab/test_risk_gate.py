import unittest
from unittest.mock import patch

from risk_gate import RiskConfig, evaluate


class NotionalCapTests(unittest.TestCase):
    """Issue #4: the $1,500/order notional cap must apply to market orders.

    A market order carries no limit price, so call sites now attach a live
    reference quote as "price" before evaluating; with no usable price at
    all, the gate fails closed instead of skipping the cap.
    """

    CFG = RiskConfig(symbol_whitelist=("SPY",))

    def test_market_order_over_cap_is_denied(self):
        # The issue's scenario: 5 SPY at the Nov 13 close ($754.37) is
        # ~$3,772 — about 2.5x the cap — and must not slip through just
        # because the order is a market order.
        d = evaluate("place_equity_order",
                     {"symbol": "SPY", "side": "buy", "type": "market",
                      "quantity": 5, "price": 754.37}, self.CFG)
        self.assertFalse(d.allowed)
        self.assertTrue(any("notional" in r for r in d.reasons))

    def test_market_order_under_cap_passes(self):
        d = evaluate("place_equity_order",
                     {"symbol": "SPY", "side": "buy", "type": "market",
                      "quantity": 2, "price": 400.0}, self.CFG)
        self.assertTrue(d.allowed)

    def test_market_order_without_price_is_denied_fail_closed(self):
        d = evaluate("place_equity_order",
                     {"symbol": "SPY", "side": "buy", "type": "market",
                      "quantity": 1}, self.CFG)
        self.assertFalse(d.allowed)
        self.assertTrue(any("notional cap cannot be verified" in r
                            for r in d.reasons))

    def test_limit_order_cap_behavior_unchanged(self):
        over = evaluate("place_equity_order",
                        {"symbol": "SPY", "side": "buy", "type": "limit",
                         "quantity": 5, "price": 754.37}, self.CFG)
        self.assertFalse(over.allowed)
        under = evaluate("place_equity_order",
                         {"symbol": "SPY", "side": "buy", "type": "limit",
                          "quantity": 2, "price": 400.0}, self.CFG)
        self.assertTrue(under.allowed)


class GateAndAffordMarketOrderTests(unittest.TestCase):
    """execution._gate_and_afford prices market orders off a live quote."""

    def _entry(self, quantity, limit_price=None):
        return {"id": "t_test", "symbol": "SPY", "side": "buy",
                "entry_style": "limit" if limit_price else "market",
                "quantity": quantity, "limit_price": limit_price,
                "snapshot_price": None, "human_notes": ""}

    def test_market_order_over_cap_blocked_by_gate(self):
        import execution
        with patch("execution._live_price", return_value=754.37), \
                patch("execution.load_risk_config",
                      return_value=RiskConfig(symbol_whitelist=("SPY",))):
            reason, _px = execution._gate_and_afford(self._entry(5))
        self.assertIsNotNone(reason)
        self.assertIn("risk gate", reason)

    def test_market_order_without_quote_blocked_fail_closed(self):
        import execution
        with patch("execution._live_price", return_value=None), \
                patch("execution.load_risk_config",
                      return_value=RiskConfig(symbol_whitelist=("SPY",))):
            reason, _px = execution._gate_and_afford(self._entry(1))
        self.assertIsNotNone(reason)
        self.assertIn("notional cap cannot be verified", reason)

    def test_market_order_under_cap_passes_gate_and_affordability(self):
        import execution
        with patch("execution._live_price", return_value=100.0), \
                patch("execution.load_risk_config",
                      return_value=RiskConfig(symbol_whitelist=("SPY",))), \
                patch("execution.ACCOUNT", "test-account"), \
                patch("execution.account_standing",
                      return_value={"buying_power": 100_000.0}):
            reason, px = execution._gate_and_afford(self._entry(2))
        self.assertIsNone(reason)
        self.assertEqual(px, 100.0)


class StartTradeReviewMarketOrderTests(unittest.TestCase):
    """trade_analyst.start_trade_review attaches a quote for market buys."""

    def test_market_buy_over_cap_fails_gate(self):
        from trade_analyst import start_trade_review
        with patch("risk_gate.load_risk_config",
                   return_value=RiskConfig(symbol_whitelist=("SPY",))), \
                patch("execution._live_price", return_value=754.37):
            result = start_trade_review("SPY", "buy", 5, "market")
        self.assertIn("fails the active risk gate", result["error"])

    def test_market_buy_without_quote_fails_closed(self):
        from trade_analyst import start_trade_review
        with patch("risk_gate.load_risk_config",
                   return_value=RiskConfig(symbol_whitelist=("SPY",))), \
                patch("execution._live_price", return_value=None):
            result = start_trade_review("SPY", "buy", 1, "market")
        self.assertIn("fails the active risk gate", result["error"])


if __name__ == "__main__":
    unittest.main()
