import unittest
from unittest.mock import patch
from urllib.error import URLError

from committee import _operator_report, _send_ntfy_notification
import graph_committee


class OperatorNotificationTests(unittest.TestCase):
    def test_pass_notification_is_structured_and_explicitly_not_placed(self):
        debate = {
            "ticker": "AAPL",
            "engine_snapshot": {
                "decision": "BUY SMALL",
                "final_score": 75,
                "confidence": "HIGH",
                "recommendation": {"explanation": ["momentum aligned"]},
            },
            "bull_case": {
                "stance": "bull",
                "confidence": 0.6,
                "thesis": "Trend may continue.",
                "key_evidence": ["above VWAP"],
                "suggested_trade": {"side": "buy", "symbol": "AAPL", "quantity": 0.02},
            },
            "bear_case": {
                "stance": "bear",
                "confidence": 0.7,
                "thesis": "Earnings risk is elevated.",
                "key_evidence": ["binary event"],
            },
            "pm_decision": {"decision": "pass", "reason": "Do not add before earnings."},
        }
        result = _operator_report(debate, None, None)
        payload = result["notification"]
        self.assertEqual(payload["event"], "spy_desk_signal")
        self.assertEqual(payload["engine"]["signal"], "BUY SMALL")
        self.assertEqual(payload["committee"]["decision"], "PASS")
        self.assertEqual(payload["trade"]["journal_status"], "not_placed")
        self.assertFalse(payload["trade"]["filled"])
        self.assertEqual(payload["agents"]["bear"]["stance"], "bear")
        self.assertIn("ORDER BUY 0.02 AAPL", result["notification_body"])
        self.assertIn("PASS", result["notification_body"])

    def test_mobile_notification_is_two_concise_lines(self):
        from committee import _mobile_notification_body

        body = _mobile_notification_body({
            "ticker": "AAPL",
            "engine": {"signal": "BUY SMALL", "score": 74, "confidence": "MEDIUM"},
            "committee": {"decision": "PASS", "reason": "Existing position and binary earnings risk."},
            "trade": {"side": "buy", "symbol": "AAPL", "quantity": 0.02,
                      "journal_status": "not_placed", "filled": False},
            "agents": {},
            "learnings": [],
        })
        self.assertEqual(len(body.splitlines()), 2)
        self.assertIn("Engine BUY SMALL", body)
        self.assertIn("Why:", body)

    def test_live_proposal_keeps_broker_state_separate(self):
        debate = {
            "ticker": "JPM",
            "engine_snapshot": {"decision": "BUY SMALL", "final_score": 80},
            "bull_case": {},
            "bear_case": {},
            "pm_decision": {"decision": "propose"},
        }
        journal_entry = {
            "side": "buy", "symbol": "JPM", "quantity": 0.1,
            "mode": "live", "status": "submitted", "broker_order_state": "queued",
            "thesis": "Momentum continuation.",
        }
        result = _operator_report(debate, journal_entry, None)
        trade = result["notification"]["trade"]
        self.assertEqual(trade["journal_status"], "submitted")
        self.assertEqual(trade["broker_status"], "queued")
        self.assertFalse(trade["filled"])

    def test_ntfy_disabled_without_topic(self):
        with patch("lab.lab_env", return_value=None):
            result = _send_ntfy_notification("AAPL: PASS", {"ticker": "AAPL"})
        self.assertEqual(result["status"], "disabled")

    def test_ntfy_posts_structured_summary_over_https(self):
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return b"{}"

        def fake_env(key, default=None):
            return {
                "SPY_NTFY_TOPIC": "private_topic_123",
                "SPY_NTFY_SERVER": "https://push.example.test",
                "SPY_NTFY_TOKEN": "test-token",
            }.get(key, default)

        with patch("lab.lab_env", side_effect=fake_env), \
                patch("urllib.request.urlopen", return_value=FakeResponse()) as urlopen:
            result = _send_ntfy_notification("AAPL: PASS", {
                "ticker": "AAPL",
                "engine": {"signal": "BUY SMALL", "score": 75, "confidence": "HIGH"},
                "committee": {"decision": "PASS", "reason": "Risk too high."},
                "trade": {"side": "buy", "symbol": "AAPL", "quantity": 0.02,
                          "mode": None, "journal_status": "not_placed", "filled": False},
                "agents": {},
            })
        self.assertEqual(result["status"], "sent")
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "https://push.example.test/private_topic_123")
        self.assertEqual(request.get_header("Authorization"), "Bearer test-token")
        self.assertIn(b"PM PASS", request.data)
        self.assertIn(b"filled=False", request.data)
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 8)

    def test_ntfy_rejects_non_https_server_without_request(self):
        def fake_env(key, default=None):
            return {"SPY_NTFY_TOPIC": "topic_123", "SPY_NTFY_SERVER": "http://push.example.test"}.get(key, default)

        with patch("lab.lab_env", side_effect=fake_env), \
                patch("urllib.request.urlopen") as urlopen:
            result = _send_ntfy_notification("AAPL: PASS", {"ticker": "AAPL"})
        self.assertEqual(result["status"], "error")
        urlopen.assert_not_called()

    def test_graph_committee_persists_and_sends_notification(self):
        report = {
            "text": "SIGNAL REPORT — AAPL",
            "notification": {"event": "spy_desk_signal", "ticker": "AAPL"},
            "notification_title": "AAPL: PASS",
            "notification_body": "ENGINE BUY SMALL | PM PASS",
        }
        saved = []
        with patch.object(graph_committee.J, "_load", return_value=[]), \
                patch.object(graph_committee, "ShadowStore") as shadow_store, \
                patch.object(graph_committee, "_operator_report", return_value=report), \
                patch.object(graph_committee, "_notify_operator", return_value={"ntfy": {"status": "sent"}}) as notify, \
                patch.object(graph_committee, "save_debate", side_effect=lambda debate: saved.append(dict(debate))):
            shadow_store.return_value._load.return_value = []
            graph_committee.record_debate({
                "debate_id": "deb_test",
                "context": {"engine_snapshot": {}},
                "pm_decision": {"decision": "pass"},
                "bull_case": {},
                "bear_case": {},
            })

        notify.assert_called_once_with("AAPL: PASS", "ENGINE BUY SMALL | PM PASS", report["notification"])
        self.assertEqual(saved[-1]["notification_delivery"]["ntfy"]["status"], "sent")


if __name__ == "__main__":
    unittest.main()
