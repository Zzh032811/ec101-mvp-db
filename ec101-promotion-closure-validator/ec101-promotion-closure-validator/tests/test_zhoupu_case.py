import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "cases" / "舟谱-羿柏" / "案例配置.json"
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.validate_zhoupu_case import analyze_case


class ZhoupuCaseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = analyze_case(CONFIG_PATH)

    def test_coupon_rule_and_activity_data_are_preserved(self):
        coupon = self.result["activities"]["满减"]
        self.assertEqual(coupon["activity_type"], "下单返券")
        self.assertEqual(coupon["threshold"], 288)
        self.assertEqual(coupon["coupon_face_value"], 15)
        self.assertEqual(coupon["issued_coupon_count"], 114)
        self.assertEqual(coupon["used_coupon_count"], 51)
        self.assertEqual(coupon["linked_usage_order_count"], 51)
        self.assertEqual(coupon["auxiliary_eligibility"]["qualified_coupon_count"], 51)

    def test_coupon_order_coverage_is_not_overstated(self):
        coupon = self.result["activities"]["满减"]
        self.assertEqual(coupon["order_source_start"], "2026-08-26")
        self.assertEqual(coupon["order_source_end"], "2026-09-08")
        self.assertEqual(coupon["eligible_order_count"], 119)
        self.assertEqual(coupon["conclusion"], "条件支持")

    def test_gift_recalculation_applies_exact_activity_time_and_customer_limit(self):
        gift = self.result["activities"]["满赠"]
        self.assertEqual(gift["eligible_order_count"], 85)
        self.assertEqual(gift["issued_order_count"], 81)
        self.assertEqual(gift["observed_gift_quantity"], 82)
        self.assertEqual(gift["not_issued_order_count"], 4)
        self.assertEqual(len(gift["exception_details"]), 5)
        self.assertEqual(sum(row["异常类型"] == "未赠" for row in gift["exception_details"]), 4)
        self.assertEqual(sum(row["异常类型"] == "异常赠送" for row in gift["exception_details"]), 1)
        self.assertEqual(gift["conclusion"], "条件支持")

    def test_mapping_keeps_source_field_union_and_v1_union(self):
        rows = self.result["field_mappings"]
        index = {(row["模块"], row["经销商原始字段"]): row for row in rows}
        v1_index = {(row["模块"], row["EC101标准字段"]): row for row in rows}
        self.assertIn(("活动执行", "已领取数量"), index)
        self.assertIn(("订单明细", "支付流水号"), index)
        self.assertIn(("活动配置", "赠品商品编号"), v1_index)


if __name__ == "__main__":
    unittest.main()
