# -*- coding: utf-8 -*-
"""EC101 MVP 定向修正 — readers.py OOXML 正则 bug 修复后, 用修正读取器就地重灌 customer 描述列.
背景: 旧 readers.py 正则把"空样式格 <c/>"与下一个有值格合并, 导致 .xlsx 值左移错位且共享字符串
      被存成原始索引. 客户主数据 2292 行 100% 受影响 -> customer_type/level/tag/region/created_at/status 全错
      (但连接键 platform_customer_no 与客户名称/所属业务员在错位起点之前, 安全).
      商品主数据/满赠指定商品 0% 受影响; 销售明细.xlsx 虽 100% 受影响但只登记血缘行数, 不参与计算.
      => 已算结果(满减2040/1995、满赠98单、券台账+order_id713、费用)全部安全, 无需重算.
本脚本(幂等, 不重建库, 只动 customer 描述列):
  按 platform_customer_no 就地 UPDATE customer_name/type/level/tag/region/salesperson/created_at/status;
  不改 customer_id / dealer_platform_id / platform_customer_no / swire_outlet_no -> FK 与已算结果零扰动.
输出 BEFORE/AFTER + customer_id 校验和 + 文件/库双向差集 + FK 校验.
"""
import os, sys, sqlite3
sys.path.insert(0, os.path.dirname(__file__))
from readers import read_table, to_datetime_text

MVP   = r"D:\Peggy zhan\智能EC101\数据底座\第三阶段数据库设计\mvp"
BASE  = r"D:\Peggy zhan\智能EC101\数据底座\第三阶段数据库设计\快马-兴路强-试点"
DB    = os.path.join(MVP, "ec101_mvp.db")
REPORT= os.path.join(MVP, "scripts", "fix_customer_reread.txt")
F_CUST_NEW = os.path.join(BASE, "User-202609221722.xlsx")

rep = open(REPORT, "w", encoding="utf-8")
def w(*a):
    s = " ".join(str(x) for x in a); print(s); rep.write(s + "\n")
def cell(row, idx, default=""):
    if idx is None or idx < 0 or idx >= len(row): return default
    v = row[idx]; return v if v is not None else default

con = sqlite3.connect(DB); con.execute("PRAGMA foreign_keys = ON"); cur = con.cursor()
DP = cur.execute("SELECT dealer_platform_id FROM dealer_platform ORDER BY dealer_platform_id LIMIT 1").fetchone()[0]

def snapshot(tag):
    w(f"\n== {tag} ==")
    w("  customer 总数 =", cur.execute("SELECT COUNT(*) FROM customer WHERE dealer_platform_id=?", (DP,)).fetchone()[0])
    w("  customer_id 校验和(SUM/MIN/MAX/COUNT) =",
      cur.execute("SELECT SUM(customer_id),MIN(customer_id),MAX(customer_id),COUNT(customer_id) FROM customer WHERE dealer_platform_id=?", (DP,)).fetchone())
    w("  customer_type 为空的客户数 =",
      cur.execute("SELECT COUNT(*) FROM customer WHERE dealer_platform_id=? AND (customer_type IS NULL OR TRIM(customer_type)='')", (DP,)).fetchone()[0])
    w("  customer_type 取值分布:")
    for r in cur.execute("SELECT customer_type,COUNT(*) FROM customer WHERE dealer_platform_id=? GROUP BY customer_type ORDER BY COUNT(*) DESC", (DP,)):
        w("     ", r)

w("== 0. 目标 ==")
w("  dealer_platform_id =", DP, " 客户主数据 =", os.path.basename(F_CUST_NEW))
snapshot("BEFORE")

w("\n== BEFORE: 2 个目标客户整行 ==")
for r in cur.execute("""SELECT customer_id,platform_customer_no,customer_name,customer_type,customer_level,
                        customer_tag,customer_region,salesperson_name,created_at,status
                        FROM customer WHERE platform_customer_no IN ('WX-00000000000007507909','WX-00000000000007507908')
                        ORDER BY customer_id"""):
    w("  ", r)

# ---- 用修正读取器重读客户主数据 ----
sig, sh, hdr, rows = read_table(F_CUST_NEW)
ci = {h: i for i, h in enumerate(hdr)}
w("\n== 1. 修正读取器重读 ==", "sig=", sig, "sheet=", sh, "数据行=", len(rows))
w("   ci['客户类型'] =", ci.get("客户类型"), " ci['客户等级'] =", ci.get("客户等级"),
  " ci['状态'] =", ci.get("状态"), " ci['添加时间'] =", ci.get("添加时间"))

file_map = {}
for r in rows:
    no = cell(r, ci.get("客户编号")).strip()
    if not no:
        continue
    file_map[no] = (
        cell(r, ci.get("客户名称")).strip(),
        cell(r, ci.get("客户类型")).strip(),
        cell(r, ci.get("客户等级")).strip(),
        cell(r, ci.get("客户标签")).strip(),
        cell(r, ci.get("客户区域")).strip(),
        cell(r, ci.get("所属业务员")).strip(),
        to_datetime_text(cell(r, ci.get("添加时间"))),
        cell(r, ci.get("状态")).strip(),
    )
w("   文件唯一客户编号 =", len(file_map))

db_nos = {no for (no,) in cur.execute("SELECT platform_customer_no FROM customer WHERE dealer_platform_id=?", (DP,))}
only_file = sorted(set(file_map) - db_nos)
only_db   = sorted(db_nos - set(file_map))
w("   文件有库没有 =", len(only_file), only_file[:10])
w("   库有文件没有 =", len(only_db), only_db[:10])

# ---- 就地 UPDATE 描述列(保留 customer_id) ----
updated = 0
for no, vals in file_map.items():
    cur.execute("""UPDATE customer SET customer_name=?,customer_type=?,customer_level=?,customer_tag=?,
                   customer_region=?,salesperson_name=?,created_at=?,status=?
                   WHERE dealer_platform_id=? AND platform_customer_no=?""",
                vals + (DP, no))
    updated += cur.rowcount
con.commit()
w("\n== 2. 就地 UPDATE 描述列 == 命中并更新行 =", updated, "(应≈2292; customer_id 不变)")

snapshot("AFTER")
w("\n== AFTER: 2 个目标客户整行(应 customer_type='零售' status='正常') ==")
for r in cur.execute("""SELECT customer_id,platform_customer_no,customer_name,customer_type,customer_level,
                        customer_tag,customer_region,salesperson_name,created_at,status
                        FROM customer WHERE platform_customer_no IN ('WX-00000000000007507909','WX-00000000000007507908')
                        ORDER BY customer_id"""):
    w("  ", r)

w("\n== 3. 关联订单复核(order_id 166/198 的客户类型) ==")
for r in cur.execute("""SELECT oh.order_id,oh.order_no,c.platform_customer_no,c.customer_name,c.customer_type,c.status
                        FROM order_header oh JOIN customer c ON oh.customer_id=c.customer_id
                        WHERE oh.order_id IN (166,198) ORDER BY oh.order_id"""):
    w("  ", r)

fk = cur.execute("PRAGMA foreign_key_check").fetchall()
w("\n== 4. FK violations(应空) ==", fk)
con.close(); rep.close()
