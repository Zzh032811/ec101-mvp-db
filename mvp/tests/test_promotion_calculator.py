import sqlite3
import unittest
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from mvp.scripts.promotion_calculator import calculate_activity


DDL = Path(__file__).resolve().parents[1] / "ddl" / "ec101_mvp_sqlite.sql"


class PromotionCalculatorTests(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.executescript(DDL.read_text(encoding="utf-8"))
        self.connection.execute("INSERT INTO dealer_platform(dealer_name, platform_name) VALUES ('经销商', '平台')")
        self.dp_id = self.connection.execute("SELECT dealer_platform_id FROM dealer_platform").fetchone()[0]
        self.connection.execute("INSERT INTO customer(dealer_platform_id, platform_customer_no, customer_name) VALUES (?, 'C-1', '客户')", (self.dp_id,))
        self.customer_id = self.connection.execute("SELECT customer_id FROM customer").fetchone()[0]

    def tearDown(self):
        self.connection.close()

    def _activity(self, name, category, promotion_type, threshold, reduce_amount, gift_qty=None, tpm=True):
        tpm_id = None
        if tpm:
            self.connection.execute("INSERT INTO tpm_application(tpm_code, apply_amount, budget_reserve_no, fee_pay_dept) VALUES (?, 100, 'R-1', '市场部')", (f'TPM-{name}',))
            tpm_id = self.connection.execute("SELECT last_insert_rowid()").fetchone()[0]
        self.connection.execute(
            "INSERT INTO activity(dealer_platform_id,tpm_id,activity_name,activity_category,promotion_type,start_time,end_time,rule_version) VALUES (?,?,?,?,?,?,?,?)",
            (self.dp_id, tpm_id, name, category, promotion_type, '2026-10-01 00:00:00', '2026-10-31 23:59:59', 'v1'),
        )
        activity_id = self.connection.execute("SELECT last_insert_rowid()").fetchone()[0]
        self.connection.execute("INSERT INTO activity_rule(activity_id,tier_no,threshold_type,threshold_value,reduce_amount) VALUES (?,?,?,?,?)", (activity_id, 1, '金额', threshold, reduce_amount))
        rule_id = self.connection.execute("SELECT last_insert_rowid()").fetchone()[0]
        if gift_qty is not None:
            self.connection.execute("INSERT INTO activity_rule_benefit(rule_id,benefit_type,gift_qty) VALUES (?, '赠品', ?)", (rule_id, gift_qty))
        return activity_id, rule_id

    def _order_activity(self, activity_id, rule_id, amount, actual=0, gift_actual=None, completed=True, at='2026-10-02 10:00:00'):
        self.connection.execute("INSERT INTO order_header(dealer_platform_id,order_no,order_time,customer_id,order_status) VALUES (?,?,?,?,?)", (self.dp_id, f'O-{activity_id}-{amount}-{gift_actual}', at, self.customer_id, '已完成' if completed else '待完成'))
        order_id = self.connection.execute("SELECT last_insert_rowid()").fetchone()[0]
        self.connection.execute("INSERT INTO fulfillment(order_id,order_status,completed_at) VALUES (?,?,?)", (order_id, '已完成' if completed else '待完成', at if completed else None))
        self.connection.execute("INSERT INTO order_activity(order_id,activity_id,rule_id,activity_product_amount,platform_actual_benefit,gift_qty_actual) VALUES (?,?,?,?,?,?)", (order_id, activity_id, rule_id, amount, actual, gift_actual))
        return order_id

    def test_calculate_activity_dispatches_discount_template_from_activity_configuration(self):
        activity_id, rule_id = self._activity('满减', '非券类', '满一定金额立减', 100, 10)
        self._order_activity(activity_id, rule_id, 100, actual=10)
        summary = calculate_activity(self.connection, activity_id, calc_batch_id=1, calc_date='2026-10-04')
        self.assertEqual(summary.template, 'discount')
        self.assertEqual(summary.theoretical_benefit, Decimal('10.00'))

    def test_gift_keeps_quantity_and_never_creates_a_currency_settlement(self):
        activity_id, rule_id = self._activity('满赠', '非券类', '立赠', 100, 0, gift_qty=2, tpm=False)
        self._order_activity(activity_id, rule_id, 100, gift_actual=2)
        summary = calculate_activity(self.connection, activity_id, calc_batch_id=2, calc_date='2026-10-04')
        fee = self.connection.execute("SELECT settle_amount, gift_cost_total FROM result_fee WHERE activity_id=?", (activity_id,)).fetchone()
        self.assertEqual(summary.template, 'gift')
        self.assertEqual(summary.gift_qty_entitled, Decimal('2'))
        self.assertEqual(fee, (None, None))

    def test_coupon_only_generates_fee_for_used_eligible_coupon(self):
        activity_id, rule_id = self._activity('券', '券类', '优惠券', 100, 10)
        self.connection.execute("INSERT INTO coupon_issue_rule(activity_id,issue_mode,issue_start_at,auto_issue_at,coupon_qty_per_grant,rule_status) VALUES (?, 'auto_grant', '2026-10-02 09:00:00', '2026-10-02 09:00:00', 1, '已结束')", (activity_id,))
        self.connection.execute("INSERT INTO coupon_use_rule(activity_id,coupon_type,validity_mode,use_start_at,use_end_at,max_use_per_coupon,rule_status) VALUES (?, '单品', 'fixed_period', '2026-10-02 00:00:00', '2026-10-10 00:00:00', 1, '已结束')", (activity_id,))
        order_id = self._order_activity(activity_id, rule_id, 100, actual=10)
        self.connection.execute("INSERT INTO coupon_ledger(dealer_platform_id,activity_id,coupon_no,customer_id,receive_time,coupon_status,use_time,use_order_no,discount_amount) VALUES (?, ?, 'C-001', ?, '2026-10-02 10:00:00', '已使用', '2026-10-02 11:00:00', ?, 10)", (self.dp_id, activity_id, self.customer_id, f'O-{activity_id}-100-None'))
        summary = calculate_activity(self.connection, activity_id, calc_batch_id=3, calc_date='2026-10-04')
        self.assertEqual(summary.template, 'coupon')
        self.assertEqual(summary.theoretical_benefit, Decimal('10.00'))
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM result_fee WHERE activity_id=?", (activity_id,)).fetchone()[0], 1)

    def test_ineligible_or_unreleased_orders_are_not_settlement_candidates(self):
        activity_id, rule_id = self._activity('边界', '非券类', '满一定金额立减', 100, 10)
        self._order_activity(activity_id, rule_id, 99, actual=0)
        self._order_activity(activity_id, rule_id, 100, actual=10, completed=False)
        summary = calculate_activity(self.connection, activity_id, calc_batch_id=4, calc_date='2026-10-04')
        self.assertEqual(summary.release_candidates, 0)
        self.assertEqual(summary.settle_amount, Decimal('0.00'))


if __name__ == '__main__':
    unittest.main()
