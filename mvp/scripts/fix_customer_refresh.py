# -*- coding: utf-8 -*-
"""EC101 MVP 定向修正 — 用新客户主数据快照(2026-09-22)补齐 2 个未匹配 customer_id.
背景: 客户主数据原为 9/14 快照(User2026091410413051852.xlsx, 2273客户), 已被 9/22 快照
      (User-202609221722.xlsx, 2292客户)替换; 旧文件已不在. 2 张 9/16 订单(订单号
      1012420526026091600049 / ...600017)的客户编号(生鲜宜购(RTM)（0098 / 惠乐惠便利店)
      当时不在主数据 -> order_header.customer_id 为空.
本脚本(幂等, 不重建库):
  1) INSERT OR IGNORE 把新快照里现库没有的客户补进 customer(只增不改, 不动现有 customer_id 映射);
  2) 用订单明细把 order_header 中 customer_id 为空的单, 按客户编号回填;
  3) 删除已解决的质量台账"客户匹配缺口"(calc_batch 1);
  4) 输出 BEFORE/AFTER + 外键校验.
只动 customer / order_header.customer_id / result_quality_issue, 不碰权益/费用结果.
"""
import os, sys, sqlite3
sys.path.insert(0, os.path.dirname(__file__))
from readers import read_table, to_datetime_text

MVP   = r"D:\Peggy zhan\智能EC101\数据底座\第三阶段数据库设计\mvp"
BASE  = r"D:\Peggy zhan\智能EC101\数据底座\第三阶段数据库设计\快马-兴路强-试点"
DB    = os.path.join(MVP, "ec101_mvp.db")
REPORT= os.path.join(MVP, "scripts", "fix_customer_refresh.txt")

F_CUST_NEW = os.path.join(BASE, "User-202609221722.xlsx")
F_ORDER    = os.path.join(BASE, "满减", "快马-兴路强-满减-订单明细-20260831-20260917.xls")

rep = open(REPORT, "w", encoding="utf-8")
def w(*a):
    s = " ".join(str(x) for x in a); print(s); rep.write(s + "\n")
def cell(row, idx, default=""):
    if idx is None or idx < 0 or idx >= len(row): return default
    v = row[idx]; return v if v is not None else default

con = sqlite3.connect(DB); con.execute("PRAGMA foreign_keys = ON"); cur = con.cursor()
DP = cur.execute("SELECT dealer_platform_id FROM dealer_platform ORDER BY dealer_platform_id LIMIT 1").fetchone()[0]

# ---------- BEFORE ----------
w("== BEFORE ==")
w("dealer_platform_id =", DP)
cust_before = cur.execute("SELECT COUNT(*) FROM customer WHERE dealer_platform_id=?", (DP,)).fetchone()[0]
null_orders_before = cur.execute(
    "SELECT order_id,order_no,order_time,order_status FROM order_header WHERE customer_id IS NULL ORDER BY order_id").fetchall()
w("customer 数 =", cust_before)
w("order_header customer_id 为空 =", len(null_orders_before), null_orders_before)
q_before = cur.execute(
    "SELECT issue_id,issue_type,reason,calc_batch_id FROM result_quality_issue WHERE issue_type='客户匹配缺口'").fetchall()
w("质量台账'客户匹配缺口' =", q_before)
qi_before = cur.execute("SELECT COUNT(*) FROM result_quality_issue").fetchone()[0]
w("result_quality_issue 总数 =", qi_before)

