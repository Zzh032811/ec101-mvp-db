# -*- coding: utf-8 -*-
"""
Extract ONLY structure (sheet names, header row, field names, 2 sample rows,
row counts) from a batch of Excel-ish files.

Handles three real formats regardless of file extension:
  * OOXML (.xlsx, zip container)  -> zipfile + xml.etree iterparse (streaming)
  * BIFF/OLE2 (.xls)              -> xlrd
  * HTML table (Excel 2003 HTML)  -> html.parser streaming

Nothing is ever printed to stdout in Chinese (console is GBK).
All output goes to a UTF-8 file.
"""

import os
import re
import sys
import zipfile
import datetime
import xml.etree.ElementTree as ET
from html.parser import HTMLParser

ROOT = r"D:/Peggy zhan/智能EC101/数据底座/第三阶段数据库设计"
PILOT = os.path.join(ROOT, "快马-兴路强-试点")
OUT_PATH = os.path.join(ROOT, ".extract", "源数据表头.txt")

SCAN_ROWS = 8          # rows scanned for header auto-detection
KEEP_HEAD_ROWS = 14    # rows kept in memory for header + samples
SAMPLE_ROWS = 2        # sample data rows after header
FIRSTCOL_CAP = 400     # cap for Template first-column dump
TPL_COLSCAN = 16       # leading columns scanned when looking for Template "first column"


# --------------------------------------------------------------------------
# signature detection
# --------------------------------------------------------------------------
def detect_signature(path):
    """Return (kind, reader) where kind in OOXML/BIFF/HTML/UNKNOWN."""
    with open(path, "rb") as fh:
        head = fh.read(512)
    if head[:4] == b"PK\x03\x04":
        return "OOXML", "zipfile"
    if head[:4] == b"\xd0\xcf\x11\xe0":
        return "BIFF", "xlrd"
    # strip UTF-8 BOM then look for markup
    stripped = head.lstrip(b"\xef\xbb\xbf").lstrip()
    low = stripped[:200].lower()
    if low.startswith(b"<") or b"<html" in low or b"<table" in low:
        return "HTML", "html"
    if stripped[:5] == b"<?xml":
        return "HTML", "html"
    return "UNKNOWN", "none"


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def col_to_idx(ref):
    """'BC12' -> 0-based column index. Returns -1 when unparseable."""
    n = 0
    for ch in ref:
        if ch.isalpha():
            n = n * 26 + (ord(ch.upper()) - 64)
        else:
            break
    return n - 1 if n else -1


def localname(tag):
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def norm(v):
    """Normalise a raw cell value to a printable string (or None if blank)."""
    if v is None:
        return None
    if isinstance(v, float):
        if v == int(v):
            v = int(v)
        else:
            v = round(v, 6)
    s = str(v).strip()
    if s == "":
        return None
    # collapse newlines so output stays one-line-per-row
    s = re.sub(r"\s*[\r\n]+\s*", " / ", s)
    return s


def is_number(s):
    try:
        float(str(s).replace(",", ""))
        return True
    except (TypeError, ValueError):
        return False


# Excel builtin numFmtIds that mean "date/time"
BUILTIN_DATE_FMT = set(
    list(range(14, 23)) + list(range(27, 37)) + list(range(45, 48)) + list(range(50, 59))
)
EPOCH_1900 = datetime.datetime(1899, 12, 30)
EPOCH_1904 = datetime.datetime(1904, 1, 1)
PRECISION_RISK = 1e15     # numbers >= this lose digits in an IEEE-754 double


def fmt_is_date(code):
    """True when a custom number formatCode describes a date/time."""
    if not code or code.strip().lower() == "general":
        return False
    c = re.sub(r'"[^"]*"', "", code)     # drop quoted literals
    c = re.sub(r"\[[^\]]*\]", "", c)     # drop [Red] / [>=100] etc
    c = re.sub(r"\\.", "", c)            # drop escaped chars like \  or \(
    low = c.lower()
    if re.search(r"[ydhs]", low):
        return True
    # 'm' alone only means month when paired with another date token
    return "m" in low and bool(re.search(r"[ydhs/]", low))


def serial_to_datetime(value, date1904=False):
    """Convert an Excel serial number to a readable timestamp string."""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if f < 0 or f > 2958465:      # out of sane Excel date range
        return None
    base = EPOCH_1904 if date1904 else EPOCH_1900
    try:
        dt = base + datetime.timedelta(days=f)
    except (OverflowError, ValueError):
        return None
    if abs(f - round(f)) < 1e-9:
        return dt.strftime("%Y-%m-%d")
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def col_letter(idx):
    """0-based column index -> Excel letter (0 -> 'A')."""
    s = ""
    idx += 1
    while idx:
        idx, rem = divmod(idx - 1, 26)
        s = chr(65 + rem) + s
    return s


