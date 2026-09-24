# -*- coding: utf-8 -*-
"""只读诊断: XD 履约单里有多少'已完成'订单没有对应 SXD(当前 SXD-中心模型会漏掉).
用户口径(2026-09-24): 以 XD 状态='已完成'结算, 不管是否关联 SXD.
本脚本量化差距 + 打印 XD 文件列(判断能否 XD-驱动核算活动参与).
用法: PYTHONIOENCODING=utf-8 python probe_xd_coverage.py
"""
import os, sys, sqlite3
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
CUTOFF = "2026-09-21 00:00:00"   # calc_date 2026-09-23 的 T-2


def agg_status(ss):
    ss = [s for s in ss if s]
    if not ss: return ""
    if all(s == "已完成" for s in ss): return "已完成"
    unk = [s for s in ss if s not in STATUS_RANK]
    if unk: return unk[0]
    return min(ss, key=lambda s: STATUS_RANK[s])


con = sqlite3.connect(DB); cur = con.cursor()
mX = load_mapping(con, PLATFORM, MAP_XD)
xd = {}   # doc -> dict(statuses, signs, outs, src)
for f in XD_FILES:
    sig, sheet, hdr, rows = read_table(f, header_row=HR)
    ci = ec_col_index(hdr, mX)
    raw_ix = {}
    for i, h in enumerate(hdr):
        if h and h not in raw_ix:
            raw_ix[str(h).strip()] = i   # 首个同名列(综合订单号/下单金额按原始表头名定位)

    def gv(row, ec):
        i = ci.get(ec)
        v = row[i] if (i is not None and i < len(row)) else ""
        return v if v is not None else ""

    def gr(row, rawname):
        i = raw_ix.get(rawname)
        v = row[i] if (i is not None and i < len(row)) else ""
        return v if v is not None else ""

    print("  原始表头:", [h for h in hdr if h])
    print("  ec101映射列(ec->idx):", {k: v for k, v in ci.items()})
    print("  综合订单号原始列idx=", raw_ix.get("综合订单号"), " 下单金额原始列idx=", raw_ix.get("下单金额"))

    for row in rows:
        doc = str(gv(row, "XD单号")).strip()
        if not doc: continue
        o = xd.setdefault(doc, dict(statuses=[], signs=[], outs=[], src=set(),
                                    zonghe=set(), amt=0.0, snow_amt=0.0, pillow=0.0))
        o["statuses"].append(str(gv(row, "履约订单状态")).strip())
        sg = to_datetime_text(gv(row, "完成时间"))
        if sg: o["signs"].append(sg)
        ot = to_datetime_text(gv(row, "出库时间"))
        if ot: o["outs"].append(ot)
        o["src"].add(os.path.basename(f))
        zh = str(gr(row, "综合订单号")).strip()
        if zh: o["zonghe"].add(zh)
        a = to_num(gr(row, "下单金额"))
        if a: o["amt"] += a
        pnm = str(gv(row, "商品名称")).strip()
        rowamt = to_num(gr(row, "下单金额")) or 0.0
        if pnm.startswith("雪碧"):
            o["snow_amt"] += rowamt
        elif pnm == "(赠品)雪碧抱枕":
            o["pillow"] += 1
    del rows

for doc, o in xd.items():
    o["status_agg"] = agg_status(o["statuses"])
    o["completed_at"] = max(o["signs"]) if o["signs"] else (max(o["outs"]) if o["outs"] else "")

# DB 里被 SXD 引用的 XD单号(downstream_order_no)
referenced = set(r[0] for r in cur.execute(
    "SELECT DISTINCT downstream_order_no FROM order_header WHERE dealer_platform_id=2 "
    "AND downstream_order_no IS NOT NULL AND downstream_order_no<>''"))
print("=" * 70)
print("XD 文件 distinct 单据 =", len(xd))
print("DB 中被 SXD 引用的 XD单号(downstream_order_no) =", len(referenced))

all_status = defaultdict(int)
only_status = defaultdict(int)
ref_status = defaultdict(int)
xd_only = []
for doc, o in xd.items():
    all_status[o["status_agg"]] += 1
    if doc in referenced:
        ref_status[o["status_agg"]] += 1
    else:
        only_status[o["status_agg"]] += 1
        xd_only.append((doc, o))

print("\n[全部XD] 状态分布:", dict(all_status))
print("[被SXD引用] 状态分布:", dict(ref_status))
print("[XD-only 无SXD] 状态分布:", dict(only_status))
print("XD-only 合计 =", len(xd_only))

