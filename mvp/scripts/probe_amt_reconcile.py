# -*- coding: utf-8 -*-
"""只读对账: 复现 §6.5 的 XD-only 单据集, 把 下单金额 按 状态/前缀/来源文件 拆开,
直接对齐 probe_xd_coverage 的 1,317,674.34(XD前缀已完成). 绝不写库.
目的: 解释 §6.5 DRY 报的 4,324,732.33 与 coverage 的 3.3x 差距究竟来自何处.
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


def agg_status(ss):
    ss = [s for s in ss if s]
    if not ss: return ""
    if all(s == "已完成" for s in ss): return "已完成"
    unk = [s for s in ss if s not in STATUS_RANK]
    if unk: return unk[0]
    return min(ss, key=lambda s: STATUS_RANK[s])


con = sqlite3.connect(DB); cur = con.cursor()
mX = load_mapping(con, PLATFORM, MAP_XD)
DP = cur.execute("SELECT dealer_platform_id FROM dealer_platform WHERE platform_name=? AND dealer_name=?",
                 (PLATFORM, "羿柏")).fetchone()[0]
referenced = set(r[0] for r in cur.execute(
    "SELECT DISTINCT downstream_order_no FROM order_header WHERE dealer_platform_id=? "
    "AND downstream_order_no IS NOT NULL AND downstream_order_no<>''", (DP,)).fetchall())
con.close()

# ---- 复现 §6.5: 逐文件读, 跨文件按 doc 去重(首次为准), 排除 referenced/TD/测试 ----
seen = set()                 # 已处理 doc(跨文件去重)
amt_by_status = defaultdict(float)
amt_by_prefix = defaultdict(float)
cnt_by_status = defaultdict(int)
doc_amt = {}                 # doc -> 累计下单金额(仅首次文件)
doc_status = {}
per_file_rows = defaultdict(int)
amt_col_idx = {}

for f in XD_FILES:
    sig, sheet, hdr, rows = read_table(f, header_row=HR)
    ci = ec_col_index(hdr, mX)
    raw_ix = {}
    for i, h in enumerate(hdr):
        if h and str(h).strip() not in raw_ix:
            raw_ix[str(h).strip()] = i
    amt_col_idx[os.path.basename(f)] = raw_ix.get("下单金额")

    def gv2(row, ec, ci=ci):
        i = ci.get(ec); v = row[i] if (i is not None and i < len(row)) else ""
        return v if v is not None else ""

    def gr2(row, name, raw_ix=raw_ix):
        i = raw_ix.get(name); v = row[i] if (i is not None and i < len(row)) else ""
        return v if v is not None else ""

    doc_rows = defaultdict(list)
    for row in rows:
        doc = str(gv2(row, "XD单号")).strip()
        if doc:
            doc_rows[doc].append(row)
    del rows

    for doc, drows in doc_rows.items():
        if doc in referenced: continue
        if doc.startswith("TD"): continue
        statuses = []; cname = ""
        for row in drows:
            if not cname: cname = str(gv2(row, "客户名称")).strip()
            statuses.append(str(gv2(row, "履约订单状态")).strip())
        if cname == "测试": continue
        st = agg_status(statuses)
        if doc in seen:
            # 跨文件重复: §6.5 会 continue(不重复计金额). 这里也跳过, 但记录重复次数
            per_file_rows["DUP_DOC"] += 1
            continue
        seen.add(doc)
        a_doc = 0.0
        for row in drows:
            a = to_num(gr2(row, "下单金额"))
            if a: a_doc += a
        doc_amt[doc] = a_doc
        doc_status[doc] = st
        amt_by_status[st or "(空)"] += a_doc
        amt_by_prefix[doc[:2]] += a_doc
        cnt_by_status[st or "(空)"] += 1

print("下单金额原始列idx(每文件):", amt_col_idx)
print("\n== §6.5 复现: XD-only 非TD 非测试 distinct 单据 ==")
print("distinct doc =", len(doc_amt))
print("下单金额合计 =", round(sum(doc_amt.values()), 2))
print("\n按状态拆:")
for st in sorted(amt_by_status, key=lambda k: -amt_by_status[k]):
    print(f"  {st:8} 单数={cnt_by_status[st]:5}  下单金额={round(amt_by_status[st],2):>15}")
print("\n按前缀拆:")
for p in sorted(amt_by_prefix, key=lambda k: -amt_by_prefix[k]):
    print(f"  '{p}' 下单金额={round(amt_by_prefix[p],2)}")

# ---- 直接对齐 coverage: 仅 XD前缀 + 已完成 ----
cov_set = [(d, a) for d, a in doc_amt.items() if d.startswith("XD") and doc_status[d] == "已完成"]
print("\n== 对齐 coverage 口径: XD前缀 且 已完成 ==")
print("  单数 =", len(cov_set), "  下单金额合计 =", round(sum(a for _, a in cov_set), 2))
print("  (coverage 报: 单数=2508  金额=1317674.34)")

# ---- top 金额单据(看是否有异常大单/疑似 doc级重复) ----
top = sorted(doc_amt.items(), key=lambda x: -x[1])[:10]
print("\n下单金额 top10 单据:")
for d, a in top:
    print(f"  {d}  status={doc_status[d]}  amt={round(a,2)}")
print("\n跨文件重复doc次数(被跳过, 未计金额):", per_file_rows["DUP_DOC"])
