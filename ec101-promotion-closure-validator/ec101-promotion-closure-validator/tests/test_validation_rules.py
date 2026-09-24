import sys
import unittest
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.validation_rules import eligible_order, full_reduction, payment_risk


class ValidationRulesTest(unittest.TestCase):
    def setUp(self):
        self.rule = {
            "start_at": datetime(2026, 9, 14, 20, 13),
            "end_at": datetime(2026, 9, 18, 20, 13),
            "required_order_status": "已完成",
        }

    def test_activity_start_is_inclusive(self):
        order = {"下单时间": datetime(2026, 9, 14, 20, 13), "订单状态": "已完成"}
        self.assertTrue(eligible_order(order, self.rule))

    def test_pre_activity_order_is_excluded(self):
        order = {"下单时间": datetime(2026, 9, 14, 20, 12, 59), "订单状态": "已完成"}
        self.assertFalse(eligible_order(order, self.rule))

    def test_non_completed_order_is_excluded(self):
        order = {"下单时间": datetime(2026, 9, 15, 8, 0), "订单状态": "待发货"}
        self.assertFalse(eligible_order(order, self.rule))

    def test_every_300_reduces_15(self):
        self.assertEqual(full_reduction(299.99, 300, 15), 0)
        self.assertEqual(full_reduction(300, 300, 15), 15)
        self.assertEqual(full_reduction(899.99, 300, 15), 30)
        self.assertEqual(full_reduction(900, 300, 15), 45)

    def test_completed_cod_order_with_unpaid_status_is_risk_not_exclusion(self):
        order = {
            "下单时间": datetime(2026, 9, 15, 8, 0),
            "订单状态": "已完成",
            "支付方式": "货到付款",
            "支付状态": "未支付",
        }
        self.assertTrue(eligible_order(order, self.rule))
        self.assertEqual(payment_risk(order), "已完成但未支付：线下实收无法确认")


if __name__ == "__main__":
    unittest.main()

