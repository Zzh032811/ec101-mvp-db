import sys
import json
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "cases" / "快马-顺英" / "案例配置.json"
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.validate_case import analyze_case
from scripts.source_readers import read_table


class RealCaseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = analyze_case(CONFIG_PATH)

    def test_full_reduction_control_total(self):
        summary = self.result["activities"]["满减"]
        self.assertEqual(summary["eligible_order_count"], 47)
        self.assertAlmostEqual(summary["actual_benefit_total"], 750.0, places=2)
        self.assertAlmostEqual(summary["theoretical_benefit_total"], 750.0, places=2)
        self.assertEqual(summary["activity_detail_matched_order_count"], 47)
        self.assertEqual(summary["sales_matched_order_count"], 47)
        self.assertEqual(summary["activity_order_count"], 54)
        self.assertEqual(summary["non_completed_activity_order_count"], 6)
        self.assertEqual(summary["unmatched_activity_order_ids"], ["10521577026091800113"])

    def test_full_gift_control_total(self):
        summary = self.result["activities"]["满赠"]
        self.assertEqual(summary["eligible_order_count"], 100)
        self.assertEqual(summary["issued_order_count"], 98)
        self.assertEqual(summary["issued_gift_quantity"], 98)
        self.assertEqual(summary["not_issued_order_count"], 2)

    def test_payment_risks_do_not_change_eligible_counts(self):
        reduction = self.result["activities"]["满减"]
        self.assertGreaterEqual(reduction["payment_risk_count"], 0)
        self.assertEqual(reduction["eligible_order_count"], 47)

    def test_reduction_policy_keeps_one_auditable_representative_text(self):
        policies = [row["活动政策"] for row in self.result["activities"]["满减"]["details"]]
        self.assertTrue(all(len(policy) <= 120 for policy in policies))

    def test_field_mapping_contains_every_source_column(self):
        config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        source_root = (CONFIG_PATH.parent / config["source_root"]).resolve()
        files_by_module = {
            "客户资料": ["User2026091613203383772.xls"],
            "商品资料": ["Product2026091613223281646.xls"],
            "订单明细": [
                config["activities"]["满减"]["order_file"],
                config["activities"]["满赠"]["order_file"],
            ],
            "销售明细": [
                config["activities"]["满减"]["sales_file"],
                config["activities"]["满赠"]["sales_file"],
            ],
            "活动执行": [
                config["activities"]["满减"]["activity_file"],
                config["activities"]["满赠"]["activity_file"],
            ],
        }
        actual = {
            (row["模块"], row["经销商原始字段"])
            for row in self.result["field_mappings"]
            if row["经销商原始字段"] != "—"
        }
        for module, file_names in files_by_module.items():
            expected_fields = set()
            for file_name in file_names:
                expected_fields.update(map(str, read_table(source_root / file_name).columns))
            self.assertTrue(
                {(module, field) for field in expected_fields}.issubset(actual),
                f"{module} 存在未展示原始字段",
            )

    def test_field_mapping_contains_non_v1_and_missing_v1_fields(self):
        mappings = self.result["field_mappings"]
        source_index = {(row["模块"], row["经销商原始字段"]): row for row in mappings}
        standard_index = {(row["模块"], row["EC101标准字段"]): row for row in mappings}
        self.assertEqual(source_index[("客户资料", "登录账号")]["字段关系"], "非V1字段")
        self.assertEqual(source_index[("商品资料", "副标题")]["字段关系"], "非V1字段")
        self.assertEqual(source_index[("销售明细", "毛利率(%)")]["字段关系"], "非V1字段")
        self.assertEqual(standard_index[("活动配置", "活动编号")]["状态"], "Gap")
        self.assertEqual(standard_index[("履约售后", "退款状态")]["状态"], "Gap")
        self.assertEqual(standard_index[("费用结果", "费用承担方")]["状态"], "Gap")


if __name__ == "__main__":
    unittest.main()
