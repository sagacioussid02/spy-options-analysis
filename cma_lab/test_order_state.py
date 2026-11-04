import json
import unittest

from order_state import average_price, classify, filled_quantity, match_record


class OrderStateTests(unittest.TestCase):
    def setUp(self):
        self.order = {
            "id": "order-1",
            "ref_id": "ref-1",
            "state": "filled",
            "average_price": "12.50",
            "cumulative_quantity": "2.0",
        }

    def test_matches_by_order_id_and_ref_id(self):
        payload = json.dumps({"data": {"orders": [self.order]}})
        self.assertEqual(match_record(payload, order_id="order-1"), self.order)
        self.assertEqual(match_record(payload, ref_id="ref-1"), self.order)

    def test_partial_fill_is_not_a_complete_fill(self):
        order = {**self.order, "state": "partially_filled"}
        self.assertEqual(classify(order), "partially_filled")
        self.assertEqual(filled_quantity(order), 2.0)
        self.assertEqual(average_price(order), 12.5)

    def test_pending_and_terminal_states(self):
        self.assertEqual(classify({"state": "confirmed"}), "submitted")
        self.assertEqual(classify({"state": "cancelled"}), "rejected")
        self.assertEqual(classify({"state": "future_state"}), "reconciliation_required")

    def test_ambiguous_multiple_orders_do_not_guess(self):
        self.assertIsNone(match_record({"data": {"orders": [self.order, self.order]}}))


if __name__ == "__main__":
    unittest.main()