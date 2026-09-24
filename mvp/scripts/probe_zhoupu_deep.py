# -*- coding: utf-8 -*-
"""只读深挖: 舟谱文件真实表头定位. 每个文件 dump 前 8 行原始内容, 找到真列头行."""
import os, sys, glob
sys.path.insert(0, os.path.dirname(__file__))
from readers import read_table

ROOT = r"D:\Peggy zhan\智能EC101\数据底座\第三阶段数据库设计"
ZP   = os.path.join(ROOT, "舟谱-羿柏-试点")
OUT  = os.path.join(ROOT, "mvp", "scripts", "probe_zhoupu_deep.txt")

rep = open(OUT, "w", encoding="utf-8")
def w(*a):
    s = " ".join(str(x) for x in a); print(s); rep.write(s + "\n")

for path in sorted(glob.glob(os.path.join(ZP, "**", "*.xls*"), recursive=True)):
    if os.path.basename(path).startswith("~$"):
        continue
    rel = os.path.relpath(path, ZP)
    w("\n" + "="*70)
    w(f"### {rel}")
    try:
        sig, sheet, header, rows = read_table(path)
    except Exception as e:
        w(f"  !! 读取失败: {type(e).__name__}: {e}")
        continue
    w(f"  格式={sig} sheet={sheet} (read_table默认把第1行当表头)")
    w(f"  [伪表头/第1行] {header}")
    for i, r in enumerate(rows[:7]):
        ncol = len(r) if r else 0
        w(f"  [第{i+2}行, {ncol}列] {r}")
w("\n[done] -> " + OUT)
rep.close()
