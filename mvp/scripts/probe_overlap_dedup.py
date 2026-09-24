# -*- coding: utf-8 -*-
"""只读: 跨文件重叠单据(同时在 满减XD 与 满赠XD 出现)是否为'同单据重复导出'?
若是重复(两文件行集相同) -> §6.5 首次为准的去重安全, 不丢行/不误判状态.
若是互补(行集不同)       -> 首次为准会丢行, 需改为跨文件合并行.
对每个重叠 doc 比较: 行数 / 商品id多重集 / 状态多重集 / 下单金额合计. 绝不写库.
"""
import os, sys, sqlite3
from collections import defaultdict, Counter
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from readers import read_table, to_num
from std_mapping import load_mapping, ec_col_index

MVP = r"D:\Peggy zhan\智能EC101\数据底座\第三阶段数据库设计\mvp"
BASE = r"D:\Peggy zhan\智能EC101\数据底座\第三阶段数据库设计\舟谱-羿柏-试点"
DB = os.path.join(MVP, "ec101_mvp.db")
PLATFORM, MAP_XD, HR = "舟谱", "订单履约", 4
XD_FILES = [
    os.path.join(BASE, "满减", "舟谱-羿柏-订单明细-XD-20260826-20260908.xlsx"),
    os.path.join(BASE, "满赠", "满赠XD20260819-20260826.xlsx"),
]

con = sqlite3.connect(DB); cur = con.cursor()
mX = load_mapping(con, PLATFORM, MAP_XD)
DP = cur.execute("SELECT dealer_platform_id FROM dealer_platform WHERE platform_name=? AND dealer_name=?",
                 (PLATFORM, "羿柏")).fetchone()[0]
referenced = set(r[0] for r in cur.execute(
    "SELECT DISTINCT downstream_order_no FROM order_header WHERE dealer_platform_id=? "
    "AND downstream_order_no IS NOT NULL AND downstream_order_no<>''", (DP,)).fetchall())
con.close()

# per (file, doc) -> signature
sig = defaultdict(dict)   # doc -> {file_idx: dict(nrows, pids, statuses, amt)}
for fi, f in enumerate(XD_FILES):
    s, sheet, hdr, rows = read_table(f, header_row=HR)
    ci = ec_col_index(hdr, mX)
    raw_ix = {}
    for i, h in enumerate(hdr):
        if h and str(h).strip() not in raw_ix:
            raw_ix[str(h).strip()] = i

    def gv2(row, ec, ci=ci):
        i = ci.get(ec); v = row[i] if (i is not None and i < len(row)) else ""
        return v if v is not None else ""

    def gr2(row, name, raw_ix=raw_ix):
        i = raw_ix.get(name); v = row[i] if (i is not None and i < len(row)) else ""
        return v if v is not None else ""

    for row in rows:
        doc = str(gv2(row, "XD单号")).strip()
        if not doc: continue
        d = sig[doc].setdefault(fi, dict(nrows=0, pids=[], statuses=[], amt=0.0))
        d["nrows"] += 1
        pid = str(gv2(row, "商品id")).strip()
        d["pids"].append(pid)
        d["statuses"].append(str(gv2(row, "履约订单状态")).strip())
        a = to_num(gr2(row, "下单金额"))
        if a: d["amt"] += a
    del rows

overlap = [doc for doc, m in sig.items() if len(m) == 2]
print(f"重叠单据(同时在两文件) distinct = {len(overlap)}")
print(f"  其中 被SXD引用(§6.5已排除) = {sum(1 for d in overlap if d in referenced)}")
cand = [d for d in overlap if d not in referenced and d.startswith("XD")]
print(f"  XD-only 且 XD前缀(§6.5会处理) = {len(cand)}")

identical = diff_rows = diff_pids = diff_status = diff_amt = 0
examples = []
for doc in cand:
    a, b = sig[doc][0], sig[doc][1]
    same_n = a["nrows"] == b["nrows"]
    same_pid = Counter(a["pids"]) == Counter(b["pids"])
    same_st = Counter(a["statuses"]) == Counter(b["statuses"])
    same_amt = abs(a["amt"] - b["amt"]) < 0.01
    if same_n and same_pid and same_st and same_amt:
        identical += 1
    else:
        if not same_n: diff_rows += 1
        if not same_pid: diff_pids += 1
        if not same_st: diff_status += 1
        if not same_amt: diff_amt += 1
        if len(examples) < 6:
            examples.append((doc, a["nrows"], b["nrows"], round(a["amt"],1), round(b["amt"],1),
                             Counter(a["statuses"]), Counter(b["statuses"])))

print(f"\n两文件行集完全相同(重复导出, 去重安全) = {identical}")
print(f"不一致: 行数不同={diff_rows}  商品id不同={diff_pids}  状态不同={diff_status}  金额不同={diff_amt}")
print("不一致样例(doc, f0行数, f1行数, f0金额, f1金额, f0状态, f1状态):")
for e in examples:
    print("   ", e)
