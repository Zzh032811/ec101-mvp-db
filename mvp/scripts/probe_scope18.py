# -*- coding: utf-8 -*-
# 探查：满赠 activity_scope 现状(占位行) + 18个指定商品编号能否匹配 product 表
import sqlite3, os, io, sys
sys.path.insert(0, os.path.dirname(__file__))
import readers

DB = os.path.join(os.path.dirname(__file__), "..", "ec101_mvp.db")
XLSX = r"D:\Peggy zhan\智能EC101\数据底座\第三阶段数据库设计\快马-兴路强-试点\满赠\满赠指定商品列表.xlsx"
OUT = os.path.join(os.path.dirname(__file__), "probe_scope18.txt")
buf = io.StringIO()
def w(s=""): buf.write(str(s)+"\n")

con = sqlite3.connect(DB); con.execute("PRAGMA foreign_keys=ON"); cur = con.cursor()

w("== A. activity 列表 ==")
for r in cur.execute("SELECT activity_id,activity_name,product_scope_type,disabled_product_scope_type FROM activity ORDER BY activity_id"):
    w("  "+str(r))

w("\n== B. activity_scope 全部现状(按活动) ==")
cur.execute("""SELECT s.scope_id,s.activity_id,a.activity_name,s.scope_category,s.scope_dimension,s.scope_value
               FROM activity_scope s JOIN activity a ON a.activity_id=s.activity_id
               ORDER BY s.activity_id,s.scope_id""")
for r in cur.fetchall():
    w("  "+str(r))

w("\n== C. 满赠(activity_id=2) scope 计数 by category/dimension ==")
cur.execute("SELECT scope_category,scope_dimension,COUNT(*) FROM activity_scope WHERE activity_id=2 GROUP BY scope_category,scope_dimension")
for r in cur.fetchall():
    w("  "+str(r))

# 读 18 SKU
sig, sheet, hdr, rows = readers.read_table(XLSX)
w(f"\n== D. 满赠指定商品列表.xlsx == sig={sig} sheet={sheet} rows={len(rows)}")
w("  header: "+str(hdr))
ix = {h:i for i,h in enumerate(hdr)}
def cell(r,i):
    return str(r[i]).strip() if (i is not None and i < len(r)) else ""
skus = []
for r in rows:
    no = str(cell(r, ix.get("编号"))).strip()
    nm = str(cell(r, ix.get("商品名称"))).strip()
    cat = str(cell(r, ix.get("目录"))).strip()
    brd = str(cell(r, ix.get("品牌"))).strip()
    if no:
        skus.append((no,nm,cat,brd))
w(f"  解析出 SKU 数 = {len(skus)}")

w("\n== E. 18编号 在 product 表匹配情况 ==")
DP = cur.execute("SELECT dealer_platform_id FROM dealer_platform WHERE dealer_name=? AND platform_name=?",
                 ("深圳市兴路强商贸有限公司","快马")).fetchone()[0]
w(f"  dealer_platform_id={DP}")
hit_no=hit_bc=hit_nm=0
for no,nm,cat,brd in skus:
    r1 = cur.execute("SELECT product_id,platform_product_no,product_name,barcode FROM product WHERE dealer_platform_id=? AND platform_product_no=?",(DP,no)).fetchone()
    r2 = cur.execute("SELECT product_id,platform_product_no,product_name,barcode FROM product WHERE dealer_platform_id=? AND barcode=?",(DP,no)).fetchone() if not r1 else None
    r3 = cur.execute("SELECT product_id,platform_product_no,product_name FROM product WHERE dealer_platform_id=? AND product_name=?",(DP,nm)).fetchone()
    if r1: hit_no+=1
    if r2: hit_bc+=1
    if r3: hit_nm+=1
    w(f"  编号={no!r:24} 名称={nm!r:34} | byNo={r1} byBarcode={r2} byName={r3}")
w(f"\n  匹配汇总: 按编号命中={hit_no}/18  按条码命中={hit_bc}/18  按名称命中={hit_nm}/18")

w("\n== F. product 表 platform_product_no 样例(看编号格式) ==")
for r in cur.execute("SELECT platform_product_no,product_name,barcode FROM product WHERE dealer_platform_id=? AND product_name LIKE '%雪碧%' LIMIT 12",(DP,)):
    w("  "+str(r))

con.close()
data=buf.getvalue()
open(OUT,"w",encoding="utf-8").write(data)
print("WROTE",os.path.abspath(OUT))
