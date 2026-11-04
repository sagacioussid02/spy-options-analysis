import unittest

import mcp_server


class McpServerTests(unittest.TestCase):
    def test_server_name_and_tool_catalog(self):
        self.assertEqual(mcp_server.mcp.name, "spy-desk")
        names = {tool.name for tool in mcp_server.mcp._tool_manager.list_tools()}
        self.assertEqual(names, {
            "get_engine_signal",
            "get_recent_debates",
            "get_journal_summary",
            "get_recent_trades",
            "get_open_positions",
            "get_unreconciled_orders",
            "get_broker_account",
            "get_broker_positions",
            "get_broker_orders",
            "get_ticker_trade_status",
            "get_risk_settings",
            "analyze_trade_request",
            "wait_for_trade_analysis",
            "get_trade_analysis_details",
            "get_trading_analyst_status",
            "execute_confirmed_trade",
            "get_lessons",
            "run_engine",
            "create_trade_proposal",
            "reject_trade_proposal",
            "preview_sweep",
            "run_paper_sweep",
        })
        self.assertNotIn("place_equity_order", names)
        self.assertNotIn("run_live_sweep", names)

    def test_paper_sweep_requires_explicit_confirmation(self):
        result = mcp_server.run_paper_sweep(confirm=False)
        self.assertIn("error", result)
        self.assertIn("No state changed", result["error"])


if __name__ == "__main__":
    unittest.main()