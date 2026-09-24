# -*- coding: utf-8 -*-
"""只读勘察: 舟谱-羿柏 vs 兴路强 同类文件的表头/行数/首行样例对照.
不写库, 不改任何文件. 用 readers.read_table (按魔数判格式).
输出到 UTF-8 文件, 避开 GBK 控制台乱码.
"""
import os, sys, glob
sys.path.insert(0, os.path.dirname(__file__))
from readers import read_table

ROOT = r"D:\Peggy zhan\智能EC101\数据底座\第三阶段数据库设计"
ZP   = os.path.join(ROOT, "舟谱-羿柏-试点")
XLQ  = os.path.join(ROOT, "快马-兴路强-试点")
OUT  = os.path.join(ROOT, "mvp", "scripts", "probe_zhoupu_headers.txt")

rep = open(OUT, "w", encoding="utf-8")
def w(*a):
    s = " ".join(str(x) for x in a); print(s); rep.write(s + "\n")

def dump(path, max_rows=1):
    try:
        sig, sheet, header, rows = read_table(path)
    except Exception as e:
        w(f"  !! 读取失败: {type(e).__name__}: {e}")
        return
    w(f"  格式={sig}  sheet={sheet}  表头列数={len(header) if header else 0}  数据行数={len(rows)}")
    w(f"  表头: {header}")
    for i, r in enumerate(rows[:max_rows]):
        w(f"  样例[{i}]: {r}")

def walk(base, title):
    w("\n" + "="*80)
    w(f"### {title}: {base}")
    w("="*80)
    if not os.path.isdir(base):
        w("  目录不存在"); return
    for path in sorted(glob.glob(os.path.join(base, "**", "*"), recursive=True)):
        if os.path.isfile(path) and path.lower().endswith((".xls", ".xlsx")):
            rel = os.path.relpath(path, base)
            w(f"\n-- {rel}")
            dump(path)

walk(XLQ, "兴路强(已接入,作为基准)")
walk(ZP,  "舟谱-羿柏(待接入)")
w("\n[done] 输出 -> " + OUT)
rep.close()
