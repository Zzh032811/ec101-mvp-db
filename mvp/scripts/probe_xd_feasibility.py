# -*- coding: utf-8 -*-
"""只读可行性探针: XD-only 已完成单能否独立建单核算?

回答改造前必须实测的 4 件事(范围 = 仅 XD-only[不被任何 SXD.downstream_order_no 引用] 且
状态聚合=已完成 且 XD 开头[TD 退货排除]):
  (1) 客户桥接命中率: '客户名称|客户助记码' 复合键 → customer.platform_customer_no
  (2) 商品桥接命中率: XD '商品id' → product.platform_product_no
  (3) 满赠门槛金额口径敏感性: 下单金额 vs 销售结算金额 vs 签收金额, 各自 >=100 的合格单数
  (4) 活动窗口时间字段: '单据时间' vs '完成时间' 落在满赠窗口[0819,0827)的差异
绝不写库。
"""
import os
import sys
import sqlite3
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from readers import read_table, to_num, to_datetime_text
from std_mapping import load_mapping, ec_col_index

MVP = r"D:\Peggy zhan\智能EC101\数据底座\第三阶段数据库设计\mvp"
BASE = r"D:\Peggy zhan\智能EC101\数据底座\第三阶段数据库设计\舟谱-羿柏-试点"
DB = os.path.join(MVP, "ec101_mvp.db")
PLATFORM, MAP_XD, HR = "舟谱", "订单履约", 4
XD_FILES = [
    os.path.join(BASE, "满减", "舟谱-羿柏-订单明细-XD-20260826-20260908.xlsx"),
    os.path.join(BASE, "满赠", "满赠XD20260819-20260826.xlsx"),
]
STATUS_RANK = {"待审核": 0, "待出库": 1, "待入库": 2, "待签收": 3, "已完成": 4}
MZ_START, MZ_END = "2026-08-19 00:00:00", "2026-08-27 00:00:00"
GIFT = "(赠品)雪碧抱枕"
SNOW = "雪碧"


def agg_status(ss):
    ss = [s for s in ss if s]
    if not ss:
        return ""
    if all(s == "已完成" for s in ss):
        return "已完成"
    unk = [s for s in ss if s not in STATUS_RANK]
    if unk:
        return unk[0]
    return min(ss, key=lambda s: STATUS_RANK[s])


con = sqlite3.connect(DB)
cur = con.cursor()
DP = cur.execute("SELECT dealer_platform_id FROM dealer_platform WHERE platform_name=? AND dealer_name=?",
                 (PLATFORM, "羿柏")).fetchone()[0]
referenced = set(r[0] for r in cur.execute(
    "SELECT DISTINCT downstream_order_no FROM order_header WHERE dealer_platform_id=? "
    "AND downstream_order_no IS NOT NULL", (DP,)).fetchall())
cust_comp = set(r[0] for r in cur.execute(
    "SELECT platform_customer_no FROM customer WHERE dealer_platform_id=?", (DP,)).fetchall())
prod_no = set(r[0] for r in cur.execute(
    "SELECT platform_product_no FROM product WHERE dealer_platform_id=? "
    "AND platform_product_no IS NOT NULL", (DP,)).fetchall())
con.close()
print(f"DP={DP}  被SXD引用的XD单号={len(referenced)}  客户复合键={len(cust_comp)}  商品编号={len(prod_no)}")

mX = None
xd = {}
con = sqlite3.connect(DB)
mX = load_mapping(con, PLATFORM, MAP_XD)
con.close()

for f in XD_FILES:
    sig, sheet, hdr, rows = read_table(f, header_row=HR)
    ci = ec_col_index(hdr, mX)
    raw_ix = {}
    for i, h in enumerate(hdr):
        if h and str(h).strip() not in raw_ix:
            raw_ix[str(h).strip()] = i

    def gv(row, ec, ci=ci):
        i = ci.get(ec)
        v = row[i] if (i is not None and i < len(row)) else ""
        return v if v is not None else ""

    def gr(row, name, raw_ix=raw_ix):
        i = raw_ix.get(name)
        v = row[i] if (i is not None and i < len(row)) else ""
        return v if v is not None else ""

    for row in rows:
        doc = str(gv(row, "XD单号")).strip()
        if not doc:
            continue
        o = xd.get(doc)
        if o is None:
            o = xd[doc] = dict(statuses=[], signs=[], cname="", mnem="", doctime="",
                               pids=set(), snow_xd=0.0, snow_st=0.0, snow_sg=0.0, pillow=0.0)
        o["statuses"].append(str(gv(row, "履约订单状态")).strip())
        sg = to_datetime_text(gv(row, "完成时间"))
        if sg:
            o["signs"].append(sg)
        if not o["cname"]:
            o["cname"] = str(gv(row, "客户名称")).strip()
        if not o["mnem"]:
            o["mnem"] = str(gv(row, "客户助记码")).strip()
        dt = to_datetime_text(gr(row, "单据时间"))
        if dt and not o["doctime"]:
            o["doctime"] = dt
        pid = str(gv(row, "商品id")).strip()
        if pid.endswith(".0"):
            pid = pid[:-2]
        if pid:
            o["pids"].add(pid)
        nm = str(gv(row, "商品名称")).strip()
        a_xd = to_num(gr(row, "下单金额")) or 0.0
        a_st = to_num(gr(row, "销售结算金额")) or 0.0
        a_sg = to_num(gr(row, "签收金额")) or 0.0
        if nm.startswith(SNOW):
            o["snow_xd"] += a_xd
            o["snow_st"] += a_st
            o["snow_sg"] += a_sg
        elif nm == GIFT:
            o["pillow"] += 1
    del rows