# ---------- 1. 补客户(只增不改) ----------
sig_c, sh_c, hdr_c, rows_c = read_table(F_CUST_NEW)
ci = {h: i for i, h in enumerate(hdr_c)}
w("\n== 1. 新客户主数据 ==", "sig=", sig_c, "sheet=", sh_c, "数据行=", len(rows_c))
inserted = 0
for r in rows_c:
    no = cell(r, ci.get("客户编号")).strip()
    if not no:
        continue
    cur.execute("""INSERT OR IGNORE INTO customer(dealer_platform_id,platform_customer_no,customer_name,
        customer_type,customer_level,customer_tag,customer_region,salesperson_name,created_at,status)
        VALUES(?,?,?,?,?,?,?,?,?,?)""",
        (DP, no, cell(r, ci.get("客户名称")).strip(), cell(r, ci.get("客户类型")).strip(),
         cell(r, ci.get("客户等级")).strip(), cell(r, ci.get("客户标签")).strip(),
         cell(r, ci.get("客户区域")).strip(), cell(r, ci.get("所属业务员")).strip(),
         to_datetime_text(cell(r, ci.get("添加时间"))), cell(r, ci.get("状态")).strip()))
    if cur.rowcount > 0:
        inserted += 1
cust_id_by_no = {no: i for (no, i) in cur.execute(
    "SELECT platform_customer_no,customer_id FROM customer WHERE dealer_platform_id=?", (DP,))}
w("INSERT OR IGNORE 实际新增客户 =", inserted, " 现 customer 总数 =", len(cust_id_by_no))

# ---------- 2. 回填 order_header.customer_id ----------
sig_o, sh_o, hdr_o, rows_o = read_table(F_ORDER)
oi = {h: i for i, h in enumerate(hdr_o)}
i_no = oi.get("订单编号"); i_cust = oi.get("客户编号"); i_cname = oi.get("客户名称")
no2cust = {}
for r in rows_o:
    n = cell(r, i_no).strip()
    if n and n not in no2cust:
        no2cust[n] = (cell(r, i_cust).strip(), cell(r, i_cname).strip())
w("\n== 2. 回填 order_header.customer_id ==")
updated = 0; still_null = []
for oid, ono, otime, ostatus in null_orders_before:
    cust_no, cust_nm = no2cust.get(ono, ("", ""))
    cid = cust_id_by_no.get(cust_no)
    if cid:
        cur.execute("UPDATE order_header SET customer_id=? WHERE order_id=?", (cid, oid))
        updated += 1
        w(f"  回填 order_id={oid} 订单号={ono} 客户编号={cust_no} 客户名称={cust_nm} -> customer_id={cid}")
    else:
        still_null.append((oid, ono, cust_no, cust_nm))
        w(f"  仍无法回填 order_id={oid} 订单号={ono} 客户编号={cust_no!r} 客户名称={cust_nm!r}")
w("回填成功 =", updated, " 仍为空 =", len(still_null), still_null)

# ---------- 3. 消除质量台账 ----------
w("\n== 3. 质量台账 ==")
if updated > 0 and not still_null:
    cur.execute("DELETE FROM result_quality_issue WHERE issue_type='客户匹配缺口' AND calc_batch_id=1")
    w("已删除'客户匹配缺口'(calc_batch 1), 删除行 =", cur.rowcount)
else:
    w("存在仍无法回填的单, 保留'客户匹配缺口'台账不删")

con.commit()

# ---------- AFTER ----------
w("\n== AFTER ==")
cust_after = cur.execute("SELECT COUNT(*) FROM customer WHERE dealer_platform_id=?", (DP,)).fetchone()[0]
null_after = cur.execute("SELECT COUNT(*) FROM order_header WHERE customer_id IS NULL").fetchone()[0]
qi_after = cur.execute("SELECT COUNT(*) FROM result_quality_issue").fetchone()[0]
w("customer 数 =", cust_after, "(应 2292)")
w("order_header customer_id 为空 =", null_after, "(应 0)")
w("result_quality_issue 总数 =", qi_after, "(应 7)")
w("两张单回填后状态:")
for r in cur.execute("""SELECT oh.order_id,oh.order_no,oh.customer_id,c.platform_customer_no,c.customer_name,c.customer_type
                        FROM order_header oh LEFT JOIN customer c ON oh.customer_id=c.customer_id
                        WHERE oh.order_id IN (166,198) ORDER BY oh.order_id"""):
    w("  ", r)
fk = cur.execute("PRAGMA foreign_key_check").fetchall()
w("FK violations(应空) =", fk)
con.close(); rep.close()
