# -*- coding: utf-8 -*-
"""只读诊断: 复现订单行商品匹配, 列出未匹配(product_id为空)的异常明细.
不写库, 不改任何源文件. 结果输出 UTF-8 文件 diag_prod_match.txt.
"""
import os, sys, sqlite3
from collections import defaultdict, Counter
sys.path.insert(0, os.path.dirname(__file__))
from readers import read_table, to_num

MVP  = r"D:\Peggy zhan\智能EC101\数据底座\第三阶段数据库设计\mvp"
BASE = r"D:\Peggy zhan\智能EC101\数据底座\第三阶段数据库设计\快马-兴路强-试点"
DB   = os.path.join(MVP, "ec101_mvp.db")
OUT  = os.path.join(MVP, "diag_prod_match.txt")

F_PROD = os.path.join(BASE, "Product2026091410431769689.xlsx")
ORDERS = [
    ("满减", os.path.join(BASE, "满减", "快马-兴路强-满减-订单明细-20260831-20260917.xls")),
    ("满赠", os.path.join(BASE, "满赠", "快马-兴路强-满赠-订单明细-20260819-20260831.xls")),
]

out = open(OUT, "w", encoding="utf-8")
def w(*a):
    s = " ".join(str(x) for x in a); print(s); out.write(s + "\n")

def cell(row, idx, default=""):
    if idx is None or idx < 0 or idx >= len(row): return default
    v = row[idx]; return v if v is not None else default

# ---- 商品主数据索引(复现接入逻辑) ----
sig, sheet, HDR_P, ROWS_P = read_table(F_PROD)
pi = {h: i for i, h in enumerate(HDR_P)}
w("== 商品主数据 ==", "sig=", sig, "sheet=", sheet, "行=", len(ROWS_P))
w("   表头字段:", HDR_P)

prod_no_set = set()          # 所有商品编号
barcode_set = set()          # 所有条码
prod_name_by_no = {}
for r in ROWS_P:
    no = cell(r, pi.get("商品编号")).strip()
    bc = cell(r, pi.get("条形码")).strip()
    nm = cell(r, pi.get("商品名称")).strip()
    if no:
        prod_no_set.add(no); prod_name_by_no[no] = nm
    if bc:
        barcode_set.add(bc)
w("   唯一商品编号=", len(prod_no_set), " 唯一条码=", len(barcode_set))
# 编号/条码长度分布
w("   商品编号长度分布:", dict(Counter(len(x) for x in prod_no_set)))
w("   条码长度分布:", dict(Counter(len(x) for x in barcode_set)))

# ---- 逐个订单文件比对 ----
grand_miss_rows = 0
grand_miss_skus = Counter()      # 商品编号 -> 未匹配行数
miss_detail = {}                 # 商品编号 -> dict(name,barcode,spec,rows,files)
per_file = {}

for tag, path in ORDERS:
    if not os.path.exists(path):
        w(f"\n!! 缺文件 {tag}: {path}"); continue
    sig, sheet, HDR_O, ROWS_O = read_table(path)
    oi = {h: i for i, h in enumerate(HDR_O)}
    i_no=oi.get("订单编号"); i_prod=oi.get("商品编号"); i_bc=oi.get("商品条码")
    i_name=oi.get("商品名称"); i_spec=oi.get("规格"); i_qty=oi.get("订货数量")
    hit_no=hit_bc=miss=0
    file_miss_sku=Counter()
    for r in ROWS_O:
        ono = cell(r, i_no).strip()
        if not ono: continue
        pno = cell(r, i_prod).strip()
        bc  = cell(r, i_bc).strip()
        if pno in prod_no_set:
            hit_no += 1
        elif bc and bc in barcode_set:
            hit_bc += 1
        else:
            miss += 1
            file_miss_sku[pno or ("条码:"+bc)] += 1
            key = pno or ("条码:"+bc)
            d = miss_detail.setdefault(key, dict(
                name=cell(r, i_name).strip(), barcode=bc,
                spec=cell(r, i_spec).strip(), rows=0, files=set(), plen=len(pno)))
            d["rows"] += 1; d["files"].add(tag)
    per_file[tag] = dict(rows=len(ROWS_O), hit_no=hit_no, hit_bc=hit_bc, miss=miss,
                         miss_sku=len(file_miss_sku))
    grand_miss_rows += miss
    for k,v in file_miss_sku.items(): grand_miss_skus[k]+=v
    w(f"\n== {tag} 订单明细 == sig={sig} 数据行={len(ROWS_O)}")
    w(f"   按商品编号命中={hit_no} 按条码兜底命中={hit_bc} 未匹配={miss} "
      f"匹配率={(hit_no+hit_bc)/max(1,hit_no+hit_bc+miss)*100:.2f}%")
    w(f"   未匹配涉及不同商品编号数={len(file_miss_sku)}")

w("\n\n========== 未匹配商品汇总(两文件合计) ==========")
w("未匹配订单行合计=", grand_miss_rows, " 不同商品编号合计=", len(grand_miss_skus))
w("未匹配商品编号长度分布:", dict(Counter(len(k.replace('条码:','')) for k in grand_miss_skus)))

# 按未匹配行数排序, 全部列出
w("\n---- 未匹配商品明细(按行数降序, 全部列示) ----")
w(f"{'商品编号':<16}{'行数':>5}  {'编号长度':>6}  {'名称':<28}{'条码':<16}{'规格':<12}{'来源'}")
rows_sorted = sorted(miss_detail.items(), key=lambda kv: -kv[1]["rows"])
for k, d in rows_sorted:
    w(f"{k:<16}{d['rows']:>5}  {d['plen']:>6}  {d['name'][:26]:<28}{d['barcode']:<16}{d['spec'][:10]:<12}{'+'.join(sorted(d['files']))}")

# ---- 根因验证: 这些未匹配编号, 是否作为条码存在于主数据? 或反之 ----
w("\n---- 根因交叉验证 ----")
sample = [k for k in grand_miss_skus if not k.startswith('条码:')][:15]
for pno in sample:
    in_no  = pno in prod_no_set
    in_bc  = pno in barcode_set
    # 主数据里是否有以该编号结尾/包含关系的条码
    bc_contains = [b for b in list(barcode_set)[:0]]  # skip heavy
    w(f"  订单商品编号={pno}(len{len(pno)}) 在主数据: 作为编号={in_no} 作为条码={in_bc}")

# ---- 与数据库实际 NULL 行数对照 ----
w("\n---- 与数据库对照 ----")
con = sqlite3.connect(DB); cur = con.cursor()
db_null = cur.execute("SELECT count(*) FROM order_line WHERE product_id IS NULL").fetchone()[0]
db_total = cur.execute("SELECT count(*) FROM order_line").fetchone()[0]
w("  DB order_line 总行=", db_total, " product_id为空行=", db_null)
w("  脚本复现未匹配行(未聚合)=", grand_miss_rows)
w("  注: DB按(订单,商品)聚合入库, 与源文件逐行计数口径不同, 数量级应一致")
con.close()
out.close()
print("\nOUT ->", OUT)