# ---- 筛选 XD-only 已完成 XD 开头 ----
target = {}
for doc, o in xd.items():
    if doc in referenced:
        continue
    if agg_status(o["statuses"]) != "已完成":
        continue
    if not doc.startswith("XD"):
        continue
    o["completed_at"] = max(o["signs"]) if o["signs"] else ""
    target[doc] = o

N = len(target)
print("\n" + "=" * 70)
print(f"XD-only 已完成 XD开头 = {N} 单 (TD退货已排除)")

# (1) 客户桥接
cust_hit = [d for d, o in target.items() if f"{o['cname']}|{o['mnem']}" in cust_comp]
cust_miss = [d for d, o in target.items() if f"{o['cname']}|{o['mnem']}" not in cust_comp]
blank_cust = [d for d in cust_miss if not target[d]["cname"]]
print(f"\n(1) 客户桥接 '客户名称|客户助记码' → customer.platform_customer_no")
print(f"    命中={len(cust_hit)} ({len(cust_hit)*100.0/N:.1f}%)  未命中={len(cust_miss)}  其中客户名为空={len(blank_cust)}")
miss_s = [(target[d]['cname'], target[d]['mnem']) for d in cust_miss[:8]]
print(f"    未命中样例(名称,助记码): {miss_s}")

# (2) 商品桥接
all_hit = some_hit = none_hit = 0
for d, o in target.items():
    if not o["pids"]:
        none_hit += 1
        continue
    h = sum(1 for p in o["pids"] if p in prod_no)
    if h == len(o["pids"]):
        all_hit += 1
    elif h > 0:
        some_hit += 1
    else:
        none_hit += 1
print(f"\n(2) 商品桥接 XD '商品id' → product.platform_product_no")
print(f"    全命中单={all_hit}  部分命中单={some_hit}  零命中/无id单={none_hit}")

# (3) 满赠门槛金额口径敏感性
q_xd = {d for d, o in target.items() if o["snow_xd"] >= 100}
q_st = {d for d, o in target.items() if o["snow_st"] >= 100}
q_sg = {d for d, o in target.items() if o["snow_sg"] >= 100}
pillow_docs = {d for d, o in target.items() if o["pillow"] > 0}
print(f"\n(3) 满赠合格(雪碧金额>=100) 三口径对比  [含雪碧行单={sum(1 for o in target.values() if o['snow_xd']>0 or o['snow_st']>0 or o['snow_sg']>0)}]")
print(f"    下单金额>=100   = {len(q_xd)}")
print(f"    销售结算金额>=100 = {len(q_st)}")
print(f"    签收金额>=100   = {len(q_sg)}")
print(f"    三口径交集       = {len(q_xd & q_st & q_sg)}   仅下单命中(结算/签收<100) = {len(q_xd - q_st - q_sg)}")
print(f"    实发抱枕单(pillow>0) = {len(pillow_docs)}   抱枕单中下单额>=100 = {len(pillow_docs & q_xd)}")

# (4) 活动窗口时间字段
def in_win(t):
    return bool(t) and MZ_START <= t < MZ_END

doc_in = {d for d, o in target.items() if in_win(o["doctime"])}
cmp_in = {d for d, o in target.items() if in_win(o["completed_at"])}
print(f"\n(4) 活动窗口[0819,0827) 时间字段差异")
print(f"    按'单据时间'在窗口 = {len(doc_in)}")
print(f"    按'完成时间'在窗口 = {len(cmp_in)}")
print(f"    两字段都在窗口     = {len(doc_in & cmp_in)}   仅单据时间在 = {len(doc_in - cmp_in)}   仅完成时间在 = {len(cmp_in - doc_in)}")
print(f"    满赠合格(下单口径)中: 按单据时间在窗口={len(q_xd & doc_in)}  按完成时间在窗口={len(q_xd & cmp_in)}")
print(f"    无单据时间的单     = {sum(1 for o in target.values() if not o['doctime'])}")
print("=" * 70)
