import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = PROJECT_ROOT.parent
SOURCE_ROOT = WORKSPACE_ROOT / "第二阶段验证" / "快马-顺英"
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.source_readers import detect_table_format, read_table


class SourceReadersTest(unittest.TestCase):
    def test_detects_three_xls_storage_formats(self):
        self.assertEqual(
            detect_table_format(SOURCE_ROOT / "满减活动明细20260914_20260916132107.xls"),
            "html",
        )
        self.assertEqual(
            detect_table_format(SOURCE_ROOT / "满减订单明细20260914-2026091613272066347.xls"),
            "biff",
        )
        self.assertEqual(
            detect_table_format(SOURCE_ROOT / "满减销售明细20260914-20260916132549.xls"),
            "ooxml",
        )

    def test_reads_expected_headers_from_each_format(self):
        activity = read_table(SOURCE_ROOT / "满减活动明细20260914_20260916132107.xls")
        orders = read_table(SOURCE_ROOT / "满减订单明细20260914-2026091613272066347.xls")
        sales = read_table(SOURCE_ROOT / "满减销售明细20260914-20260916132549.xls")
        self.assertIn("订单号", activity.columns)
        self.assertIn("订单状态", orders.columns)
        self.assertIn("单据编号", sales.columns)


if __name__ == "__main__":
    unittest.main()

