import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "cases" / "快马-兴路强" / "案例配置.json"
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.validate_kuaima_xingluqiang_case import analyze_case


class KuaimaXingluqiangCaseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = analyze_case(CONFIG_PATH)

    def test_reduction_uses_fixed_reduction_and_completed_gate(self):
        reduction = self.result["activities"]["满减"]
        self.assertEqual(reduction["eligible_order_count"], 133)
        self.assertEqual(reduction["theoretical_benefit_total"], 1995)
        self.assertEqual(reduction["actual_benefit_total"], 1995)
        self.assertEqual(reduction["sales_matched_order_count"], 133)
        self.assertEqual(reduction["payment_risk_count"], 10)

    def test_gift_uses_new_order_detail_for_completed_gate(self):
        gift = self.result["activities"]["满赠"]
        self.assertEqual(gift["observed_activity_order_count"], 98)
        self.assertEqual(gift["order_detail_matched_order_count"], 98)
        self.assertEqual(gift["missing_order_detail_count"], 0)
        self.assertEqual(gift["eligible_order_count"], 98)
        self.assertEqual(gift["observed_gift_quantity"], 98)
        self.assertEqual(gift["order_detail_gift_total"], 99)
        self.assertEqual(gift["non_activity_gift_quantity"], 1)
        self.assertEqual(gift["non_activity_gift_details"][0]["订单编号"], "1012420526026081900082")
        self.assertEqual(gift["non_activity_gift_details"][0]["异常类型"], "活动前非关联抱枕")
        self.assertIn("客户编号", gift["non_activity_gift_details"][0])
        self.assertIn("支付方式", gift["non_activity_gift_details"][0])
        self.assertEqual(gift["not_issued_order_count"], 0)
        self.assertEqual(gift["payment_risk_count"], 1)
        self.assertEqual(gift["conclusion"], "条件支持")

    def test_mapping_includes_all_source_fields_and_v1_gap(self):
        rows = self.result["field_mappings"]
        raw_index = {(row["模块"], row["经销商原始字段"]): row for row in rows}
        standard_index = {(row["模块"], row["EC101标准字段"]): row for row in rows}
        self.assertIn(("活动执行", "享受促销政策"), raw_index)
        self.assertIn(("订单明细", "支付状态"), raw_index)
        self.assertIn(("订单明细", "订单状态"), raw_index)
        self.assertEqual(standard_index[("活动配置", "活动编号")]["状态"], "Gap")


if __name__ == "__main__":
    unittest.main()
