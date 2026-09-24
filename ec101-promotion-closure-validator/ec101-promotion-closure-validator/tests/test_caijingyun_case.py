import json
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "cases" / "财经云-勤进" / "案例配置.json"
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.validate_caijingyun_case import analyze_case


class CaijingyunCaseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = analyze_case(CONFIG_PATH)

    def test_reduction_covers_business_supplied_start_date(self):
        summary = self.result["activities"]["满减"]
        self.assertEqual(summary["source_end_date"], "2026-09-08")
        self.assertGreater(summary["activity_period_record_count"], 0)
        self.assertEqual(summary["activity_period"], "自2026-08-26起（结束时间未提供）")
        self.assertEqual(summary["conclusion"], "未验证")

    def test_reduction_configuration_is_not_provided(self):
        summary = self.result["activities"]["满减"]
        self.assertIsNone(summary["config_evidence"])
        self.assertEqual(summary["config_source"], "未提供")

    def test_gift_bundle_and_pillow_observations_are_preserved(self):
        summary = self.result["activities"]["满赠"]
        self.assertEqual(summary["source_period"], "2026-08-21 至 2026-08-25")
        self.assertEqual(summary["observed_bundle_order_count"], 99)
        self.assertEqual(summary["issued_order_count"], 97)
        self.assertEqual(summary["issued_gift_quantity"], 97)
        self.assertEqual(summary["not_issued_order_count"], 2)
        self.assertEqual(summary["ordinary_pillow_sale_count"], 1)
        self.assertEqual(summary["conclusion"], "未验证")

    def test_gift_configuration_is_not_provided(self):
        summary = self.result["activities"]["满赠"]
        self.assertIsNone(summary["config_evidence"])
        self.assertEqual(summary["config_source"], "未提供")

    def test_gift_details_expose_the_two_missing_gifts(self):
        details = self.result["activities"]["满赠"]["details"]
        missing = {row["销售单号"] for row in details if row["实际赠品数量"] == 0}
        self.assertEqual(missing, {"SK2026082300040", "SK2026082200025"})
        self.assertTrue(all(row["雪碧套装金额"] == 105.5 for row in details))

    def test_overall_result_is_not_overstated(self):
        self.assertEqual(self.result["overall_conclusion"], "未验证")
        q001 = next(issue for issue in self.result["issues"] if issue["ID"] == "Q001")
        self.assertEqual(q001["分类"], "Gap")
        self.assertIn("2026-08-26", q001["问题"])

    def test_field_mapping_contains_all_finance_cloud_modules(self):
        mappings = self.result["field_mappings"]
        source_index = {(row["模块"], row["经销商原始字段"]): row for row in mappings}
        standard_index = {(row["模块"], row["EC101标准字段"]): row for row in mappings}

        self.assertIn(("客户资料", "手机/账号"), source_index)
        self.assertIn(("商品资料", "合作产品-商品名称"), source_index)
        self.assertIn(("销售明细", "销售-差价金额"), source_index)
        self.assertIn(("订单明细", "促销活动"), source_index)
        self.assertIn("销售出库(按单号)", source_index[("销售明细", "开单日期")]["来源文件"])
        self.assertIn("销售出库明细", source_index[("订单明细", "货品名称")]["来源文件"])
        self.assertEqual(standard_index[("订单明细", "订单状态")]["状态"], "Gap")
        self.assertEqual(standard_index[("活动配置", "活动编号")]["状态"], "Gap")
        self.assertEqual(standard_index[("活动配置", "活动名称")]["状态"], "Gap")
        self.assertEqual(standard_index[("活动配置", "活动商品范围值")]["状态"], "Gap")

    def test_gift_orders_match_the_separate_sales_detail_source(self):
        summary = self.result["activities"]["满赠"]
        self.assertEqual(summary["sales_matched_order_count"], 99)
        self.assertTrue(all(row["销售明细匹配"] for row in summary["details"]))

    def test_activity_configuration_gap_is_narrowed_to_structured_export(self):
        issue_text = "\n".join(issue["问题"] for issue in self.result["issues"])
        self.assertIn("满减活动配置暂未提供", issue_text)
        self.assertIn("满赠活动配置暂未提供", issue_text)

    def test_report_contract_is_data_driven(self):
        report = self.result["report"]
        self.assertEqual(len(report["capability_rows"]), 3)
        self.assertEqual(len(report["validation_summary_rows"]), 2)
        self.assertEqual({sheet["name"] for sheet in report["detail_sheets"]}, {"活动配置", "满减数据覆盖", "满赠逐单"})
        self.assertGreaterEqual(len(report["gap_rows"]), 6)


if __name__ == "__main__":
    unittest.main()
