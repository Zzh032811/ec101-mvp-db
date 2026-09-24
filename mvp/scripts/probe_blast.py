# -*- coding: utf-8 -*-
"""证实 readers.py 的 OOXML 正则 bug 并量化波及范围.
对比 错误正则(现 readers.py) vs 修正正则(自闭合分支前置) 在所有 .xlsx 上的逐行差异.
并给出 2 个目标客户在修正解析下的真实 客户类型/客户等级/联系电话 等值.
"""
import os, sys, re, glob, zipfile, html as H

BASE = r"D:\Peggy zhan\智能EC101\数据底座\第三阶段数据库设计\快马-兴路强-试点"
REPORT = os.path.join(os.path.dirname(__file__), "probe_blast.txt")
rep = open(REPORT, "w", encoding="utf-8")
def w(*a):
    s = " ".join(str(x) for x in a); print(s); rep.write(s + "\n")

RE_BAD  = r'(<c\b[^>]*>.*?</c>|<c\b[^>]*/>)'   # 现 readers.py: 自闭合分支在后 -> 吞并
RE_GOOD = r'(<c\b[^>]*/>|<c\b[^>]*>.*?</c>)'   # 修正: 自闭合分支前置

def col_of(ref):
    letters = ''.join(ch for ch in ref if ch.isalpha())
    idx = 0
    for ch in letters: idx = idx*26 + (ord(ch.upper())-ord('A')+1)
    return idx-1

def load_shared(z):
    ss = []
    if 'xl/sharedStrings.xml' in z.namelist():
        s = z.read('xl/sharedStrings.xml').decode('utf-8')
        for si in re.findall(r'<si>(.*?)</si>', s, re.S):
            ss.append(H.unescape(''.join(re.findall(r'<t[^>]*>(.*?)</t>', si, re.S))))
    return ss

def first_sheet_xml(z):
    wb = z.read('xl/workbook.xml').decode('utf-8')
    sheets = re.findall(r'<sheet[^>]*name="([^"]+)"[^>]*r:id="(rId\d+)"', wb)
    rels = z.read('xl/_rels/workbook.xml.rels').decode('utf-8')
    rid2t = dict(re.findall(r'Id="(rId\d+)"[^>]*Target="([^"]+)"', rels))
    tgt = rid2t.get(sheets[0][1], '').lstrip('/')
    if not tgt.startswith('xl/'): tgt = 'xl/' + tgt
    return sheets[0][0], z.read(tgt).decode('utf-8')

def parse_cells(rbody, ss, rex):
    """按给定正则切格 -> {col: value}"""
    out = {}
    for c in re.findall(rex, rbody, re.S):
        gt = c.index('>')
        tag = c[:gt+1]
        refm = re.search(r'\br="([A-Za-z]+\d+)"', tag)
        if not refm: continue
        col = col_of(refm.group(1))
        t = re.search(r'\bt="(\w+)"', tag); t = t.group(1) if t else ''
        v = re.search(r'<v>(.*?)</v>', c, re.S); v = v.group(1) if v else ''
        ist = re.search(r'<t[^>]*>(.*?)</t>', c, re.S)
        if t=='s' and v!='': val = ss[int(v)]
        elif t=='inlineStr' and ist: val = H.unescape(ist.group(1))
        else: val = H.unescape(v)
        out[col] = val
    return out

def rowlist(d, maxcol):
    return [d.get(i, '') for i in range(maxcol)]

# ---- 目标客户真值 (customer master) ----
F_CUST = os.path.join(BASE, "User-202609221722.xlsx")
z = zipfile.ZipFile(F_CUST); ss = load_shared(z); shname, x = first_sheet_xml(z)
w("== 0. 共享字符串抽样 (被错配的字面量索引对应的真值) ==")
for i in (29, 98, 102, 103, 37, 31, 58, 34, 36, 38, 100, 101):
    w(f"  ss[{i}] = {ss[i]!r}" if i < len(ss) else f"  ss[{i}] = <越界>")

HDR = None
rows = list(re.finditer(r'<row[^>]*>(.*?)</row>', x, re.S))
# 取表头(第一行)确定列数
hdr_bad = parse_cells(rows[0].group(1), ss, RE_BAD)
maxcol = max(hdr_bad.keys())+1 if hdr_bad else 26
HDR = [hdr_bad.get(i,'') for i in range(maxcol)]
w("\n== 1. 表头(修正解析) ==", HDR)

TARGETS = {"WX-00000000000007507909":"惠乐惠便利店", "WX-00000000000007507908":"生鲜宜购(RTM)（0098"}
w("\n== 2. 2个目标客户: 错误解析 vs 修正解析 ==")
for rm in rows[1:]:
    body = rm.group(1)
    good = parse_cells(body, ss, RE_GOOD)
    no = good.get(1, '')
    if no in TARGETS:
        bad = parse_cells(body, ss, RE_BAD)
        w(f"\n  --- {no} ({TARGETS[no]}) ---")
        w(f"  {'列':<12}{'错误(现库)':<22}{'修正(真值)'}")
        for i in range(maxcol):
            bv = bad.get(i,''); gv = good.get(i,'')
            flag = '  <<< 不一致' if bv != gv else ''
            if bv != gv or HDR[i] in ('客户类型','客户等级','联系电话','客户标签','客户区域','可用积分','状态','添加时间','备注','上级分销商','起订金额'):
                w(f"  {HDR[i]:<12}{bv!r:<22}{gv!r}{flag}")
z.close()

# ---- 波及范围: 所有 .xlsx ----
w("\n\n== 3. 波及范围: 每个 .xlsx 文件 错误 vs 修正 的逐行差异 ==")
xlsx = sorted(glob.glob(os.path.join(BASE, "**", "*.xlsx"), recursive=True))
for f in xlsx:
    try:
        z = zipfile.ZipFile(f); ss = load_shared(z); shname, x = first_sheet_xml(z)
    except Exception as e:
        w(f"  [跳过] {os.path.basename(f)}: {e}"); continue
    rws = list(re.finditer(r'<row[^>]*>(.*?)</row>', x, re.S))
    if not rws:
        w(f"  [空] {os.path.basename(f)}"); z.close(); continue
    diff_rows = 0; total = len(rws)-1; examples = []
    for rm in rws[1:]:
        body = rm.group(1)
        b = parse_cells(body, ss, RE_BAD); g = parse_cells(body, ss, RE_GOOD)
        # 只比较两解析都覆盖到的列范围
        mc = max((max(b.keys(), default=-1), max(g.keys(), default=-1)))+1
        bl = [b.get(i,'') for i in range(mc)]; gl = [g.get(i,'') for i in range(mc)]
        if bl != gl:
            diff_rows += 1
            if len(examples) < 2:
                # 找出首个不一致列
                fd = next((i for i in range(mc) if bl[i]!=gl[i]), None)
                examples.append((rm.start(), fd, bl[fd] if fd is not None else None, gl[fd] if fd is not None else None))
    pct = (diff_rows/total*100) if total else 0
    w(f"\n  文件: {os.path.relpath(f, BASE)}")
    w(f"    sheet={shname}  数据行={total}  受影响行={diff_rows} ({pct:.1f}%)")
    for ex in examples:
        w(f"    例: 首个错位列#{ex[1]}  错误={ex[2]!r}  修正={ex[3]!r}")
    z.close()
rep.close()
