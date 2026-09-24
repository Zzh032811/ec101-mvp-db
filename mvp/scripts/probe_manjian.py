# -*- coding: utf-8 -*-
"""满减接入前的数据勘察: 验证理论权益公式假设, 输出分布到 UTF-8 文件."""
import os, sys
from collections import Counter, defaultdict
sys.path.insert(0, os.path.dirname(__file__))
from readers import read_table, to_num, to_datetime_text

BASE = r"D:\Peggy zhan\智能EC101\数据底座\第三阶段数据库设计\快马-兴路强-试点"
F_ORDER = os.path.join(BASE, "满减", "快马-兴路强-满减-订单明细-20260831-20260917.xls")
F_ACT   = os.path.join(BASE, "满减", "快马-兴路强-满减-活动明细-20260831-20260917.xls")
F_SALES = os.path.join(BASE, "满减", "快马-兴路强-满减-销售明细-20260831-20260917.xlsx")

out = open(os.path.join(BASE, "..", "mvp", "probe_manjian.txt"), "w", encoding="utf-8")
def w(*a):
    print(*a, file=out)

# ---- 订单明细 ----
sig, sheet, hdr, rows = read_table(F_ORDER)
w("== 订单明细 ==", sig, sheet, "rows=", len(rows))
ci = {h: i for i, h in enumerate(hdr)}
i_no   = ci["订单编号"]; i_time = ci["下单时间"]; i_status = ci["订单状态"]
i_cust = ci["客户编号"]; i_prod = ci["商品编号"]
order_status = Counter()
order_time_by_no = {}
order_lines = Counter()
cust_by_no = {}
for r in rows:
    no = r[i_no].strip()
    if not no:
        continue
    order_status[r[i_status].strip()] += 1
    order_lines[no] += 1
    if no not in order_time_by_no:
        order_time_by_no[no] = to_datetime_text(r[i_time])
        cust_by_no[no] = r[i_cust].strip()
w("唯一订单数=", len(order_time_by_no))
w("订单状态分布(按行):", dict(order_status))
# 每单状态(取首行)
status_by_order = {}
for r in rows:
    no = r[i_no].strip()
    if no and no not in status_by_order:
        status_by_order[no] = r[i_status].strip()
w("订单状态分布(按单):", dict(Counter(status_by_order.values())))
w("订单行数分布 top:", Counter(order_lines.values()).most_common(8))

# ---- 活动明细 聚合 ----
sig2, sheet2, hdr2, rows2 = read_table(F_ACT)
w("\n== 活动明细 ==", sig2, sheet2, "rows=", len(rows2))
ai = {h: i for i, h in enumerate(hdr2)}
a_no = ai["订单号"]; a_amt = ai["商品总金额"]; a_disc = ai["促销优惠金额"]; a_pol = ai["享受促销政策"]
agg_amt = defaultdict(float)
agg_disc = defaultdict(float)
agg_lines = Counter()
pol_samples = set()
for r in rows2:
    no = r[a_no].strip()
    if not no:
        continue
    agg_amt[no] += to_num(r[a_amt]) or 0.0
    agg_disc[no] += to_num(r[a_disc]) or 0.0
    agg_lines[no] += 1
    if len(pol_samples) < 6:
        pol_samples.add(r[a_pol].strip()[:60])
w("活动明细唯一订单数=", len(agg_disc))
w("活动明细每单行数分布:", Counter(agg_lines.values()).most_common(8))
# Σ促销优惠金额 分布
disc_round = Counter(round(v, 2) for v in agg_disc.values())
w("Σ促销优惠金额分布(取整2位) top15:", disc_round.most_common(15))
eq15 = sum(1 for v in agg_disc.values() if abs(round(v,2) - 15.0) < 0.005)
lt15 = sum(1 for v in agg_disc.values() if round(v,2) < 14.995)
gt15 = sum(1 for v in agg_disc.values() if round(v,2) > 15.005)
w(f"Σ优惠=15: {eq15}  <15: {lt15}  >15: {gt15}  合计订单: {len(agg_disc)}")
# Σ商品总金额 vs 300
amt_ge300 = sum(1 for v in agg_amt.values() if round(v,2) >= 300)
amt_lt300 = sum(1 for v in agg_amt.values() if round(v,2) < 300)
w(f"Σ商品总金额>=300: {amt_ge300}  <300: {amt_lt300}")
amt_bucket = Counter()
for v in agg_amt.values():
    rv = round(v,2)
    if rv < 100: amt_bucket["<100"] += 1
    elif rv < 200: amt_bucket["100-200"] += 1
    elif rv < 300: amt_bucket["200-300"] += 1
    elif rv < 400: amt_bucket["300-400"] += 1
    elif rv < 600: amt_bucket["400-600"] += 1
    else: amt_bucket[">=600"] += 1
w("Σ商品总金额分桶:", dict(amt_bucket))
w("政策文本样例:", list(pol_samples))

# ---- 活动明细订单 是否都能在订单明细找到 ----
act_orders = set(agg_disc.keys())
ord_orders = set(order_time_by_no.keys())
missing = act_orders - ord_orders
w(f"\n活动明细订单在订单明细缺失数= {len(missing)}  样例={list(missing)[:5]}")

# ---- 销售明细 覆盖 ----
sig3, sheet3, hdr3, rows3 = read_table(F_SALES)
si = {h: i for i, h in enumerate(hdr3)}
sales_no = set()
for r in rows3:
    no = r[si["单据编号"]].strip()
    if no:
        sales_no.add(no)
w("\n== 销售明细 ==", sig3, sheet3, "rows=", len(rows3), "唯一单据=", len(sales_no))
w("订单明细订单 在销售明细覆盖=", len(ord_orders & sales_no), "/", len(ord_orders))
w("活动明细订单 在销售明细覆盖=", len(act_orders & sales_no), "/", len(act_orders))

out.close()
print("done")
