# -*- coding: utf-8 -*-
"""EC101 MVP 定向修正 — 为客户主数据 9/22 快照补登 RAW 血缘(append-only, 不改不覆盖).
背景: 客户表已由 9/14 快照(User2026091410413051852.xlsx,2273) 换为 9/22 快照
      (User-202609221722.xlsx,2292), 但 fix_customer_refresh.py / fix_customer_reread.py
      只更新了 customer 表, 未登记血缘 -> raw_file 仍指向旧文件/2273, 可追溯性(P6)有洞.
本脚本(幂等, 不重建库, 只写 RAW 血缘两张表, 不碰 customer/订单/结果):
  1) INSERT OR IGNORE 新增 raw_import_batch 4 (batch_code 唯一, 重跑不重复);
  2) 用修正读取器实读 User-202609221722.xlsx, 按 ingest 同款列约定登记 raw_file
     (header_row=1, read_method=readers.read_table, data_rows=实读行数);
  3) 保留 batch 1 旧客户行作历史记录(append-only), 不删除不改写;
  4) 输出 BEFORE/AFTER + 外键校验.
imported_at 取 fix_customer_refresh.txt 的 mtime(=客户刷新实际入库时间 2026-09-22 17:30).
"""
import os, sys, sqlite3, datetime
sys.path.insert(0, os.path.dirname(__file__))
from readers import read_table

MVP    = r"D:\Peggy zhan\智能EC101\数据底座\第三阶段数据库设计\mvp"
BASE   = r"D:\Peggy zhan\智能EC101\数据底座\第三阶段数据库设计\快马-兴路强-试点"
DB     = os.path.join(MVP, "ec101_mvp.db")
REPORT = os.path.join(MVP, "scripts", "fix_lineage_cust_refresh.txt")
F_CUST = os.path.join(BASE, "User-202609221722.xlsx")
REFRESH_REPORT = os.path.join(MVP, "scripts", "fix_customer_refresh.txt")

BATCH_CODE = "KM-XLQ-CUST-REFRESH-20260922"
PLATFORM   = "快马"
DEALER     = "深圳市兴路强商贸有限公司"
OPERATOR   = "小凡"

rep = open(REPORT, "w", encoding="utf-8")
def w(*a):
    s = " ".join(str(x) for x in a); print(s); rep.write(s + "\n")

# 客户刷新实际入库时间 = fix_customer_refresh.txt 的 mtime
if os.path.exists(REFRESH_REPORT):
    imported_at = datetime.datetime.fromtimestamp(
        os.path.getmtime(REFRESH_REPORT)).strftime("%Y-%m-%d %H:%M:%S")
else:
    imported_at = "2026-09-22 17:30:00"

con = sqlite3.connect(DB); con.execute("PRAGMA foreign_keys = ON"); cur = con.cursor()

w("== BEFORE ==")
w("raw_import_batch 数 =", cur.execute("SELECT COUNT(*) FROM raw_import_batch").fetchone()[0])
w("raw_file 数 =", cur.execute("SELECT COUNT(*) FROM raw_file").fetchone()[0])
w("batch1 客户行(旧, 保留作历史):")
for r in cur.execute("SELECT file_id,batch_id,file_name,module,file_signature,data_rows FROM raw_file WHERE module='客户'"):
    w("   ", r)

# ---------- 1. 新增批次 4 ----------
cur.execute("""INSERT OR IGNORE INTO raw_import_batch(batch_code,source_platform,dealer_name,imported_at,operator)
               VALUES(?,?,?,?,?)""", (BATCH_CODE, PLATFORM, DEALER, imported_at, OPERATOR))
w("\n== 1. 新增批次 ==", "inserted =", cur.rowcount, " batch_code =", BATCH_CODE, " imported_at =", imported_at)
BATCH = cur.execute("SELECT batch_id FROM raw_import_batch WHERE batch_code=?", (BATCH_CODE,)).fetchone()[0]
w("batch_id =", BATCH)

# ---------- 2. 实读新快照并登记 raw_file ----------
sig, sheet, hdr, rows = read_table(F_CUST)
w("\n== 2. 实读新快照 ==", "sig=", sig, "sheet=", sheet, "数据行=", len(rows))
cur.execute("""INSERT OR IGNORE INTO raw_file(batch_id,file_name,module,file_signature,read_method,sheet_name,header_row,data_rows)
               VALUES(?,?,?,?,?,?,?,?)""",
            (BATCH, os.path.basename(F_CUST), "客户", sig, "readers.read_table", sheet, 1, len(rows)))
w("raw_file 登记 inserted =", cur.rowcount, " data_rows =", len(rows))

con.commit()

# ---------- AFTER ----------
w("\n== AFTER ==")
w("raw_import_batch 数 =", cur.execute("SELECT COUNT(*) FROM raw_import_batch").fetchone()[0], "(应 4)")
w("raw_file 数 =", cur.execute("SELECT COUNT(*) FROM raw_file").fetchone()[0], "(应 12)")
w("全部批次:")
for r in cur.execute("SELECT batch_id,batch_code,operator,imported_at FROM raw_import_batch ORDER BY batch_id"):
    w("   ", r)
w("客户模块血缘行(旧+新):")
for r in cur.execute("SELECT file_id,batch_id,file_name,file_signature,data_rows FROM raw_file WHERE module='客户' ORDER BY file_id"):
    w("   ", r)
w("customer 总数(应不变 2292) =", cur.execute("SELECT COUNT(*) FROM customer").fetchone()[0])
w("customer_id 校验和(应不变 2627781) =", cur.execute("SELECT SUM(customer_id) FROM customer").fetchone()[0])
fk = cur.execute("PRAGMA foreign_key_check").fetchall()
w("FK violations(应空) =", fk)
con.close(); rep.close()