def pad_grid(grid):
    """Pad ragged grid to a rectangle."""
    width = max((len(r) for r in grid), default=0)
    return [list(r) + [None] * (width - len(r)) for r in grid], width


def detect_header_row(grid):
    """
    Auto-detect the header row index (0-based) within the first SCAN_ROWS rows.

    Scoring favours rows that are wide, short-labelled and non-numeric;
    penalises single-cell title rows, long report-note text and numeric data.
    """
    best_idx, best_score = 0, None
    limit = min(len(grid), SCAN_ROWS)
    for i in range(limit):
        row = grid[i]
        cells = [norm(c) for c in row]
        cells = [c for c in cells if c is not None]
        n = len(cells)
        if n == 0:
            continue
        score = float(n)
        for c in cells:
            if len(c) > 25:
                score -= 1.5          # long text -> report note / sentence
            if len(c) > 60:
                score -= 3.0
            if is_number(c):
                score -= 2.5          # pure number -> data row, not a header
        if n == 1:
            score -= 4.0              # single title cell
        # bonus: every cell looks like a compact label
        if all((not is_number(c)) and len(c) <= 25 for c in cells) and n >= 3:
            score += 3.0
        if best_score is None or score > best_score:
            best_score, best_idx = score, i
    return best_idx


def fmt_pre_rows(grid, hdr_idx):
    """Dump rows above the detected header verbatim."""
    lines = []
    for i in range(hdr_idx):
        vals = [norm(c) or "" for c in grid[i]]
        while vals and vals[-1] == "":
            vals.pop()
        lines.append("  第%d行: %s" % (i + 1, " | ".join(vals) if vals else "(空)"))
    return "\n".join(lines) if lines else "(无)"


def build_report(grid, total_rows, notes, sheet_label, numeric_cols=None):
    """Turn a head-grid + total row count into report lines."""
    out = []
    grid, width = pad_grid(grid)
    if not grid or width == 0 or all(all(norm(c) is None for c in r) for r in grid):
        out.append("[Sheet: %s]" % sheet_label)
        out.append("表头行号(从1开始): 无法判定(空表)")
        out.append("解析错误/备注: %s" % ("; ".join(notes) if notes else "工作表为空"))
        return out
    hdr_idx = detect_header_row(grid)
    header = [norm(c) for c in grid[hdr_idx]]
    # trim trailing empty columns but keep interior gaps (labelled)
    while header and header[-1] is None:
        header.pop()
    ncol = len(header)
    out.append("[Sheet: %s]" % sheet_label)
    out.append("表头行号(从1开始): %d" % (hdr_idx + 1))
    out.append("表头之前的说明行:")
    out.append(fmt_pre_rows(grid, hdr_idx))
    fields = " | ".join(
        "%d) %s" % (i + 1, header[i] if header[i] is not None else "(空列名)")
        for i in range(ncol)
    )
    out.append("字段清单(共%d个): %s" % (ncol, fields if ncol else "(无)"))

    data_rows = grid[hdr_idx + 1:]
    shown = 0
    for r in data_rows:
        if shown >= SAMPLE_ROWS:
            break
        vals = [norm(c) for c in r[:ncol]]
        if all(v is None for v in vals):
            continue      # skip fully blank rows, do not waste a sample slot
        shown += 1
        pairs = " | ".join(
            "%s=%s" % (
                header[i] if i < ncol and header[i] is not None else "列%d" % (i + 1),
                vals[i] if i < len(vals) and vals[i] is not None else "",
            )
            for i in range(ncol)
        )
        out.append("样例行%d: %s" % (shown, pairs))
    if shown == 0:
        out.append("样例行1: (无数据行)")

    data_count = total_rows - (hdr_idx + 1) if total_rows is not None else None
    if data_count is not None:
        if data_count < 0:
            data_count = 0
        out.append("数据行数(不含表头): %d" % data_count)
    else:
        out.append("数据行数(不含表头): 未知")
    all_notes = list(notes) + precision_notes(
        data_rows[:SAMPLE_ROWS + 2], header, numeric_cols or set())
    out.append("解析错误/备注: %s" % ("; ".join(all_notes) if all_notes else "无"))
    return out