# XD-only 已完成: 释放候选(完成时间<=cutoff) + 来源文件分布
done_only = [(d, o) for d, o in xd_only if o["status_agg"] == "已完成"]
rel = [(d, o) for d, o in done_only if o["completed_at"] and o["completed_at"] <= CUTOFF]
src_dist = defaultdict(int)
for d, o in done_only:
    src_dist[tuple(sorted(o["src"]))] += 1
print("\nXD-only 已完成 =", len(done_only))
print("  其中 完成时间<=cutoff(可释放) =", len(rel))
print("  XD-only已完成 按来源文件:", dict(src_dist))
# 完成时间月份分布
mon = defaultdict(int)
for d, o in done_only:
    mon[(o["completed_at"] or "")[:7]] += 1
print("  XD-only已完成 完成月份分布:", dict(sorted(mon.items())))
print("\n样例 XD-only 已完成(前8): ", [(d, o['completed_at']) for d, o in done_only[:8]])

# ---- XD-only 已完成: 按单据前缀 + 综合订单号是否命中DB里的SXD ----
sxd_nos = set(r[0] for r in cur.execute(
    "SELECT order_no FROM order_header WHERE dealer_platform_id=2"))
prefix_all = defaultdict(int)
prefix_zh_hit = defaultdict(int)     # 综合订单号命中SXD(=连接缺口, SXD其实已在库)
prefix_zh_miss = defaultdict(int)    # 综合订单号不在SXD(=真正缺SXD或非销售单)
prefix_amt = defaultdict(float)
prefix_no_zh = defaultdict(int)      # 无综合订单号
for d, o in done_only:
    p = d[:2]
    prefix_all[p] += 1
    prefix_amt[p] += o["amt"]
    zh = o["zonghe"]
    if not zh:
        prefix_no_zh[p] += 1
    elif zh & sxd_nos:
        prefix_zh_hit[p] += 1
    else:
        prefix_zh_miss[p] += 1
print("\n[XD-only 已完成 按单据前缀]")
for p in sorted(prefix_all, key=lambda k: -prefix_all[k]):
    print(f"  前缀'{p}': 单数={prefix_all[p]}  下单金额合计={round(prefix_amt[p],2)}  "
          f"综合订单号命中SXD={prefix_zh_hit[p]}  未命中={prefix_zh_miss[p]}  无综合订单号={prefix_no_zh[p]}")
tot_hit = sum(prefix_zh_hit.values()); tot_miss = sum(prefix_zh_miss.values()); tot_nozh = sum(prefix_no_zh.values())
print(f"  合计: 综合订单号命中SXD(连接缺口)={tot_hit}  未命中(真缺SXD/非销售)={tot_miss}  无综合订单号={tot_nozh}")

# ---- XD-only 已完成 里的满赠活动参与度(雪碧>=100 / 含抱枕) ----
print("\n[XD-only 已完成 满赠活动参与度]")
for want in ("XD", "TD"):
    sub = [(d, o) for d, o in done_only if d[:2] == want]
    snow100 = [(d, o) for d, o in sub if o["snow_amt"] >= 100]
    pil = [(d, o) for d, o in sub if o["pillow"] > 0]
    snow_any = [(d, o) for d, o in sub if o["snow_amt"] > 0]
    print(f"  前缀'{want}': 单数={len(sub)}  含雪碧行={len(snow_any)}  雪碧下单额>=100(满赠合格)={len(snow100)}  含抱枕赠品={len(pil)}")
    if snow100[:5]:
        print(f"     雪碧>=100样例(doc,雪碧额,抱枕数): {[(d, round(o['snow_amt'],1), o['pillow']) for d,o in snow100[:5]]}")
    if want == "XD" and snow100:
        mz_file = "满赠XD20260819-20260826.xlsx"
        in_mz = [(d, o) for d, o in snow100 if mz_file in o["src"]]
        only_mj = [(d, o) for d, o in snow100 if mz_file not in o["src"]]
        in_mz_pil = [(d, o) for d, o in in_mz if o["pillow"] > 0]
        print(f"     雪碧>=100 来源拆分: 满赠XD窗口(0819-0826)={len(in_mz)} (其中含抱枕={len(in_mz_pil)})  仅满减XD(0826-0908,多在满赠窗口后)={len(only_mj)}")
con.close()
