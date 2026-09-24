# -*- coding: utf-8 -*-
"""终极核查: 直接看 User-202609221722.xlsx 里这2个客户行的原始XML字节; 并列出目录内所有客户主数据候选文件."""
import os, sys, zipfile, re, html as H, glob
sys.path.insert(0, os.path.dirname(__file__))

BASE = r"D:\Peggy zhan\智能EC101\数据底座\第三阶段数据库设计\快马-兴路强-试点"
F    = os.path.join(BASE, "User-202609221722.xlsx")
REPORT = os.path.join(os.path.dirname(__file__), "probe_rawxml.txt")
TARGETS = ["WX-00000000000007507909", "WX-00000000000007507908"]

rep = open(REPORT, "w", encoding="utf-8")
def w(*a):
    s = " ".join(str(x) for x in a); print(s); rep.write(s + "\n")

# ---- 0. 目录内所有可能的客户主数据文件 ----
w("== 0. 试点目录内 User*/客户* 候选文件 ==")
for p in sorted(glob.glob(os.path.join(BASE, "**", "*.xls*"), recursive=True)):
    nm = os.path.basename(p)
    if nm.lower().startswith("user") or "客户" in nm:
        w(f"  {p}  ({os.path.getsize(p)} bytes)")

# ---- 1. 打开 xlsx, 定位 客户列表 sheet 的 xml ----
z = zipfile.ZipFile(F)
ss = []
if 'xl/sharedStrings.xml' in z.namelist():
    s = z.read('xl/sharedStrings.xml').decode('utf-8')
    for si in re.findall(r'<si>(.*?)</si>', s, re.S):
        txt = ''.join(re.findall(r'<t[^>]*>(.*?)</t>', si, re.S))
        ss.append(H.unescape(txt))
wb = z.read('xl/workbook.xml').decode('utf-8')
sheets = re.findall(r'<sheet[^>]*name="([^"]+)"[^>]*r:id="(rId\d+)"', wb)
rels = z.read('xl/_rels/workbook.xml.rels').decode('utf-8')
rid2target = dict(re.findall(r'Id="(rId\d+)"[^>]*Target="([^"]+)"', rels))
name2file = {}
for name, rid in sheets:
    tgt = rid2target.get(rid, '').lstrip('/')
    if not tgt.startswith('xl/'): tgt = 'xl/' + tgt
    name2file[name] = tgt
w("\n== 1. 工作表 ==", sheets, "->", name2file)
target_file = name2file[sheets[0][0]]
x = z.read(target_file).decode('utf-8')

# 找出 target 客户编号对应的 sharedString 索引
tgt_ss_idx = {}
for tno in TARGETS:
    for i, sv in enumerate(ss):
        if sv.strip() == tno:
            tgt_ss_idx[tno] = i
            break
w("== 2. 目标客户编号在 sharedStrings 的索引 ==", tgt_ss_idx)

# ---- 3. 遍历每个 <row>, 找到含目标编号的行, 打印原始 XML ----
def col_of(ref):
    letters = ''.join(ch for ch in ref if ch.isalpha())
    idx = 0
    for ch in letters: idx = idx*26 + (ord(ch.upper())-ord('A')+1)
    return idx-1
COLNAME = {0:'登录账号',1:'客户编号',2:'客户名称',3:'客户等级',4:'客户类型',5:'客户标签',6:'客户区域',
           7:'客情预警分类',8:'联系电话',9:'省市区',10:'详细地址',11:'联系人',12:'备注',13:'添加时间',
           14:'所属业务员',15:'上级分销商',16:'推荐人',17:'可用积分',18:'可用预存款',19:'起订金额',
           20:'状态',21:'起订SKU数',22:'自_客户名称',23:'自_所在地区',24:'自_详细地址',25:'自_太古test'}

w("\n== 3. 目标行原始 XML 逐格拆解 ==")
rownum = 0
for rmatch in re.finditer(r'<row[^>]*r="(\d+)"[^>]*>(.*?)</row>', x, re.S):
    rn = rmatch.group(1); rbody = rmatch.group(2)
    cells = re.findall(r'(<c\b[^>]*>.*?</c>|<c\b[^>]*/>)', rbody, re.S)
    # 解析每格
    parsed = {}
    raw_of = {}
    for c in cells:
        tag = c[:c.index('>')+1]
        refm = re.search(r'\br="([A-Za-z]+\d+)"', tag)
        if not refm: continue
        col = col_of(refm.group(1))
        parsed[col] = c
        raw_of[col] = c
    # 该行的 客户编号 (col 1)
    def valof(col):
        c = parsed.get(col)
        if c is None: return None
        t = re.search(r't="(\w+)"', c[:c.index('>')+1])
        t = t.group(1) if t else ''
        v = re.search(r'<v>(.*?)</v>', c, re.S); v = v.group(1) if v else ''
        ist = re.search(r'<t[^>]*>(.*?)</t>', c, re.S)
        if t=='s' and v!='': return ss[int(v)]
        if t=='inlineStr' and ist: return H.unescape(ist.group(1))
        return H.unescape(v)
    cust_no = valof(1)
    if cust_no in TARGETS:
        w(f"\n  --- 行 r={rn}  客户编号={cust_no} ---")
        for col in range(0, 26):
            cn = COLNAME.get(col, f'col{col}')
            raw = raw_of.get(col)
            if raw is None:
                w(f"     [{col:2}] {cn:12} : <该格在XML中完全不存在(省略)>")
            else:
                w(f"     [{col:2}] {cn:12} : 解析值={valof(col)!r}  原始XML={raw}")
rep.close(); z.close()