# --------------------------------------------------------------------------
# OOXML reader (zipfile + iterparse, streaming)
# --------------------------------------------------------------------------
def load_shared_strings(zf):
    if "xl/sharedStrings.xml" not in zf.namelist():
        return []
    strings = []
    with zf.open("xl/sharedStrings.xml") as fh:
        ctx = ET.iterparse(fh, events=("end",))
        for _, elem in ctx:
            if localname(elem.tag) != "si":
                continue
            parts = []
            for sub in elem.iter():
                if localname(sub.tag) == "t" and sub.text:
                    parts.append(sub.text)
            strings.append("".join(parts))
            elem.clear()
    return strings


def sheet_targets(zf):
    """Return ordered list of (sheet_name, zip_member_path)."""
    names = zf.namelist()
    wb_xml = zf.read("xl/workbook.xml")
    root = ET.fromstring(wb_xml)
    sheets = []          # (name, rid)
    for el in root.iter():
        if localname(el.tag) == "sheet":
            rid = None
            for k, v in el.attrib.items():
                if localname(k) == "id":
                    rid = v
            sheets.append((el.get("name") or "(unnamed)", rid))

    # relationship id -> target
    relmap = {}
    relname = "xl/_rels/workbook.xml.rels"
    if relname in names:
        rroot = ET.fromstring(zf.read(relname))
        for el in rroot.iter():
            if localname(el.tag) == "Relationship":
                rid = el.get("Id")
                tgt = el.get("Target") or ""
                tgt = tgt.lstrip("/")
                if not tgt.startswith("xl/"):
                    tgt = "xl/" + tgt if not tgt.startswith("/") else tgt
                relmap[rid] = tgt

    result = []
    used = set()
    for name, rid in sheets:
        tgt = relmap.get(rid)
        if tgt and tgt in names:
            result.append((name, tgt))
            used.add(tgt)
        else:
            result.append((name, None))

    # fallback: assign leftover worksheet members in numeric order
    if any(t is None for _, t in result):
        leftover = sorted(
            (n for n in names
             if re.match(r"^xl/worksheets/sheet\d+\.xml$", n) and n not in used),
            key=lambda p: int(re.search(r"(\d+)", p).group(1)),
        )
        fixed = []
        li = 0
        for name, tgt in result:
            if tgt is None:
                tgt = leftover[li] if li < len(leftover) else None
                li += 1
            fixed.append((name, tgt))
        result = fixed
    return result


def load_styles(zf):
    """Parse xl/styles.xml -> list mapping cellXf index -> bool(is date format)."""
    if "xl/styles.xml" not in zf.namelist():
        return []
    try:
        root = ET.fromstring(zf.read("xl/styles.xml"))
    except ET.ParseError:
        return []
    custom = {}
    for el in root.iter():
        if localname(el.tag) == "numFmt":
            try:
                custom[int(el.get("numFmtId"))] = el.get("formatCode") or ""
            except (TypeError, ValueError):
                pass
    cellxfs = None
    for el in root.iter():
        if localname(el.tag) == "cellXfs":
            cellxfs = el
            break
    if cellxfs is None:
        return []
    flags = []
    for xf in cellxfs:
        if localname(xf.tag) != "xf":
            continue
        try:
            fid = int(xf.get("numFmtId") or 0)
        except ValueError:
            fid = 0
        if fid in BUILTIN_DATE_FMT:
            flags.append(True)
        elif fid in custom:
            flags.append(fmt_is_date(custom[fid]))
        else:
            flags.append(False)
    return flags


def workbook_date1904(zf):
    """True when the workbook uses the 1904 date system."""
    try:
        root = ET.fromstring(zf.read("xl/workbook.xml"))
    except Exception:
        return False
    for el in root.iter():
        if localname(el.tag) == "workbookPr":
            v = (el.get("date1904") or "").lower()
            return v in ("1", "true")
    return False


def extract_cell(c_elem, shared, xfs=None, date1904=False, date_cols=None, ci=None,
                 num_cols=None):
    """Return the display value of one <c> element (string, or None if blank)."""
    t = c_elem.get("t")
    if t == "inlineStr":
        parts = []
        for sub in c_elem.iter():
            if localname(sub.tag) == "t" and sub.text:
                parts.append(sub.text)
        return "".join(parts) if parts else None
    v_text = None
    for ch in c_elem:
        if localname(ch.tag) == "v":
            v_text = ch.text
            break
    if v_text is None:
        return None
    if t == "s":
        try:
            return shared[int(v_text)]
        except (ValueError, IndexError):
            return None
    if t in ("str", "e"):
        return v_text
    # numeric (t is None or 'n'): decode when the style says it is a date
    if num_cols is not None and ci is not None:
        num_cols.add(ci)
    if xfs:
        try:
            s_idx = int(c_elem.get("s") or 0)
        except ValueError:
            s_idx = 0
        if s_idx < len(xfs) and xfs[s_idx]:
            decoded = serial_to_datetime(v_text, date1904)
            if decoded is not None:
                if date_cols is not None and ci is not None:
                    date_cols.add(ci)
                return decoded
    return v_text


