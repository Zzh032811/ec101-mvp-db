# -*- coding: utf-8 -*-
"""格式感知读取器: 按文件签名判定 OOXML / BIFF / HTML, 统一返回 (header, rows).
所有单元格返回字符串; 日期由 to_datetime_text 归一.
"""
import zipfile, re, html as H
from html.parser import HTMLParser
from datetime import datetime, timedelta

EPOCH = datetime(1899, 12, 30)


def detect(path):
    with open(path, 'rb') as f:
        head = f.read(8)
    if head[:4] == b'PK\x03\x04':
        return 'OOXML'
    if head[:4] == b'\xd0\xcf\x11\xe0':
        return 'BIFF'
    return 'HTML'


def _serial_to_text(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if 20000 <= f <= 80000:
        dt = EPOCH + timedelta(days=f)
        if abs(f - round(f)) < 1e-9:
            return dt.strftime('%Y-%m-%d')
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    return None


_DT_FORMATS = (
    '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d',
    '%Y/%m/%d %H:%M:%S', '%Y/%m/%d %H:%M', '%Y/%m/%d',
)


def to_datetime_text(v):
    if v is None:
        return ''
    s = str(v).strip()
    if not s:
        return ''
    for f in _DT_FORMATS:
        try:
            return datetime.strptime(s, f).strftime('%Y-%m-%d %H:%M:%S')
        except ValueError:
            pass
    t = _serial_to_text(s)
    return t or s


def to_num(v):
    if v is None:
        return None
    s = str(v).strip().replace(',', '')
    if not s:
        return None
    m = re.match(r'^-?\d+(\.\d+)?$', s)
    if m:
        return float(s)
    m = re.match(r'^-?(\d+(?:\.\d+)?)\s*(个|箱|件|瓶|包|提)$', s)
    if m:
        return float(m.group(1))
    try:
        return float(s)
    except ValueError:
        return None


class _TableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tables = []
        self._cur = None
        self._row = None
        self._cell = None
        self._intd = False

    def handle_starttag(self, tag, attrs):
        if tag == 'table':
            self._cur = []
        elif tag == 'tr' and self._cur is not None:
            self._row = []
        elif tag in ('td', 'th') and self._row is not None:
            self._cell = []
            self._intd = True

    def handle_endtag(self, tag):
        if tag == 'table' and self._cur is not None:
            self.tables.append(self._cur)
            self._cur = None
        elif tag == 'tr' and self._row is not None:
            if self._cur is not None:
                self._cur.append(self._row)
            self._row = None
        elif tag in ('td', 'th') and self._intd:
            if self._row is not None:
                self._row.append(''.join(self._cell).strip())
            self._cell = None
            self._intd = False

    def handle_data(self, data):
        if self._intd and self._cell is not None:
            self._cell.append(data)


def _col_to_index(ref):
    """'AB12' -> 0-based column index (A=0)."""
    letters = ''.join(ch for ch in ref if ch.isalpha())
    idx = 0
    for ch in letters:
        idx = idx * 26 + (ord(ch.upper()) - ord('A') + 1)
    return idx - 1


def _read_ooxml(path):
    z = zipfile.ZipFile(path)
    ss = []
    if 'xl/sharedStrings.xml' in z.namelist():
        s = z.read('xl/sharedStrings.xml').decode('utf-8')
        for si in re.findall(r'<si>(.*?)</si>', s, re.S):
            txt = ''.join(re.findall(r'<t[^>]*>(.*?)</t>', si, re.S))
            ss.append(H.unescape(txt))
    wb = z.read('xl/workbook.xml').decode('utf-8')
    sheets = re.findall(r'<sheet[^>]*name="([^"]+)"[^>]*r:id="(rId\d+)"', wb)
    rels = z.read('xl/_rels/workbook.xml.rels').decode('utf-8')
    # 顺序无关解析: 舟谱部分文件 <Relationship> 是 Target-first, 旧正则假设 Id 在 Target 前会漏配 -> KeyError:'xl/'
    rid2target = {}
    for m in re.finditer(r'<Relationship\b[^>]*>', rels):
        tag = m.group(0)
        rid = re.search(r'\bId="([^"]+)"', tag)
        tgt = re.search(r'\bTarget="([^"]+)"', tag)
        if rid and tgt:
            rid2target[rid.group(1)] = tgt.group(1)
    name2file = {}
    for name, rid in sheets:
        tgt = rid2target.get(rid, '')
        tgt = tgt.lstrip('/')
        if not tgt.startswith('xl/'):
            tgt = 'xl/' + tgt
        name2file[name] = tgt
    first_name = sheets[0][0] if sheets else None
    target = name2file[first_name]
    x = z.read(target).decode('utf-8')
    rows = []
    for r in re.findall(r'<row[^>]*>(.*?)</row>', x, re.S):
        # 自闭合分支必须前置: 否则空样式格 <c r="D12" s="1"/> 的 '/>' 会被 [^>]* 吃进,
        # 与下一个有值格合并 -> 值左移错位且丢失 t="s" 标记(共享字符串被存成原始索引).
        cells = re.findall(r'(<c\b[^>]*/>|<c\b[^>]*>.*?</c>)', r, re.S)
        line = []
        for c in cells:
            tag = c[:c.index('>') + 1]
            ref = re.search(r'\br="([A-Za-z]+\d+)"', tag)
            col = _col_to_index(ref.group(1)) if ref else len(line)
            t = re.search(r't="(\w+)"', tag)
            t = t.group(1) if t else ''
            v = re.search(r'<v>(.*?)</v>', c, re.S)
            v = v.group(1) if v else ''
            ist = re.search(r'<t[^>]*>(.*?)</t>', c, re.S)
            if t == 's' and v != '':
                val = ss[int(v)]
            elif t == 'inlineStr' and ist:
                val = H.unescape(ist.group(1))
            else:
                val = H.unescape(v)
            # 稀疏行: 空单元格可能被省略, 用 ref 列号定位并补齐空档
            while len(line) < col:
                line.append('')
            if len(line) == col:
                line.append(val)
            else:
                line[col] = val
        rows.append(line)
    return first_name, rows


def _read_biff(path):
    import xlrd
    book = xlrd.open_workbook(path)
    sh = book.sheet_by_index(0)
    rows = []
    for ri in range(sh.nrows):
        line = []
        for ci in range(sh.ncols):
            cell = sh.cell(ri, ci)
            if cell.ctype == 3:  # date
                dt = xlrd.xldate_as_datetime(cell.value, book.datemode)
                line.append(dt.strftime('%Y-%m-%d %H:%M:%S'))
            elif cell.ctype == 2:  # number -> keep as text, avoid float artefacts
                fv = cell.value
                if abs(fv - round(fv)) < 1e-9:
                    line.append(str(int(round(fv))))
                else:
                    line.append(repr(fv))
            else:
                line.append(str(cell.value).strip())
        rows.append(line)
    return sh.name, rows


def _read_html(path):
    for enc in ('utf-8', 'gbk', 'gb18030'):
        try:
            text = open(path, encoding=enc).read()
            break
        except UnicodeDecodeError:
            continue
    else:
        text = open(path, encoding='utf-8', errors='ignore').read()
    p = _TableParser()
    p.feed(text)
    if not p.tables:
        return None, []
    tbl = max(p.tables, key=len)
    return 'html', tbl


def read_table(path, header_row=1):
    """return (signature, sheet_name, header, rows)
    header_row: 1-based 表头行号。默认 1(兴路强)；舟谱表头在第 4 行(前 3 行是标题/导出时间/筛选条件)传 4。
    """
    sig = detect(path)
    if sig == 'OOXML':
        sheet, rows = _read_ooxml(path)
    elif sig == 'BIFF':
        sheet, rows = _read_biff(path)
    else:
        sheet, rows = _read_html(path)
    if not rows or header_row > len(rows):
        return sig, sheet, [], []
    header = [c.strip() for c in rows[header_row - 1]]
    return sig, sheet, header, rows[header_row:]
