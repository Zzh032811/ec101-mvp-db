from pathlib import Path
from typing import Iterable, List

import pandas as pd
from bs4 import BeautifulSoup


def detect_table_format(path: Path) -> str:
    signature = Path(path).read_bytes()[:16]
    if signature.startswith(b"PK"):
        return "ooxml"
    if signature.startswith(bytes.fromhex("D0CF11E0A1B11AE1")):
        return "biff"
    if signature.lstrip().startswith((b"<", b"\xef\xbb\xbf<")):
        return "html"
    raise ValueError(f"无法识别表格格式: {path}")


def _deduplicate_headers(headers: Iterable[str]) -> List[str]:
    counts = {}
    result = []
    for index, raw_header in enumerate(headers, start=1):
        header = str(raw_header).strip() or f"未命名列{index}"
        counts[header] = counts.get(header, 0) + 1
        result.append(header if counts[header] == 1 else f"{header}_{counts[header]}")
    return result


def _read_html_excel(path: Path) -> pd.DataFrame:
    text = Path(path).read_text(encoding="utf-8-sig", errors="replace")
    table_start = text.lower().find("<table")
    if table_start < 0:
        raise ValueError(f"HTML Excel 中未找到 table: {path}")
    soup = BeautifulSoup(text[table_start:], "lxml")
    rows = []
    for table_row in soup.find_all("tr"):
        cells = [cell.get_text(" ", strip=True) for cell in table_row.find_all(["td", "th"])]
        if cells:
            rows.append(cells)
    if not rows:
        raise ValueError(f"HTML Excel 中未找到数据行: {path}")
    width = max(len(row) for row in rows)
    normalized_rows = [row + [""] * (width - len(row)) for row in rows]
    headers = _deduplicate_headers(normalized_rows[0])
    frame = pd.DataFrame(normalized_rows[1:], columns=headers)
    return frame.replace("", pd.NA).dropna(how="all").reset_index(drop=True)


def read_table(path: Path) -> pd.DataFrame:
    path = Path(path)
    table_format = detect_table_format(path)
    if table_format == "html":
        return _read_html_excel(path)
    if table_format == "ooxml":
        return pd.read_excel(path, engine="openpyxl")
    return pd.read_excel(path, engine="xlrd")

