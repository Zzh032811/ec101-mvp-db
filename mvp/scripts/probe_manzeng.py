# -*- coding: utf-8 -*-
"""满赠接入前勘察: 格式/表头/行数 + 活动明细结构 + 赠品口径."""
import os, sys
from collections import Counter, defaultdict
sys.path.insert(0, os.path.dirname(__file__))
from readers import read_table, to_num, to_datetime_text

BASE = r"D:\Peggy zhan\智能EC101\数据底座\第三阶段数据库设计\快马-兴路强-试点"
F_ORDER = os.path.join(BASE, "满赠", "快马-兴路强-满赠-订单明细-20260819-20260831.xls")
F_ACT   = os.path.join(BASE, "满赠", "快马-兴路强-满赠-活动明细-20260819-20260831.xls")
F_SALES = os.path.join(BASE, "满赠", "快马-兴路强-满赠-销售明细-20260819-20260831.xls")

out = open(os.path.join(BASE, "..", "mvp", "probe_manzeng.txt"), "w", encoding="utf-8")
def w(*a):
    print(*a, file=out)

for tag, f in [("订单明细", F_ORDER), ("活动明细", F_ACT), ("销售明细", F_SALES)]:
    sig, sheet, hdr, rows = read_table(f)
    w(f"\n===== {tag} ===== sig={sig} sheet={sheet} rows={len(rows)} ncols={len(hdr)}")
    w("header:", " | ".join(hdr))
    if rows:
        w("row1:", " | ".join(str(c) for c in rows[0]))
    if tag == "订单明细":
        ci = {h: i for i, h in enumerate(hdr)}
        st = Counter()
        nos = set()
        for r in rows:
            no = (r[ci["订单编号"]] if "订单编号" in ci and ci["订单编号"] < len(r) else "").strip()
            if no:
                nos.add(no)
                st[(r[ci["订单状态"]] if ci["订单状态"] < len(r) else "").strip()] += 1
        w("唯一订单=", len(nos), " 状态分布(行):", dict(st))
    if tag == "活动明细":
        w("--- 活动明细 全部行(前30) ---")
        for r in rows[:30]:
            w("  ", " | ".join(str(c) for c in r))

out.close()
print("done")