def read_ooxml_sheet(zf, member, shared, xfs=None, date1904=False):
    """
    Stream one worksheet without loading it fully into memory.
    Returns (head_grid, total_row_count, date_cols, dimension_ref, notes).
    """
    notes = []
    head_rows = []
    total = 0
    max_r = 0
    dim_ref = None
    date_cols = set()
    num_cols = set()
    with zf.open(member) as fh:
        ctx = ET.iterparse(fh, events=("start", "end"))
        root = None
        for event, elem in ctx:
            if event == "start":
                if root is None:
                    root = elem
                elif dim_ref is None and localname(elem.tag) == "dimension":
                    dim_ref = elem.get("ref")
                continue
            tag = localname(elem.tag)
            if tag == "dimension" and dim_ref is None:
                dim_ref = elem.get("ref")
            if tag != "row":
                continue
            total += 1
            r_attr = elem.get("r")
            if r_attr and r_attr.isdigit():
                max_r = max(max_r, int(r_attr))
            if total <= KEEP_HEAD_ROWS:
                cells = {}
                nxt = 0
                for c in elem:
                    if localname(c.tag) != "c":
                        continue
                    ref = c.get("r") or ""
                    ci = col_to_idx(ref)
                    if ci < 0:
                        ci = nxt
                    cells[ci] = extract_cell(c, shared, xfs, date1904, date_cols, ci,
                                             num_cols)
                    nxt = ci + 1
                if cells:
                    w = max(cells) + 1
                    head_rows.append([cells.get(i) for i in range(w)])
                else:
                    head_rows.append([])
            elem.clear()
            if root is not None and total % 2000 == 0:
                root.clear()
    if root is not None:
        root.clear()
    if max_r and max_r != total:
        notes.append("流内<row>计数=%d, 最大r属性=%d (差异通常为稀疏行/尾部空行)" % (total, max_r))
    if dim_ref:
        notes.append("工作表 <dimension ref>=%s" % dim_ref)
        m = re.match(r"^[A-Za-z]+\d+:([A-Za-z]+)(\d+)$", dim_ref.strip())
        if m:
            dim_rows = int(m.group(2))
            if dim_rows < total:
                notes.append("警告-<dimension> 会导致截断: 声明 %d 行 < 实际 <row> 计数 %d 行, "
                             "pandas/openpyxl(read_only) 会少读 %d 行数据, 必须用流式解析"
                             % (dim_rows, total, total - dim_rows))
            elif dim_rows > total:
                notes.append("备注-<dimension> 声明 %d 行 > 实际 <row> 计数 %d 行 "
                             "(差异为尾部/稀疏空行, 读取时会多出空行, 无数据丢失)"
                             % (dim_rows, total))
        elif re.match(r"^[A-Za-z]+\d+$", dim_ref.strip()):
            notes.append("警告-<dimension> 严重错误: 只声明了单个单元格 %s, 实际 <row> 计数 "
                         "%d 行; pandas/openpyxl(read_only) 会把它当成 1 行 1 列而几乎读不到数据, "
                         "该文件必须用流式解析" % (dim_ref.strip(), total))
    return head_rows, total, date_cols, num_cols, dim_ref, notes


def date_note(header, date_cols):
    """Note which columns were stored as Excel serials and decoded to datetimes."""
    if not date_cols:
        return []
    names = []
    for ci in sorted(date_cols):
        if header and ci < len(header) and header[ci] is not None:
            names.append("%s(第%d列)" % (header[ci], ci + 1))
        else:
            names.append("第%d列(%s)" % (ci + 1, col_letter(ci)))
    return ["以下列在文件中以 Excel 日期序列号存储, 已按 numFmt 解码为日期时间: "
            + ", ".join(names)]


