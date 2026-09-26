import unittest
from pathlib import Path

from api.server import SUPPORTED_OBJECTS, get_detail, query_dataset


DB_PATH = Path(__file__).resolve().parents[2] / "mvp" / "ec101_mvp.db"


class ReadonlyBusinessDataApiTests(unittest.TestCase):
    def test_exposes_eight_business_objects(self):
        self.assertEqual(
            set(SUPPORTED_OBJECTS),
            {
                "orders",
                "order-lines",
                "activities",
                "activity-details",
                "customers",
                "products",
                "fulfillments",
                "order-activities",
            },
        )

    def test_orders_support_filter_and_pagination(self):
        result = query_dataset(
            DB_PATH,
            "orders",
            {"dealer": "兴路强", "platform": "快马", "q": "", "limit": 2, "offset": 0},
        )
        self.assertEqual(result["total"], 2925)
        self.assertEqual(len(result["rows"]), 2)
        self.assertEqual(result["rows"][0]["dealer"], "深圳市兴路强商贸有限公司")

    def test_unknown_object_is_rejected(self):
        with self.assertRaises(KeyError):
            query_dataset(DB_PATH, "drop-table", {"limit": 10, "offset": 0})

    def test_detail_returns_real_order(self):
        result = get_detail(DB_PATH, "orders", "1")
        self.assertIsNotNone(result)
        self.assertIn("order_no", result)
        self.assertIn("dealer", result)


if __name__ == "__main__":
    unittest.main()
