# -*- coding: utf-8 -*-
"""满赠勘察2: 赠品行证据 / 赠品单价 / 限购1校验 / 活动订单覆盖与状态."""
import os, sys
from collections import Counter, defaultdict
sys.path.insert(0, os.path.dirname(__file__))
from readers import read_table, to_num, to_datetime_text

BASE = r"D:\Peggy zhan\智能EC101\数据底座\第三阶段数据库设计\快马-兴路强-试点"
F_ORDER = os.path.join(BASE, "满赠", "快马-兴路强-满赠-订单明细-20260819-20260831.xls")
F_ACT   = os.path.join(BASE, "满赠", "快马-兴路强-满赠-活动明细-20260819-20260831.xls")
F_PROD  = os.path.join(BASE, "Product2026091410431769689.xlsx")
GIFT_NO = "348721357"

out = open(os.path.join(BASE, "..", "mvp", "probe_manzeng2.txt"), "w", encoding="utf-8")
def w(*a):
    print(*a, file=out)

# ---- 订单明细: 赠品行 ----
sig, sheet, hdr, rows = read_table(F_ORDER)
ci = {h: i for i, h in enumerate(hdr)}
def g(r, name):
    i = ci.get(name)
    return r[i].strip() if i is not None and i < len(r) else ""
gift_lines = []
order_status = {}
order_time = {}
order_cust = {}
for r in rows:
    no = g(r, "订单编号")
    if not no:
        continue
    if no not in order_status:
        order_status[no] = g(r, "订单状态"); order_time[no] = to_datetime_text(g(r, "下单时间")); order_cust[no] = g(r, "客户编号")
    if g(r, "商品编号") == GIFT_NO or "抱枕" in g(r, "商品名称"):
        gift_lines.append((no, g(r, "商品编号"), g(r, "商品名称"), g(r, "订货数量"), g(r, "优惠前金额"), g(r, "优惠金额"), g(r, "订货金额"), g(r, "订单状态")))
w("== 赠品行(订单明细) ==", len(gift_lines), " 涉及订单=", len(set(x[0] for x in gift_lines)))
for x in gift_lines[:12]:
    w("   ", x)
gift_per_order = Counter(x[0] for x in gift_lines)
w("每单赠品行数分布:", dict(Counter(gift_per_order.values())))

# ---- 商品主数据: 赠品单价 ----
sigp, shp, hp, rp = read_table(F_PROD)
pi = {h: i for i, h in enumerate(hp)}
for r in rp:
    if (r[pi["商品编号"]] if pi["商品编号"] < len(r) else "").strip() == GIFT_NO:
        w("\n== 商品主数据 赠品 ==", {k: (r[pi[k]] if pi[k] < len(r) else "") for k in
           ["商品编号","商品名称","单位","状态","成本价","市场价","批发价1","实际库存","条形码"]})
        break
else:
    w("\n== 商品主数据 赠品 == 未找到 348721357")

# ---- 活动明细 ----
siga, sha, ha, ra = read_table(F_ACT)
ai = {h: i for i, h in enumerate(ha)}
agg_amt = defaultdict(float); lines = Counter()
for r in ra:
    no = (r[ai["订单号"]] if ai["订单号"] < len(r) else "").strip()
    if not no: continue
    agg_amt[no] += to_num(r[ai["商品总金额"]]) or 0.0
    lines[no] += 1
w("\n== 活动明细 == 唯一订单=", len(agg_amt), " 行=", len(ra))
ge100 = sum(1 for v in agg_amt.values() if round(v,2) >= 100); lt100 = sum(1 for v in agg_amt.values() if round(v,2) < 100)
w("Σ商品金额>=100:", ge100, " <100:", lt100)
# 覆盖 + 状态
miss = [no for no in agg_amt if no not in order_status]
w("活动订单不在订单明细:", len(miss), miss[:5])
stc = Counter(order_status.get(no, "?") for no in agg_amt)
w("活动订单状态分布:", dict(stc))
# 限购1: 每客户活动订单数
cust_orders = Counter(order_cust.get(no, "?") for no in agg_amt)
multi = {c: n for c, n in cust_orders.items() if n > 1}
w("客户活动订单数>1 (限购1校验):", len(multi), list(multi.items())[:10])
# 赠品行订单 vs 活动明细订单
gift_orders = set(gift_per_order.keys()); act_orders = set(agg_amt.keys())
w("赠品行订单=", len(gift_orders), " 活动明细订单=", len(act_orders),
  " 交集=", len(gift_orders & act_orders), " 仅赠品行=", len(gift_orders - act_orders), " 仅活动明细=", len(act_orders - gift_orders))
w("仅活动明细(无赠品行)样例:", list(act_orders - gift_orders)[:8])
w("仅赠品行(不在活动明细)样例:", list(gift_orders - act_orders)[:8])

out.close()
print("done")