def precision_notes(grid, header, numeric_cols):
    """
    Flag columns whose sample values are plain numbers with |v| >= 1e15.
    Such values (order ids, coupon ids) cannot survive an IEEE-754 double
    losslessly, so they must be modelled as strings.
    Only columns physically stored as numbers are considered.
    """
    if not numeric_cols:
        return []
    risky = []
    ncol = len(header) if header else 0
    for r in grid:
        span = min(len(r), ncol) if ncol else len(r)
        for ci in range(span):
            if ci not in numeric_cols:
                continue
            v = r[ci]
            if v is None:
                continue
            sv = str(v).strip()
            if not re.match(r"^-?\d+(\.\d+)?([eE][+-]?\d+)?$", sv):
                continue
            try:
                if abs(float(sv)) >= PRECISION_RISK:
                    risky.append(ci)
            except ValueError:
                continue
    if not risky:
        return []
    seen = []
    for ci in dict.fromkeys(risky):
        if header and ci < len(header) and header[ci] is not None:
            seen.append("%s(第%d列)" % (header[ci], ci + 1))
        else:
            seen.append("第%d列(%s)" % (ci + 1, col_letter(ci)))
    return ["警告-数值精度风险: 以下列在文件里【以数值类型存储】且样例值 |值|>=1e15 "
            "(编号/单号被写成了数字), IEEE-754 双精度仅约15-17位有效数字, 末位可能已丢失, "
            "建模时必须按字符串处理: " + ", ".join(seen)]


def process_ooxml(path, rel, out):
    try:
        zf = zipfile.ZipFile(path)
    except Exception as e:
        out.append("Sheet 列表: (无法打开 zip)")
        out.append("解析错误/备注: %s: %s" % (type(e).__name__, e))
        return
    try:
        shared = load_shared_strings(zf)
        xfs = load_styles(zf)
        date1904 = workbook_date1904(zf)
        targets = sheet_targets(zf)
        out.append("Sheet 列表: %s" % ", ".join(n for n, _ in targets))
        for name, member in targets:
            if member is None:
                out.append("[Sheet: %s]" % name)
                out.append("解析错误/备注: 未能定位对应 worksheet XML 成员")
                continue
            grid, total, date_cols, num_cols, dim_ref, notes = read_ooxml_sheet(
                zf, member, shared, xfs, date1904)
            # derive the header once more so the date note can name the columns
            padded, width = pad_grid(grid) if grid else ([], 0)
            if padded:
                hdr_idx = detect_header_row(padded)
                header = [norm(c) for c in padded[hdr_idx]]
                while header and header[-1] is None:
                    header.pop()
                notes.extend(date_note(header, date_cols))
            out.extend(build_report(grid, total, notes, name, num_cols))
            out.append("")
    except Exception as e:
        out.append("解析错误/备注: OOXML 解析异常 %s: %s" % (type(e).__name__, e))
    finally:
        zf.close()


# --------------------------------------------------------------------------
# BIFF reader (xlrd)
# --------------------------------------------------------------------------
def process_biff(path, rel, out):
    try:
        import xlrd
    except ImportError:
        out.append("Sheet 列表: (未知)")
        out.append("解析错误/备注: 该文件是 BIFF 格式，xlrd 不可用，无法解析，需手工处理")
        return
    try:
        wb = xlrd.open_workbook(path, on_demand=True)
    except Exception as e:
        out.append("Sheet 列表: (未知)")
        out.append("解析错误/备注: xlrd 打开失败 %s: %s" % (type(e).__name__, e))
        return
    try:
        names = wb.sheet_names()
        out.append("Sheet 列表: %s" % ", ".join(names))
        for name in names:
            notes = []
            try:
                sh = wb.sheet_by_name(name)
                nrows = sh.nrows
                ncols = sh.ncols
                grid = []
                numeric_cols = set()
                for r in range(min(KEEP_HEAD_ROWS, nrows)):
                    row_vals = []
                    for c in range(ncols):
                        cell = sh.cell(r, c)
                        # XL_CELL_DATE -> keep as float, note it
                        if cell.ctype == xlrd.XL_CELL_DATE:
                            numeric_cols.add(c)
                            try:
                                row_vals.append(
                                    xlrd.xldate_as_datetime(cell.value, wb.datemode)
                                    .strftime("%Y-%m-%d %H:%M:%S"))
                            except Exception:
                                row_vals.append(cell.value)
                        elif cell.ctype == xlrd.XL_CELL_NUMBER:
                            numeric_cols.add(c)
                            row_vals.append(cell.value)
                        elif cell.ctype == xlrd.XL_CELL_EMPTY:
                            row_vals.append(None)
                        else:
                            row_vals.append(cell.value)
                    grid.append(row_vals)
                if sh.nrows > KEEP_HEAD_ROWS:
                    notes.append("xlrd 报告 nrows=%d, ncols=%d" % (nrows, ncols))
                out.extend(build_report(grid, nrows, notes, name, numeric_cols))
            except Exception as e:
                out.append("[Sheet: %s]" % name)
                out.append("解析错误/备注: 读取失败 %s: %s" % (type(e).__name__, e))
            out.append("")
    finally:
        try:
            wb.release_resources()
        except Exception:
            pass


