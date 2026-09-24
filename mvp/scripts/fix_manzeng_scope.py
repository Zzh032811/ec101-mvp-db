# -*- coding: utf-8 -*-
"""一次性修正(可审计)：把满赠(activity_id=2)的占位"指定商品"范围行替换为
满赠指定商品列表.xlsx 的 18 个雪碧 SKU(按 编号=platform_product_no)。
同时移除已关闭的质量台账"满赠指定商品清单未导出"。带 BEFORE/AFTER 与 FK 校验。
依据 2026-09-22 业务决策(§7.7)：18 个指定商品清单已拿到，落 activity_scope。
只删 scope_category='商品' 的占位行，保留 5 行客户类型范围。
"""
import os, sys, sqlite3
sys.path.insert(0, os.path.dirname(__file__))
from readers import read_table

MVP   = r"D:\Peggy zhan\智能EC101\数据底座\第三阶段数据库设计\mvp"
BASE  = r"D:\Peggy zhan\智能EC101\数据底座\第三阶段数据库设计\快马-兴路强-试点"
DB    = os.path.join(MVP, "ec101_mvp.db")
F_SCOPE = os.path.join(BASE, "满赠", "满赠指定商品列表.xlsx")
OUT   = os.path.join(os.path.dirname(__file__), "fix_manzeng_scope.txt")
ACT_NAME = "满赠优惠"

con = sqlite3.connect(DB); con.execute("PRAGMA foreign_keys=ON"); cur = con.cursor()
rep = open(OUT, "w", encoding="utf-8")
def w(*a):
    s = " ".join(str(x) for x in a); rep.write(s + "\n")

# 读 18 SKU
sig, sheet, hdr, rows = read_table(F_SCOPE)
ix = {h: i for i, h in enumerate(hdr)}
def cell(r, i): return str(r[i]).strip() if (i is not None and i < len(r)) else ""
skus = []
for r in rows:
    no = cell(r, ix.get("编号")); nm = cell(r, ix.get("商品名称"))
    if no: skus.append((no, nm))

aid, dp = cur.execute("SELECT activity_id,dealer_platform_id FROM activity WHERE activity_name=?", (ACT_NAME,)).fetchone()
cb_row = cur.execute("SELECT calc_batch_id FROM result_calc_batch WHERE operator LIKE '满赠%' ORDER BY calc_batch_id DESC LIMIT 1").fetchone()
cb = cb_row[0] if cb_row else None
w(f"满赠 activity_id={aid}  dealer_platform_id={dp}  calc_batch_id={cb}  (指定商品SKU={len(skus)}, sig={sig}, sheet={sheet})")

w("--- BEFORE ---")
w("scope(满赠):", cur.execute("SELECT scope_id,scope_category,scope_dimension,scope_value FROM activity_scope WHERE activity_id=? ORDER BY scope_id", (aid,)).fetchall())
w("quality(满赠批次):", cur.execute("SELECT issue_id,issue_type,level FROM result_quality_issue WHERE calc_batch_id=? ORDER BY issue_id", (cb,)).fetchall() if cb else "(无批次)")
w("activity_scope 总行数:", cur.execute("SELECT COUNT(*) FROM activity_scope").fetchone()[0])
w("result_quality_issue 总行数:", cur.execute("SELECT COUNT(*) FROM result_quality_issue").fetchone()[0])

# 1. 删占位"商品"范围行(保留客户类)
cur.execute("DELETE FROM activity_scope WHERE activity_id=? AND scope_category='商品'", (aid,))
deleted_scope = cur.rowcount
# 2. 插入 18 个指定商品(编号=platform_product_no, 字符串)
inserted = 0
for no, nm in skus:
    cur.execute("INSERT INTO activity_scope(activity_id,scope_category,scope_dimension,scope_value) VALUES(?,?,?,?)",
                (aid, "商品", "商品", no))
    inserted += 1
# 3. 移除已关闭的质量台账
deleted_q = 0
if cb:
    cur.execute("DELETE FROM result_quality_issue WHERE calc_batch_id=? AND issue_type='满赠指定商品清单未导出'", (cb,))
    deleted_q = cur.rowcount
con.commit()

w(f"\ndeleted 商品占位行={deleted_scope}  inserted 指定商品={inserted}  deleted quality={deleted_q}")
w("--- AFTER ---")
w("scope(满赠) by cat/dim:", cur.execute("SELECT scope_category,scope_dimension,COUNT(*) FROM activity_scope WHERE activity_id=? GROUP BY scope_category,scope_dimension", (aid,)).fetchall())
w("scope(满赠,商品) 18值:", cur.execute("SELECT scope_value FROM activity_scope WHERE activity_id=? AND scope_category='商品' ORDER BY scope_id", (aid,)).fetchall())
w("quality(满赠批次):", cur.execute("SELECT issue_id,issue_type,level FROM result_quality_issue WHERE calc_batch_id=? ORDER BY issue_id", (cb,)).fetchall() if cb else "(无批次)")
miss = [no for no, _ in skus if not cur.execute("SELECT 1 FROM product WHERE dealer_platform_id=? AND platform_product_no=?", (dp, no)).fetchone()]
w("18编号 join product 未命中(应空):", miss)
w("满减 scope 不变(应7行):", cur.execute("SELECT COUNT(*) FROM activity_scope WHERE activity_id=1").fetchone()[0])
w("activity_scope 总行数(应30):", cur.execute("SELECT COUNT(*) FROM activity_scope").fetchone()[0])
w("result_quality_issue 总行数(应8):", cur.execute("SELECT COUNT(*) FROM result_quality_issue").fetchone()[0])
w("FK violations(应空):", cur.execute("PRAGMA foreign_key_check").fetchall())

con.close(); rep.close()
print("WROTE", os.path.abspath(OUT))
