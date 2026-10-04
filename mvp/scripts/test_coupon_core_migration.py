# -*- coding: utf-8 -*-
import sqlite3
import unittest
from pathlib import Path

from mvp.scripts.migrate_coupon_core import load_coupon_activities, migrate_schema


class CouponCoreMigrationTest(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.executescript(
            """
            CREATE TABLE dealer_platform (
              dealer_platform_id INTEGER PRIMARY KEY,
              dealer_name TEXT NOT NULL,
              platform_name TEXT NOT NULL
            );
            INSERT INTO dealer_platform VALUES (1, '深圳市兴路强商贸有限公司', '快马');
            CREATE TABLE customer (
              customer_id INTEGER PRIMARY KEY AUTOINCREMENT,
              dealer_platform_id INTEGER NOT NULL REFERENCES dealer_platform(dealer_platform_id),
              platform_customer_no TEXT NOT NULL,
              customer_name TEXT NOT NULL,
              customer_type TEXT,
              UNIQUE(dealer_platform_id, platform_customer_no)
            );
            CREATE TABLE coupon_ledger (
              coupon_id INTEGER PRIMARY KEY AUTOINCREMENT,
              dealer_platform_id INTEGER NOT NULL REFERENCES dealer_platform(dealer_platform_id),
              coupon_no TEXT NOT NULL,
              coupon_name TEXT,
              customer_id INTEGER REFERENCES customer(customer_id),
              receive_time TEXT,
              use_period TEXT,
              coupon_status TEXT,
              UNIQUE(dealer_platform_id, coupon_no)
            );
            CREATE TABLE activity (
              activity_id INTEGER PRIMARY KEY AUTOINCREMENT,
              dealer_platform_id INTEGER NOT NULL REFERENCES dealer_platform(dealer_platform_id),
              tpm_id INTEGER,
              activity_name TEXT NOT NULL,
              activity_category TEXT,
              promo_method TEXT,
              promotion_type TEXT,
              product_scope_type TEXT,
              disabled_product_scope_type TEXT,
              purchase_limit_type TEXT,
              purchase_limit_value NUMERIC,
              customer_scope_type TEXT,
              disabled_customer_scope_type TEXT,
              use_device TEXT,
              limit_recharge_gift TEXT,
              start_time TEXT NOT NULL,
              end_time TEXT NOT NULL,
              use_scene TEXT,
              allow_stack TEXT,
              allow_coupon TEXT,
              min_sku_count NUMERIC,
              activity_status TEXT,
              rule_version TEXT,
              UNIQUE(dealer_platform_id, activity_name)
            );
            CREATE TABLE activity_rule (
              rule_id INTEGER PRIMARY KEY AUTOINCREMENT,
              activity_id INTEGER NOT NULL REFERENCES activity(activity_id),
              tier_no INTEGER NOT NULL,
              threshold_type TEXT,
              threshold_value NUMERIC,
              reduce_amount NUMERIC,
              free_shipping INTEGER DEFAULT 0,
              UNIQUE(activity_id, tier_no)
            );
            CREATE TABLE activity_scope (
              scope_id INTEGER PRIMARY KEY AUTOINCREMENT,
              activity_id INTEGER NOT NULL REFERENCES activity(activity_id),
              scope_category TEXT NOT NULL,
              scope_dimension TEXT NOT NULL,
              scope_value TEXT NOT NULL
            );
            """
        )

    def tearDown(self):
        self.connection.close()

    def insert_activity(self, name, import_key):
        self.connection.execute(
            """
            INSERT INTO activity(
              dealer_platform_id, activity_name, start_time, end_time, activity_import_key
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (1, name, "2026-09-01 00:00:00", "2026-09-30 23:59:59", import_key),
        )

    def insert_legacy_activity(self, name):
        cursor = self.connection.execute(
            """
            INSERT INTO activity(dealer_platform_id, activity_name, start_time, end_time)
            VALUES (?, ?, ?, ?)
            """,
            (1, name, "2026-09-01 00:00:00", "2026-09-30 23:59:59"),
        )
        return cursor.lastrowid

    def query_activity(self, activity_id):
        return self.connection.execute(
            "SELECT * FROM activity WHERE activity_id=?", (activity_id,)
        ).fetchone()

    def rule_activity_ids(self):
        return [row[0] for row in self.connection.execute(
            "SELECT activity_id FROM activity_rule ORDER BY rule_id"
        )]

    def test_migrate_schema_allows_duplicate_activity_names_and_unique_non_null_import_keys(self):
        self.assertIsNone(migrate_schema(self.connection))

        self.insert_activity("同名活动", None)
        self.insert_activity("同名活动", None)
        self.insert_activity("券活动", "KM-COUPON-AUTO-001")
        with self.assertRaises(sqlite3.IntegrityError):
            self.insert_activity("另一名称", "KM-COUPON-AUTO-001")

    def test_migrate_schema_rebuilds_legacy_activity_without_losing_children(self):
        legacy_id = self.insert_legacy_activity("旧活动")
        self.connection.execute(
            """
            INSERT INTO activity_rule(activity_id, tier_no, threshold_type, threshold_value, reduce_amount)
            VALUES (?, ?, ?, ?, ?)
            """,
            (legacy_id, 1, "金额", 800, 10),
        )

        migrate_schema(self.connection)

        self.assertIsNone(self.query_activity(legacy_id)[23])
        self.assertEqual(self.rule_activity_ids(), [legacy_id])

    def test_load_coupon_activities_creates_rules_scopes_and_only_verified_ledger_link(self):
        self.connection.executemany(
            "INSERT INTO customer(dealer_platform_id, platform_customer_no, customer_name) VALUES (?, ?, ?)",
            [(1, "WX-00000000000007507893", "可口可乐客户测试"), (1, "WX-00000000000007507743", "快乐为民")],
        )
        self.connection.executemany(
            "INSERT INTO coupon_ledger(dealer_platform_id, coupon_no, coupon_name, customer_id, receive_time, use_period) VALUES (?, ?, ?, ?, ?, ?)",
            [(1, "202609091700313431", "test1", 1, "2026-09-09 17:00:31", "2026-09-09 16:50-2026-09-12 16:50"),
             (1, "UNVERIFIED-001", "test1", 2, "2026-09-09 17:00:31", "2026-09-09 16:50-2026-09-12 16:50")],
        )
        migrate_schema(self.connection)

        summary = load_coupon_activities(
            self.connection, Path("快马-兴路强-试点/优惠券")
        )

        self.assertEqual(summary["activities"], 2)
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM coupon_issue_rule").fetchone()[0], 2)
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM coupon_use_rule").fetchone()[0], 2)
        auto_id = self.connection.execute(
            "SELECT activity_id FROM activity WHERE activity_import_key='KM-COUPON-AUTO-001'"
        ).fetchone()[0]
        self.assertEqual(self.connection.execute(
            "SELECT activity_id FROM coupon_ledger WHERE coupon_no='202609091700313431'"
        ).fetchone()[0], auto_id)
        self.assertIsNone(self.connection.execute(
            "SELECT activity_id FROM coupon_ledger WHERE coupon_no='UNVERIFIED-001'"
        ).fetchone()[0])


if __name__ == "__main__":
    unittest.main()