# --------------------------------------------------------------------------
# HTML reader (streaming HTMLParser)
# --------------------------------------------------------------------------
class TableParser(HTMLParser):
    def __init__(self, keep=KEEP_HEAD_ROWS):
        super().__init__(convert_charrefs=True)
        self.keep = keep
        self.tables = 0
        self.total_rows = 0
        self.head_rows = []
        self.head_num_cols = []      # parallel: set of numeric col idx per kept row
        self._row = None
        self._row_num = None
        self._cell = None
        self._cell_num = False

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.tables += 1
        elif tag == "tr":
            self._row = []
            self._row_num = set()
        elif tag in ("td", "th"):
            self._cell = []
            cls = ""
            for k, v in attrs:
                if k.lower() == "class" and v:
                    cls = v.lower()
            self._cell_num = ("num" in cls)

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None:
            if self._row is not None:
                if self._cell_num:
                    self._row_num.add(len(self._row))
                self._row.append("".join(self._cell))
            self._cell = None
            self._cell_num = False
        elif tag == "tr" and self._row is not None:
            self.total_rows += 1
            if self.total_rows <= self.keep:
                self.head_rows.append(self._row)
                self.head_num_cols.append(self._row_num)
            self._row = None
            self._row_num = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def process_html(path, rel, out):
    notes = []
    sheet_names = []
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
    except Exception as e:
        out.append("Sheet 列表: (读取失败)")
        out.append("解析错误/备注: %s: %s" % (type(e).__name__, e))
        return
    text = raw.decode("utf-8-sig", errors="replace")
    # Excel-HTML carries the logical worksheet name in the MSO conditional block
    sheet_names = re.findall(r"<x:Name>(.*?)</x:Name>", text, re.S)
    del raw

    p = TableParser()
    try:
        p.feed(text)
        p.close()
    except Exception as e:
        notes.append("HTML 解析异常 %s: %s" % (type(e).__name__, e))
    if not sheet_names:
        sheet_names = ["HTMLTable%d" % (i + 1) for i in range(max(p.tables, 1))]
    notes.append("实际格式为 Excel 2003 HTML 表格 (扩展名 .xlsx 不可信)")
    notes.append("发现 <table> 数=%d" % p.tables)
    out.append("Sheet 列表: %s" % ", ".join(sheet_names))
    label = sheet_names[0] if sheet_names else "HTMLTable1"
    numeric_cols = set()
    for s in p.head_num_cols:
        numeric_cols |= s
    notes.append("HTML 单元格自带 class=str/num 类型标记, 数值型列 = %s"
                 % (", ".join(col_letter(i) for i in sorted(numeric_cols))
                    if numeric_cols else "(无)"))
    out.extend(build_report(p.head_rows, p.total_rows, notes, label, numeric_cols))
    out.append("")


