# -*- coding: utf-8 -*-
"""复核 2 个新客户的 customer_type: Excel 原值 vs 库里存的值 vs 表头真实列名."""
import os, sys, sqlite3
sys.path.insert(0, os.path.dirname(__file__))
from readers import read_table

MVP   = r"D:\Peggy zhan\智能EC101\数据底座\第三阶段数据库设计\mvp"
BASE  = r"D:\Peggy zhan\智能EC101\数据底座\第三阶段数据库设计\快马-兴路强-试点"
DB    = os.path.join(MVP, "ec101_mvp.db")
F_CUST_NEW = os.path.join(BASE, "User-202609221722.xlsx")
REPORT = os.path.join(MVP, "scripts", "probe_custtype.txt")

TARGET_NOS = ["WX-00000000000007507909", "WX-00000000000007507908"]

rep = open(REPORT, "w", encoding="utf-8")
def w(*a):
    s = " ".join(str(x) for x in a); print(s); rep.write(s + "\n")
def cell(row, idx, default=""):
    if idx is None or idx < 0 or idx >= len(row): return default
    v = row[idx]; return v if v is not None else default

sig, sh, hdr, rows = read_table(F_CUST_NEW)
w("== A. 新客户主数据文件 ==")
w("  sig=", sig, " sheet=", sh, " 数据行=", len(rows))
w("== B. 表头真实列名(带索引) ==")
for i, h in enumerate(hdr):
    w(f"  [{i}] {h!r}")

ci = {h: i for i, h in enumerate(hdr)}
w("\n== C. 含'类型'或'分类'或'性质'的列 ==")
for i, h in enumerate(hdr):
    if any(k in str(h) for k in ("类型", "分类", "性质", "等级", "标签")):
        w(f"  [{i}] {h!r}")

w("\n== D. 脚本用的键 ci.get('客户类型') =", ci.get("客户类型"), "==")
w("   (若为 None 则说明 Excel 没有叫'客户类型'的列, customer_type 被存成空)")

w("\n== E. 2 个目标客户在 Excel 的整行原值 ==")
i_no = ci.get("客户编号")
for r in rows:
    no = str(cell(r, i_no)).strip()
    if no in TARGET_NOS:
        w(f"  --- 客户编号 {no} ---")
        for i, h in enumerate(hdr):
            w(f"      {h!r:24} = {cell(r, i)!r}")

w("\n== F. 库里 customer_id 2284/2285 实际存的值 ==")
con = sqlite3.connect(DB); cur = con.cursor()
cols = [c[1] for c in cur.execute("PRAGMA table_info(customer)")]
w("  customer 列:", cols)
for r in cur.execute("SELECT * FROM customer WHERE customer_id IN (2284,2285) ORDER BY customer_id"):
    w("  ---", dict(zip(cols, r)))
w("\n== G. 全库 customer_type 空值统计 ==")
tot = cur.execute("SELECT COUNT(*) FROM customer").fetchone()[0]
empty = cur.execute("SELECT COUNT(*) FROM customer WHERE customer_type IS NULL OR TRIM(customer_type)=''").fetchone()[0]
w(f"  customer 总数={tot}  customer_type 为空={empty}")
w("  customer_type 取值分布(前20):")
for r in cur.execute("SELECT customer_type, COUNT(*) FROM customer GROUP BY customer_type ORDER BY COUNT(*) DESC LIMIT 20"):
    w("    ", r)
con.close(); rep.close()
