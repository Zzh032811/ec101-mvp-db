# -*- coding: utf-8 -*-
"""SQLite migration for the EC101 coupon CORE model."""
import sqlite3
import argparse
import shutil
from datetime import datetime
from pathlib import Path

try:
    from .readers import read_table
except ImportError:
    from readers import read_table

ACTIVITY_COLUMNS = (
    "activity_id, dealer_platform_id, tpm_id, activity_name, activity_category, "
    "promo_method, promotion_type, product_scope_type, disabled_product_scope_type, "
    "purchase_limit_type, purchase_limit_value, customer_scope_type, "
    "disabled_customer_scope_type, use_device, limit_recharge_gift, start_time, "
    "end_time, use_scene, allow_stack, allow_coupon, min_sku_count, activity_status, "
    "rule_version"
)

ACTIVITY_TABLE_SQL = """
CREATE TABLE activity__new (
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
  activity_import_key TEXT
)
"""


def _table_exists(connection, name):
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _columns(connection, table):
    return {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}


def _ensure_coupon_tables(connection):
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS coupon_issue_rule (
          coupon_issue_rule_id INTEGER PRIMARY KEY AUTOINCREMENT,
          activity_id INTEGER NOT NULL UNIQUE REFERENCES activity(activity_id),
          issue_mode TEXT NOT NULL CHECK(issue_mode IN ('auto_grant', 'manual_claim')),
          issue_start_at TEXT NOT NULL,
          issue_end_at TEXT,
          auto_issue_at TEXT,
          coupon_qty_per_grant NUMERIC NOT NULL,
          max_claim_per_customer NUMERIC,
          daily_claim_limit NUMERIC,
          rule_status TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS coupon_use_rule (
          coupon_use_rule_id INTEGER PRIMARY KEY AUTOINCREMENT,
          activity_id INTEGER NOT NULL UNIQUE REFERENCES activity(activity_id),
          coupon_type TEXT NOT NULL,
          validity_mode TEXT NOT NULL CHECK(validity_mode IN ('fixed_period', 'days_after_receive')),
          use_start_at TEXT,
          use_end_at TEXT,
          valid_days_after_receive INTEGER,
          max_use_per_coupon NUMERIC NOT NULL,
          rule_status TEXT NOT NULL
        );
        """
    )


def migrate_schema(connection):
    """Upgrade an EC101 database to the coupon CORE schema in place."""
    if not _table_exists(connection, "activity"):
        raise ValueError("activity table is required")

    foreign_keys = connection.execute("PRAGMA foreign_keys").fetchone()[0]
    if connection.in_transaction:
        connection.commit()
    connection.execute("PRAGMA foreign_keys = OFF")
    try:
        with connection:
            if "activity_import_key" not in _columns(connection, "activity"):
                connection.execute("DROP TABLE IF EXISTS activity__new")
                connection.execute(ACTIVITY_TABLE_SQL)
                connection.execute(
                    f"INSERT INTO activity__new ({ACTIVITY_COLUMNS}) "
                    f"SELECT {ACTIVITY_COLUMNS} FROM activity"
                )
                connection.execute("DROP TABLE activity")
                connection.execute("ALTER TABLE activity__new RENAME TO activity")
            connection.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_activity_import_key "
                "ON activity(activity_import_key) WHERE activity_import_key IS NOT NULL"
            )
            _ensure_coupon_tables(connection)
            if _table_exists(connection, "coupon_ledger"):
                if "activity_id" not in _columns(connection, "coupon_ledger"):
                    connection.execute(
                        "ALTER TABLE coupon_ledger ADD COLUMN activity_id "
                        "INTEGER REFERENCES activity(activity_id)"
                    )
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS idx_coupon_activity "
                    "ON coupon_ledger(activity_id)"
                )
            violations = connection.execute("PRAGMA foreign_key_check").fetchall()
            if violations:
                raise ValueError(f"foreign key violations after migration: {violations}")
    finally:
        connection.execute(f"PRAGMA foreign_keys = {int(bool(foreign_keys))}")


def _customer_numbers(source_path):
    _, _, headers, rows = read_table(str(source_path))
    index = {name: position for position, name in enumerate(headers)}
    customer_index = index["客户编号"]
    return [str(row[customer_index]).strip() for row in rows if row[customer_index]]


def _activity_id(connection, import_key, values):
    row = connection.execute(
        "SELECT activity_id FROM activity WHERE activity_import_key=?", (import_key,)
    ).fetchone()
    if row:
        connection.execute(
            "UPDATE activity SET activity_name=?, activity_category=?, promotion_type=?, "
            "start_time=?, end_time=?, activity_status=?, rule_version=? WHERE activity_id=?",
            (*values, row[0]),
        )
        return row[0]
    cursor = connection.execute(
        "INSERT INTO activity(dealer_platform_id, activity_name, activity_category, promotion_type, "
        "start_time, end_time, activity_status, rule_version, activity_import_key) "
        "VALUES(1, ?, ?, ?, ?, ?, ?, ?, ?)",
        (*values, import_key),
    )
    return cursor.lastrowid


def _replace_activity_details(connection, activity_id, issue, use, threshold, scopes):
    connection.execute("DELETE FROM coupon_issue_rule WHERE activity_id=?", (activity_id,))
    connection.execute("DELETE FROM coupon_use_rule WHERE activity_id=?", (activity_id,))
    connection.execute("DELETE FROM activity_scope WHERE activity_id=?", (activity_id,))
    connection.execute("DELETE FROM activity_rule WHERE activity_id=?", (activity_id,))
    rule_id = connection.execute(
        "INSERT INTO activity_rule(activity_id, tier_no, threshold_type, threshold_value, reduce_amount) "
        "VALUES (?, 1, '金额', ?, ?)", (activity_id, *threshold)
    ).lastrowid
    connection.execute(
        "INSERT INTO coupon_issue_rule(activity_id, issue_mode, issue_start_at, issue_end_at, auto_issue_at, "
        "coupon_qty_per_grant, max_claim_per_customer, daily_claim_limit, rule_status) VALUES(?,?,?,?,?,?,?,?,?)",
        (activity_id, *issue),
    )
    connection.execute(
        "INSERT INTO coupon_use_rule(activity_id, coupon_type, validity_mode, use_start_at, use_end_at, "
        "valid_days_after_receive, max_use_per_coupon, rule_status) VALUES(?,?,?,?,?,?,?,?)",
        (activity_id, *use),
    )
    connection.executemany(
        "INSERT INTO activity_scope(activity_id, scope_category, scope_dimension, scope_value) VALUES(?,?,?,?)",
        [(activity_id, *scope) for scope in scopes],
    )
    return rule_id


def load_coupon_activities(connection, source_dir):
    """Load the two source-backed coupon configurations idempotently."""
    source_dir = Path(source_dir)
    manual_customers = _customer_numbers(source_dir / "新客户投放优惠券指定客户列表.xlsx")
    auto_customers = _customer_numbers(source_dir / "test1优惠券指定客户列表.xlsx")
    for customer_no in manual_customers + auto_customers:
        if not connection.execute(
            "SELECT 1 FROM customer WHERE dealer_platform_id=1 AND platform_customer_no=?", (customer_no,)
        ).fetchone():
            raise ValueError(f"specified coupon customer not found: {customer_no}")

    with connection:
        manual_id = _activity_id(connection, "KM-COUPON-MANUAL-001", (
            "新客户投放", "券类", "满一定金额立减", "2026-08-31 16:04:00",
            "2026-09-15 23:59:00", "已结束", "coupon-v1",
        ))
        _replace_activity_details(connection, manual_id,
            ("manual_claim", "2026-08-31 16:10:00", "2026-08-31 23:59:00", None, 2, 2, None, "已结束"),
            ("多品组合优惠", "fixed_period", "2026-08-31 16:04:00", "2026-09-15 23:59:00", None, 1, "已结束"),
            (800, 10),
            [("发放对象", "客户编号", number) for number in manual_customers] + [
                ("适用商品", "商品范围", "全部商品"), ("支付方式", "支付方式", "在线支付")])

        auto_id = _activity_id(connection, "KM-COUPON-AUTO-001", (
            "test1", "券类", "满一定金额立减", "2026-09-09 16:50:00",
            "2026-09-12 16:50:00", "已结束", "coupon-v1",
        ))
        _replace_activity_details(connection, auto_id,
            ("auto_grant", "2026-09-09 16:55:00", None, "2026-09-09 16:55:00", 1, None, None, "已结束"),
            ("单品优惠", "fixed_period", "2026-09-09 16:50:00", "2026-09-12 16:50:00", None, 1, "已结束"),
            (588, 200),
            [("发放对象", "客户编号", number) for number in auto_customers] + [
                ("适用商品", "品牌", "可口可乐"), ("使用场景", "下单场景", "客户自下单"),
                ("使用场景", "下单场景", "代下单")])
        connection.execute(
            "UPDATE coupon_ledger SET activity_id=? WHERE dealer_platform_id=1 "
            "AND coupon_no='202609091700313431' AND coupon_name='test1' "
            "AND customer_id=(SELECT customer_id FROM customer WHERE dealer_platform_id=1 "
            "AND platform_customer_no='WX-00000000000007507893') "
            "AND receive_time='2026-09-09 17:00:31' "
            "AND use_period='2026-09-09 16:50-2026-09-12 16:50'",
            (auto_id,),
        )
    return {"activities": 2, "manual_activity_id": manual_id, "auto_activity_id": auto_id}


def run(db_path, source_dir):
    db_path = Path(db_path)
    backup_path = db_path.with_suffix(db_path.suffix + "." + datetime.now().strftime("%Y%m%d%H%M%S") + ".bak")
    shutil.copy2(db_path, backup_path)
    connection = sqlite3.connect(db_path, timeout=30)
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        migrate_schema(connection)
        summary = load_coupon_activities(connection, source_dir)
        summary["backup"] = str(backup_path)
        summary["foreign_key_violations"] = len(connection.execute("PRAGMA foreign_key_check").fetchall())
        return summary
    finally:
        connection.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--source-dir", required=True)
    args = parser.parse_args()
    print(run(args.db, args.source_dir))