# --------------------------------------------------------------------------
# Template special handling: sheet names + all first-column values
# --------------------------------------------------------------------------
def template_first_columns(path, out):
    out.append("")
    out.append("-------- Template 专项: 每个 Sheet 名 + 第一列取值 --------")
    try:
        zf = zipfile.ZipFile(path)
    except Exception as e:
        out.append("解析错误/备注: 无法打开 %s: %s" % (type(e).__name__, e))
        return
    try:
        shared = load_shared_strings(zf)
        targets = sheet_targets(zf)
        out.append("Template Sheet 列表(共%d个): %s"
                   % (len(targets), ", ".join(n for n, _ in targets)))
        for name, member in targets:
            out.append("")
            out.append("[Template Sheet: %s]" % name)
            if member is None:
                out.append("  第一列取值: (未能定位 worksheet)")
                continue
            total = 0
            try:
                xfs = load_styles(zf)
                d1904 = workbook_date1904(zf)
                # collect de-duplicated values for each of the first N columns,
                # because several Template sheets leave column A entirely empty
                col_uniq = [dict() for _ in range(TPL_COLSCAN)]
                head_rows = []
                with zf.open(member) as fh:
                    ctx = ET.iterparse(fh, events=("start", "end"))
                    root = None
                    for event, elem in ctx:
                        if event == "start":
                            if root is None:
                                root = elem
                            continue
                        if localname(elem.tag) != "row":
                            continue
                        total += 1
                        cells = {}
                        for c in elem:
                            if localname(c.tag) != "c":
                                continue
                            ci = col_to_idx(c.get("r") or "")
                            if ci < 0:
                                continue
                            # only decode the leading columns + header candidates
                            if ci < TPL_COLSCAN or total <= KEEP_HEAD_ROWS:
                                cells[ci] = extract_cell(c, shared, xfs, d1904)
                        if total <= KEEP_HEAD_ROWS:
                            if cells:
                                w = max(cells) + 1
                                head_rows.append([cells.get(i) for i in range(w)])
                            else:
                                head_rows.append([])
                        for ci in range(TPL_COLSCAN):
                            if ci in cells:
                                v = norm(cells[ci])
                                if v is not None and len(col_uniq[ci]) < FIRSTCOL_CAP + 1:
                                    col_uniq[ci].setdefault(v, None)
                        elem.clear()
                        if root is not None and total % 2000 == 0:
                            root.clear()
                    if root is not None:
                        root.clear()
                if head_rows:
                    padded, _w = pad_grid(head_rows)
                    h_idx = detect_header_row(padded)
                    hnorm = [norm(x) for x in padded[h_idx]]
                    while hnorm and hnorm[-1] is None:
                        hnorm.pop()
                    out.append("  表头行号(从1开始): %d" % (h_idx + 1))
                    out.append("  表头字段: %s"
                               % (" | ".join(x if x is not None else "(空)" for x in hnorm)
                                  if hnorm else "(无)"))
                    if h_idx > 0:
                        out.append("  表头之前的说明行:")
                        out.append(fmt_pre_rows(padded, h_idx))
                out.append("  总行数(<row>计数): %d" % total)
                pick = None
                for ci in range(TPL_COLSCAN):
                    if col_uniq[ci]:
                        pick = ci
                        break
                if pick is None:
                    out.append("  第一列取值: (前%d列全部为空)" % TPL_COLSCAN)
                else:
                    if pick > 0:
                        span = ("A 列(第1列)" if pick == 1
                                else "A~%s 列(第1~%d列)" % (col_letter(pick - 1), pick))
                        out.append("  注意: %s整列为空, 实际最左有值列 = %s (第%d列)"
                                   % (span, col_letter(pick), pick + 1))
                    else:
                        out.append("  最左有值列 = A (第1列)")
                    uniq = list(col_uniq[pick].keys())
                    truncated = len(uniq) > FIRSTCOL_CAP
                    if truncated:
                        uniq = uniq[:FIRSTCOL_CAP]
                    out.append("  该列非空取值(去重, %d 个%s): %s"
                               % (len(uniq), ", 已截断" if truncated else "",
                                  " | ".join(uniq) if uniq else "(空)"))
            except Exception as e:
                out.append("  解析错误/备注: %s: %s" % (type(e).__name__, e))
    finally:
        zf.close()


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------
TARGETS = [
    (os.path.join(PILOT, "Product2026091410431769689.xlsx"), "Product2026091410431769689.xlsx (商品/舟谱)"),
    (os.path.join(PILOT, "User2026091410413051852.xlsx"), "User2026091410413051852.xlsx (客户/舟谱)"),
    (os.path.join(PILOT, "平台操作手册.xlsx"), "平台操作手册.xlsx"),
    (os.path.join(PILOT, "优惠券", "快马-兴路强-优惠券-活动明细-字段参考.xlsx"), "优惠券/快马-兴路强-优惠券-活动明细-字段参考.xlsx"),
    (os.path.join(PILOT, "满减", "快马-兴路强-满减-活动明细-20260831-20260917.xlsx"), "满减/快马-兴路强-满减-活动明细-20260831-20260917.xlsx"),
    (os.path.join(PILOT, "满减", "快马-兴路强-满减-销售明细-20260831-20260917.xls"), "满减/快马-兴路强-满减-销售明细-20260831-20260917.xls"),
    (os.path.join(PILOT, "满减", "快马-兴路强-满减-销售明细-20260831-20260917.xlsx"), "满减/快马-兴路强-满减-销售明细-20260831-20260917.xlsx"),
    (os.path.join(PILOT, "满赠", "快马-兴路强-满赠-活动明细-20260819-20260831.xlsx"), "满赠/快马-兴路强-满赠-活动明细-20260819-20260831.xlsx"),
    (os.path.join(PILOT, "满赠", "快马-兴路强-满赠-订单明细-20260819-20260831.xls"), "满赠/快马-兴路强-满赠-订单明细-20260819-20260831.xls"),
    (os.path.join(PILOT, "满赠", "快马-兴路强-满赠-销售明细-20260819-20260831.xlsx"), "满赠/快马-兴路强-满赠-销售明细-20260819-20260831.xlsx"),
    (os.path.join(ROOT, "兴路强-产品映射-20260921-0851（0921导出）.xlsx"), "兴路强-产品映射-20260921-0851（0921导出）.xlsx"),
    (os.path.join(ROOT, "兴路强-客资映射-20260921-0850（0921导出）.xlsx"), "兴路强-客资映射-20260921-0850（0921导出）.xlsx"),
    (os.path.join(ROOT, "Template_系统主要功能模块要求.xlsx"), "Template_系统主要功能模块要求.xlsx"),
]


def main():
    out = []
    out.append("# 源数据结构提取报告 (仅结构: 表头字段名 / 前2行样例 / 行数 / Sheet名)")
    out.append("# 生成脚本: .extract/extract_headers.py   输出编码: UTF-8")
    out.append("#")
    out.append("# 读取方式说明:")
    out.append("#   * 一律按【文件头魔数】判定真实格式, 不信任扩展名:")
    out.append("#       PK\\x03\\x04 -> OOXML(zip) ; \\xd0\\xcf\\x11\\xe0 -> BIFF/OLE2 ; '<' -> HTML")
    out.append("#   * .xlsx 使用 zipfile + xml.etree.iterparse 流式解析(只保留前 %d 行 + 计数 <row>),"
               % KEEP_HEAD_ROWS)
    out.append("#     不把整份 XML 读入内存。不使用 openpyxl: 舟谱导出的 Product/User 文件")
    out.append("#     <dimension> 声明是错的, openpyxl read_only 会把 max_row 报成 1。")
    out.append("#   * 数据行数 = 流内 <row> 元素计数 - 表头行号; 备注里同时给出 <dimension ref>")
    out.append("#     与最大 r 属性以便交叉核对。")
    out.append("#   * 表头行自动探测: 扫描前 %d 行, 取\"非空短标签最多、纯数字/长句最少\"的一行。"
               % SCAN_ROWS)
    out.append("#   * Excel 日期序列号按 styles.xml 的 numFmt 解码为 yyyy-mm-dd HH:MM:SS。")
    out.append("")
    status = []
    for idx, (path, rel) in enumerate(TARGETS, 1):
        print("[%d/%d] %s" % (idx, len(TARGETS), "processing..."), flush=True)
        if not os.path.exists(path):
            out.append("==================== %s ====================" % rel)
            out.append("解析错误/备注: 文件不存在")
            out.append("")
            status.append((rel, "MISSING"))
            continue
        size = os.path.getsize(path)
        kind, reader = detect_signature(path)
        block = []
        block.append("==================== %s ====================" % rel)
        block.append("文件大小: %d bytes  文件签名判定: %s  使用的读取方式: %s"
                     % (size, kind, reader))
        try:
            if kind == "OOXML":
                process_ooxml(path, rel, block)
                st = "OK"
            elif kind == "BIFF":
                process_biff(path, rel, block)
                st = "OK"
            elif kind == "HTML":
                process_html(path, rel, block)
                st = "OK"
            else:
                block.append("Sheet 列表: (未知)")
                block.append("解析错误/备注: 无法识别文件签名, 前8字节=%s"
                             % open(path, "rb").read(8).hex())
                st = "UNKNOWN"
        except Exception as e:
            block.append("解析错误/备注: 顶层异常 %s: %s" % (type(e).__name__, e))
            st = "FAIL"
        ascii_st = st
        if any(k in "\n".join(block) for k in ("无法解析", "FAIL", "异常", "失败", "警告-")):
            if st == "OK":
                st = "OK(含警告)"
                ascii_st = "WARN"
            ascii_st = "WARN" if st == "OK(含警告)" else st
        out.extend(block)
        out.append("")
        status.append((rel, st))
        print("    -> %s (%s/%s)" % (ascii_st.encode("ascii", "replace").decode(),
                                     kind, reader), flush=True)

    # Template extra section
    tpl = os.path.join(ROOT, "Template_系统主要功能模块要求.xlsx")
    if os.path.exists(tpl):
        print("[template] extracting first columns...", flush=True)
        try:
            template_first_columns(tpl, out)
        except Exception as e:
            out.append("Template 专项解析失败: %s: %s" % (type(e).__name__, e))
        out.append("")

    out.append("==================== 汇总状态 ====================")
    for rel, st in status:
        out.append("%-10s %s" % (st, rel))

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(out))
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
