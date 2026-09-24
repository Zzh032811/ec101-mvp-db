# -*- coding: utf-8 -*-
"""EC101 第二平台接入 — 舟谱 / 羿柏.

范围(本轮): 客户主数据 + 商品主数据 + SXD订单(order_header/order_line) + XD履约(fulfillment) + RAW血缘.
不做: 返券/满赠核算 · 销售明细 · 活动明细 · 退货冲回 · RESULT层 · cross_mapping.

共库追加(严禁重建): 羿柏作为新的 dealer_platform 写进同一 ec101_mvp.db;
兴路强按 dealer_platform_id 隔离, 加载前后逐表计数不变(验证#4).

配置驱动: 字段映射读 std_field_mapping(platform='舟谱', 由 seed_std_mapping_zhoupu.py 灌入);
舟谱特有的非1:1语义(复合主键 / 客户·商品双过桥 / XD权威状态 / 计算列)在本薄适配层.

五个锁定决策:
  1 共库追加   2 配置驱动+薄适配   3 主数据+订单两层   4 订单两层都落   5 order_status 取 XD 权威
两条业务规则:
  Rule1 SXD状态='未下发' → 本就无 XD, 正常业务(非缺口)
  Rule2 XD同单据多行 → 全行'已完成'才判完成; 否则取'最未完成'(待审核<待出库<待入库<待签收<已完成)

用法:
  python ingest_zhoupu.py          # DRY(默认): 只读文件+算匹配统计+打印验证报告, 绝不写库
  python ingest_zhoupu.py --real   # 真正写库(append; 先幂等清理羿柏作用域再重灌)
"""
import os
import re
import sys
import sqlite3
from collections import defaultdict
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))
from readers import read_table, to_num, to_datetime_text
from std_mapping import load_mapping, map_rows, project, ec_col_index, unmapped_columns

REAL = "--real" in sys.argv

MVP = r"D:\Peggy zhan\智能EC101\数据底座\第三阶段数据库设计\mvp"
BASE = r"D:\Peggy zhan\智能EC101\数据底座\第三阶段数据库设计\舟谱-羿柏-试点"
DB = os.path.join(MVP, "ec101_mvp.db")
REPORT = os.path.join(MVP, "ingest_report_zhoupu.txt")

PLATFORM = "舟谱"
DEALER = "羿柏"
BATCH_CODE = "ZHOUPU-YIBAI-MASTER-ORDER-XD-20260923"
OPERATOR = "小凡"
HR = 4  # 舟谱表头在第4行(前3行=标题/导出时间/筛选条件)

# std_field_mapping.module 词表(配置驱动映射)
MAP_CUST, MAP_PROD, MAP_SXD, MAP_XD = "客户资料", "商品资料", "订单明细", "订单履约"
# raw_file.module 词表(血缘)
RAW_CUST, RAW_PROD, RAW_ORDER, RAW_FULFILL = "客户", "商品", "订单", "订单履约"

F_CUST = os.path.join(BASE, "客户档案-20260914.xlsx")
F_PROD = os.path.join(BASE, "商品档案-20260914.xlsx")
SXD_FILES = [
    os.path.join(BASE, "满减", "舟谱-羿柏-订单明细 0826-0827.xlsx"),
    os.path.join(BASE, "满减", "舟谱-羿柏-订单明细 0828-0830.xlsx"),
    os.path.join(BASE, "满减", "舟谱-羿柏-订单明细 0831-0902.xlsx"),
    os.path.join(BASE, "满减", "舟谱-羿柏-订单明细 0903-0905.xlsx"),
    os.path.join(BASE, "满减", "舟谱-羿柏-订单明细 0906-0908.xlsx"),
    os.path.join(BASE, "满赠", "满赠订单明细20260819-20260821.xlsx"),
    os.path.join(BASE, "满赠", "满赠订单明细20260822-20260823.xlsx"),  # 换掉旧0821-0823(与0819-0821在08-21重叠); 新文件仅08-22/23, 窗口连续无重叠
    os.path.join(BASE, "满赠", "满赠订单明细20260824-20260826.xlsx"),
]
XD_FILES = [
    os.path.join(BASE, "满减", "舟谱-羿柏-订单明细-XD-20260826-20260908.xlsx"),
    os.path.join(BASE, "满赠", "满赠XD20260819-20260826.xlsx"),
]

# Rule2: 状态优先级(越小越未完成)
STATUS_RANK = {"待审核": 0, "待出库": 1, "待入库": 2, "待签收": 3, "已完成": 4}

rep = open(REPORT, "w", encoding="utf-8")


def w(*a):
    s = " ".join(str(x) for x in a)
    print(s)
    rep.write(s + "\n")


def r2(x):
    return None if x is None else round(float(x) + 0.0, 2)


def norm_id(s):
    """规范化 ID/条码连接键: 满赠XD把'商品id'存成浮点串('237.0'), 主数据'商品唯一序号'是'237'.
    去掉尾部'.0'(及全零小数)使二者可连接; 非数值/已规范值原样返回. 不改变语义, 仅统一格式.
    """
    s = str(s).strip()
    if not s:
        return s
    m = re.match(r"^(\d+)\.0+$", s)
    return m.group(1) if m else s


def agg_status(statuses):
    """Rule2: 全行'已完成'才判完成; 否则取'最未完成'代表; 有未知状态则暴露未知(不敢判完成)."""
    ss = [s for s in statuses if s]
    if not ss:
        return ""
    if all(s == "已完成" for s in ss):
        return "已完成"
    unknown = [s for s in ss if s not in STATUS_RANK]
    if unknown:
        return unknown[0]
    return min(ss, key=lambda s: STATUS_RANK[s])


def parse_per_box(*texts):
    """从'大单位换算'/'单位换算'文本尽力解析'每大单位含多少基本单位'. 解析不出返回 None(不臆造)."""
    for t in texts:
        if t is None:
            continue
        s = str(t).strip()
        if not s:
            continue
        n = to_num(s)
        if n is not None and n > 0:
            return n
        m = re.search(r"(\d+(?:\.\d+)?)\s*[*×xX]\s*(\d+(?:\.\d+)?)", s)  # '1*15'
        if m:
            return float(m.group(2))
        m = re.search(r"(\d+(?:\.\d+)?)", s)  # 兜底取第一个数
        if m:
            v = float(m.group(1))
            if v > 0:
                return v
    return None


# ─────────────────────────── DB 连接 ───────────────────────────
con = sqlite3.connect(DB)
con.execute("PRAGMA foreign_keys = ON")
cur = con.cursor()


def has_col(table, col):
    return any(r[1] == col for r in cur.execute(f"PRAGMA table_info({table})"))


def xingluqiang_counts():
    """兴路强(非舟谱 dealer_platform)在各 CORE 表的行数 — 隔离性快照."""
    ids = [r[0] for r in cur.execute("SELECT dealer_platform_id FROM dealer_platform WHERE platform_name<>?", (PLATFORM,))]
    if not ids:
        return {"customer": 0, "product": 0, "order_header": 0, "order_line": 0, "fulfillment": 0}
    q = ",".join("?" * len(ids))
    out = {}
    out["customer"] = cur.execute(f"SELECT count(*) FROM customer WHERE dealer_platform_id IN ({q})", ids).fetchone()[0]
    out["product"] = cur.execute(f"SELECT count(*) FROM product WHERE dealer_platform_id IN ({q})", ids).fetchone()[0]
    out["order_header"] = cur.execute(f"SELECT count(*) FROM order_header WHERE dealer_platform_id IN ({q})", ids).fetchone()[0]
    oid_sub = f"SELECT order_id FROM order_header WHERE dealer_platform_id IN ({q})"
    out["order_line"] = cur.execute(f"SELECT count(*) FROM order_line WHERE order_id IN ({oid_sub})", ids).fetchone()[0]
    out["fulfillment"] = cur.execute(f"SELECT count(*) FROM fulfillment WHERE order_id IN ({oid_sub})", ids).fetchone()[0]
    return out


w("=" * 78)
w("舟谱 / 羿柏 第二平台接入  —  模式 =", "REAL(写库)" if REAL else "DRY(只读预演, 不写库)")
w("库 =", DB)
w("=" * 78)

SNAP_BEFORE = xingluqiang_counts()
w("\n[隔离基线] 兴路强(非舟谱)加载前计数:", SNAP_BEFORE)

# ─────────────────────────── 0. 守卫式 ALTER(非破坏) ───────────────────────────
if REAL:
    if not has_col("order_header", "downstream_order_no"):
        cur.execute("ALTER TABLE order_header ADD COLUMN downstream_order_no TEXT")
        w("\n[步骤0.5] ALTER order_header ADD downstream_order_no TEXT  (兴路强既有行得 NULL)")
    else:
        w("\n[步骤0.5] order_header.downstream_order_no 已存在, 跳过 ALTER")
    con.commit()
else:
    w("\n[步骤0.5] DRY: 跳过 ALTER (活库当前 downstream_order_no 存在? =", has_col("order_header", "downstream_order_no"), ")")

# ─────────────────────────── 1. 幂等清理(仅羿柏作用域, 按FK顺序) ───────────────────────────
def cleanup_yibai():
    row = cur.execute("SELECT dealer_platform_id FROM dealer_platform WHERE dealer_name=? AND platform_name=?", (DEALER, PLATFORM)).fetchone()
    if not row:
        w("[清理] 羿柏 dealer_platform 不存在, 无需清理(首次运行)")
        return
    dp = row[0]
    oid_sub = "SELECT order_id FROM order_header WHERE dealer_platform_id=?"
    n_ful = cur.execute(f"DELETE FROM fulfillment WHERE order_id IN ({oid_sub})", (dp,)).rowcount
    n_ol = cur.execute(f"DELETE FROM order_line WHERE order_id IN ({oid_sub})", (dp,)).rowcount
    n_oh = cur.execute("DELETE FROM order_header WHERE dealer_platform_id=?", (dp,)).rowcount
    n_prod = cur.execute("DELETE FROM product WHERE dealer_platform_id=?", (dp,)).rowcount
    n_cust = cur.execute("DELETE FROM customer WHERE dealer_platform_id=?", (dp,)).rowcount
    w(f"[清理] 羿柏作用域删除: fulfillment={n_ful} order_line={n_ol} order_header={n_oh} product={n_prod} customer={n_cust}")


if REAL:
    cleanup_yibai()
    # RAW 血缘幂等
    for (b,) in cur.execute("SELECT batch_id FROM raw_import_batch WHERE batch_code=?", (BATCH_CODE,)).fetchall():
        cur.execute("DELETE FROM raw_file WHERE batch_id=?", (b,))
        cur.execute("DELETE FROM raw_import_batch WHERE batch_id=?", (b,))
    con.commit()
else:
    w("[清理] DRY: 跳过清理")

# ─────────────────────────── 2. dealer_platform + RAW batch ───────────────────────────
row = cur.execute("SELECT dealer_platform_id FROM dealer_platform WHERE dealer_name=? AND platform_name=?", (DEALER, PLATFORM)).fetchone()
if row:
    DP = row[0]
elif REAL:
    cur.execute("INSERT INTO dealer_platform(dealer_name,platform_name,admission_status) VALUES(?,?,?)", (DEALER, PLATFORM, "已接入"))
    DP = cur.lastrowid
else:
    DP = -1  # DRY 占位
w("\n[dealer_platform] 羿柏/舟谱 dealer_platform_id =", DP)

NOW = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
if REAL:
    cur.execute("INSERT INTO raw_import_batch(batch_code,source_platform,dealer_name,imported_at,operator) VALUES(?,?,?,?,?)",
                (BATCH_CODE, PLATFORM, DEALER, NOW, OPERATOR))
    BATCH = cur.lastrowid
else:
    BATCH = -1
w("[RAW] raw_import_batch batch_code =", BATCH_CODE, " batch_id =", BATCH)

RAW_ROWS = []  # (file_name, module, sig, sheet, header_row, data_rows)


def reg_file(fname, module, sig, sheet, nrows):
    RAW_ROWS.append((fname, module, sig, sheet, HR, nrows))
    if REAL:
        cur.execute("INSERT INTO raw_file(batch_id,file_name,module,file_signature,read_method,sheet_name,header_row,data_rows) VALUES(?,?,?,?,?,?,?,?)",
                    (BATCH, fname, module, sig, f"readers.read_table(header_row={HR})", sheet, HR, nrows))


# ─────────────────────────── 3. 客户主数据 ───────────────────────────
w("\n" + "=" * 78)
w("[3] 客户主数据  ←", os.path.basename(F_CUST))
sig, sheet, hdr, rows = read_table(F_CUST, header_row=HR)
reg_file(os.path.basename(F_CUST), RAW_CUST, sig, sheet, len(rows))
mC = load_mapping(con, PLATFORM, MAP_CUST)
unmappedC = unmapped_columns(con, PLATFORM, MAP_CUST, hdr)
mapped = map_rows(hdr, rows, mC)

cust_id_by_composite = {}
cust_id_by_name = defaultdict(list)
_synth = 0
dup_comp = blank_cname = 0
for mr in mapped:
    name = (mr.get("客户名称") or "").strip()
    mnem = (mr.get("客户助记码") or "").strip()
    comp = f"{name}|{mnem}"
    if not name:
        blank_cname += 1
    if comp in cust_id_by_composite:
        dup_comp += 1
        continue
    row = project(mr, "customer")
    if REAL:
        cur.execute("""INSERT INTO customer(dealer_platform_id,platform_customer_no,customer_name,customer_type,
            customer_level,customer_tag,customer_region,salesperson_name,created_at,status)
            VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (DP, comp, row.get("customer_name") or name, row.get("customer_type"), row.get("customer_level"),
             row.get("customer_tag"), row.get("customer_region"), row.get("salesperson_name"),
             row.get("created_at"), row.get("status")))
        cid = cur.lastrowid
    else:
        _synth += 1
        cid = _synth
    cust_id_by_composite[comp] = cid
    if name:
        cust_id_by_name[name].append(cid)
w(f"  客户行={len(mapped)}  入库(去重后)={len(cust_id_by_composite)}  复合键重复跳过={dup_comp}  空客户名={blank_cname}")
w(f"  未映射列(客户资料): {unmappedC}")
sample_comp = list(cust_id_by_composite.keys())[:3]
w(f"  抽样复合键(名称|助记码): {sample_comp}")
dup_names = {n: ids for n, ids in cust_id_by_name.items() if len(ids) > 1}
w(f"  [冲突] 羿柏内客户重名(名称→多id)数={len(dup_names)}  样例={list(dup_names.items())[:3]}")
del rows, mapped

# ─────────────────────────── 4. 商品主数据 ───────────────────────────
w("\n" + "=" * 78)
w("[4] 商品主数据  ←", os.path.basename(F_PROD))
sig, sheet, hdr, rows = read_table(F_PROD, header_row=HR)
reg_file(os.path.basename(F_PROD), RAW_PROD, sig, sheet, len(rows))
mP = load_mapping(con, PLATFORM, MAP_PROD)
unmappedP = unmapped_columns(con, PLATFORM, MAP_PROD, hdr)
mapped = map_rows(hdr, rows, mP)

prod_id_by_no = {}
prod_id_by_barcode = {}
prod_boxqty = {}
dup_pno = dup_bc = blank_pno = perbox_ok = 0
prod_samples = []
for mr in mapped:
    pno = norm_id(mr.get("平台商品编号"))   # = 商品唯一序号 = XD.商品id (规范化去'.0')
    nm = (mr.get("商品名称") or "").strip()
    bc = norm_id(mr.get("商品条码"))         # = 小单位条码
    row = project(mr, "product")
    per_box = parse_per_box(mr.get("每箱基本单位数量"), row.get("box_conversion"))
    if per_box is not None:
        perbox_ok += 1
    if not pno:
        blank_pno += 1
    if pno in prod_id_by_no:
        dup_pno += 1
        continue
    if REAL:
        cur.execute("""INSERT INTO product(dealer_platform_id,platform_product_no,product_name,brand,category,
            spec,barcode,base_unit,box_conversion,swire_product_code) VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (DP, pno, row.get("product_name") or nm, row.get("brand"), row.get("category"), row.get("spec"),
             row.get("barcode"), row.get("base_unit"), row.get("box_conversion"), row.get("swire_product_code")))
        pid = cur.lastrowid
    else:
        _synth += 1
        pid = _synth
    prod_id_by_no[pno] = pid
    if bc:
        if bc in prod_id_by_barcode:
            dup_bc += 1
        else:
            prod_id_by_barcode[bc] = pid
    prod_boxqty[pid] = per_box
    if len(prod_samples) < 3:
        prod_samples.append((pno, nm[:16], bc, mr.get("每箱基本单位数量"), row.get("box_conversion"), per_box))
w(f"  商品行={len(mapped)}  入库(去重后)={len(prod_id_by_no)}  编号重复跳过={dup_pno}  空商品编号={blank_pno}")
w(f"  条码重复(取首条)={dup_bc}  唯一条码={len(prod_id_by_barcode)}  每箱换算解析成功={perbox_ok}/{len(mapped)}")
w(f"  未映射列(商品资料): {unmappedP}")
w("  抽样(编号,名称,条码,大单位换算,单位换算,解析per_box):")
for s in prod_samples:
    w("    ", s)
del rows, mapped

# ─────────────────────────── 5. XD 桥索引(流式, 先于SXD) ───────────────────────────
w("\n" + "=" * 78)
w("[5] XD 履约桥索引  ← 2 文件 (一律按列名定位, 禁止固定列序)")
mX = load_mapping(con, PLATFORM, MAP_XD)
xd_order = {}          # 单据 -> {mnem,cname,phone,region,level,settle,statuses[],signs[],outs[],rets[],has_return,files}
xd_line_bc = {}        # (单据,条形码) -> 商品id
xd_line_nm = {}        # (单据,商品名称) -> 商品id
xd_doc_collisions = 0
xd_bc_conflicts = 0
xd_total_rows = 0
for f in XD_FILES:
    sig, sheet, hdr, rows = read_table(f, header_row=HR)
    reg_file(os.path.basename(f), RAW_FULFILL, sig, sheet, len(rows))
    unmappedX = unmapped_columns(con, PLATFORM, MAP_XD, hdr)
    ci = ec_col_index(hdr, mX)
    has_return = "退货数量" in ci   # 满减XD有'退货结算数量'; 满赠XD无(仅（大/中/小）) → return_qty None

    def gv(row, ec, ci=ci):
        i = ci.get(ec)
        v = row[i] if (i is not None and i < len(row)) else ""
        return v if v is not None else ""

    file_docs = set()
    for row in rows:
        doc = str(gv(row, "XD单号")).strip()
        if not doc:
            continue
        xd_total_rows += 1
        o = xd_order.get(doc)
        if o is None:
            o = xd_order[doc] = dict(mnem="", cname="", phone="", region="", level="", settle="",
                                     statuses=[], signs=[], outs=[], rets=[], has_return=has_return, files=set())
        if doc not in file_docs:
            file_docs.add(doc)
            if o["files"]:
                xd_doc_collisions += 1  # 同单据跨文件
        o["files"].add(os.path.basename(f))
        for fld, ec in (("mnem", "客户助记码"), ("cname", "客户名称"), ("phone", "老板电话"),
                        ("region", "客户区域"), ("level", "客户等级"), ("settle", "结款状态")):
            if not o[fld]:
                v = str(gv(row, ec)).strip()
                if v:
                    o[fld] = v
        o["statuses"].append(str(gv(row, "履约订单状态")).strip())
        sg = to_datetime_text(gv(row, "完成时间"))
        if sg:
            o["signs"].append(sg)
        ot = to_datetime_text(gv(row, "出库时间"))
        if ot:
            o["outs"].append(ot)
        if has_return:
            rr = to_num(gv(row, "退货数量"))
            if rr is not None:
                o["rets"].append(rr)
        # 行级商品桥
        pid_no = norm_id(gv(row, "商品id"))
        bc = norm_id(gv(row, "商品条码"))
        nm = str(gv(row, "商品名称")).strip()
        if pid_no:
            if bc:
                k = (doc, bc)
                if k in xd_line_bc and xd_line_bc[k] != pid_no:
                    xd_bc_conflicts += 1
                xd_line_bc.setdefault(k, pid_no)
            if nm:
                xd_line_nm.setdefault((doc, nm), pid_no)
    w(f"  {os.path.basename(f)}: cols={len(hdr)} rows={len(rows)} 单据={len(file_docs)} "
      f"has_return={has_return} 未映射列={unmappedX}")
    del rows

# XD 单据级后处理(Rule2 聚合)
xd_all_complete = xd_not_all = xd_mixed = 0
for doc, o in xd_order.items():
    o["status_agg"] = agg_status(o["statuses"])
    o["mixed"] = len({s for s in o["statuses"] if s}) > 1
    o["completed_at"] = max(o["signs"]) if o["signs"] else (max(o["outs"]) if o["outs"] else "")
    o["return_qty"] = r2(sum(o["rets"])) if o["has_return"] else None
    if o["status_agg"] == "已完成":
        xd_all_complete += 1
    else:
        xd_not_all += 1
    if o["mixed"]:
        xd_mixed += 1
w(f"  XD 桥汇总: 总行={xd_total_rows} 单据={len(xd_order)} 全完成={xd_all_complete} 非全完成={xd_not_all}")
w(f"  [Rule2/冲突] 同单据状态不一致(mixed)={xd_mixed} (预期0)  跨文件同单据={xd_doc_collisions}  条码→商品id冲突={xd_bc_conflicts}")

# ─────────────────────────── 6. SXD 订单两层加载 ───────────────────────────
w("\n" + "=" * 78)
w("[6] SXD 订单  ← 8 文件 → order_header + order_line + fulfillment")
mS = load_mapping(con, PLATFORM, MAP_SXD)

order_first = {}                 # ono -> 首个 header mapped row
order_file = {}                  # ono -> 首个来源文件
order_lines = defaultdict(list)  # ono -> [line mapped rows] (仅首文件)
overlap_orders = set()           # 跨文件重复出现的 ono(满赠窗口重叠)
footer_rows = 0
sxd_total_rows = 0
per_file_unmapped = {}

for f in SXD_FILES:
    sig, sheet, hdr, rows = read_table(f, header_row=HR)
    reg_file(os.path.basename(f), RAW_ORDER, sig, sheet, len(rows))
    unmappedS = unmapped_columns(con, PLATFORM, MAP_SXD, hdr)
    per_file_unmapped[os.path.basename(f)] = (len(hdr), len(rows), unmappedS)
    mapped = map_rows(hdr, rows, mS)
    fname = os.path.basename(f)
    for mr in mapped:
        sxd_total_rows += 1
        ono = (mr.get("订单编号") or "").strip()
        if not ono or not ono.startswith("SXD"):
            footer_rows += 1   # '合计'总计行(每文件1行)或空订单号 → 非订单, 跳过
            continue
        if ono not in order_first:
            order_first[ono] = mr
            order_file[ono] = fname
            order_lines[ono].append(mr)
        elif order_file[ono] == fname:
            order_lines[ono].append(mr)   # 同文件的另一行
        else:
            overlap_orders.add(ono)       # 跨文件重复(已加载) → 跳过, 避免重复计数
    del rows, mapped

for fn, (nc, nr, um) in per_file_unmapped.items():
    w(f"  {fn}: cols={nc} rows={nr} 未映射列={um}")
w(f"  SXD 总行={sxd_total_rows}  distinct订单={len(order_first)}  跳过总计/空行={footer_rows}  跨文件重叠订单={len(overlap_orders)}")


def match_customer(sxd_cname, xd, stat):
    """客户三级过桥: A=XD助记码复合键桥 / B=名称唯一回退 / C=置空. 返回 (cid, tier)."""
    if xd:
        comp_a = f"{xd['cname']}|{xd['mnem']}"
        cid = cust_id_by_composite.get(comp_a)
        if cid is not None:
            stat["A_xdname"] += 1
            return cid, "A"
        comp_b = f"{sxd_cname}|{xd['mnem']}"
        cid = cust_id_by_composite.get(comp_b)
        if cid is not None:
            stat["A2_sxdname"] += 1
            return cid, "A2"
    for nm in (sxd_cname, xd["cname"] if xd else ""):
        nm = (nm or "").strip()
        if nm and nm in cust_id_by_name and len(cust_id_by_name[nm]) == 1:
            stat["B_name"] += 1
            return cust_id_by_name[nm][0], "B"
    nm = (sxd_cname or "").strip()
    if nm and nm in cust_id_by_name and len(cust_id_by_name[nm]) > 1:
        stat["C_ambiguous"] += 1
    else:
        stat["D_none"] += 1
    return None, "C"


def match_product(downstream, bc, nm, stat):
    """商品三级过桥: A=XD商品id桥 / B=条码直连 / C=置空. 返回 (pid, tier)."""
    if downstream:
        pid_no = xd_line_bc.get((downstream, bc)) if bc else None
        if pid_no is None and nm:
            pid_no = xd_line_nm.get((downstream, nm))
        if pid_no is not None:
            pid = prod_id_by_no.get(str(pid_no).strip())
            if pid is not None:
                stat["A_xd_pid"] += 1
                return pid, "A"
            stat["A_pid_not_in_master"] += 1  # XD给了id但主数据无此SKU
    if bc and bc in prod_id_by_barcode:
        stat["B_barcode"] += 1
        return prod_id_by_barcode[bc], "B"
    stat["C_none"] += 1
    return None, "C"


cust_stat = defaultdict(int)
prod_stat = defaultdict(int)
status_src = defaultdict(int)          # XD / SXD_fallback
fallback_no_downstream = 0             # Rule1 正常(未下发/状态空, 无下游编号)
fallback_gap = 0                       # 有下游编号但XD不在窗口(覆盖缺口)
fallback_status_dist = defaultdict(int)
divergent = defaultdict(int)           # SXD'已完成'但XD权威≠已完成 → 按XD聚合值分
status_blank = 0
hdr_inserted = hdr_ignored = 0
line_inserted = line_merged = line_price_conflict = 0
base_qty_null = 0
unit_dist = defaultdict(int)
ful_inserted = 0
orders_with_xd = orders_without_xd = 0
unresolved_cust = []
unresolved_prod = []
sample_target = "SXD260827000153"
sample_dump = None
referenced_xd = set()   # 被 SXD.下游订单编号 引用的 XD单号; §6.5 据此判定 XD-only

for ono in order_first:
    mr = order_first[ono]
    downstream = (mr.get("下游订单编号") or "").strip() or None
    xd = xd_order.get(downstream) if downstream else None
    if downstream:
        referenced_xd.add(downstream)
    sxd_cname = (mr.get("客户名称") or "").strip()
    sxd_status = (mr.get("订单状态") or "").strip()

    # order_status: 决策5 取 XD 权威, 无XD回退 SXD
    if xd:
        order_status = xd["status_agg"]
        status_src["XD"] += 1
        orders_with_xd += 1
        if sxd_status == "已完成" and order_status != "已完成":
            divergent[order_status] += 1
    else:
        order_status = sxd_status
        status_src["SXD_fallback"] += 1
        orders_without_xd += 1
        if downstream:
            fallback_gap += 1
        else:
            fallback_no_downstream += 1
        fallback_status_dist[sxd_status or "(空)"] += 1
        if not order_status:
            status_blank += 1

    cid, ctier = match_customer(sxd_cname, xd, cust_stat)
    if cid is None and len(unresolved_cust) < 50:
        unresolved_cust.append((ono, sxd_cname, downstream, ctier))

    order_time = to_datetime_text(mr.get("下单时间"))
    oh = project(mr, "order_header")
    pay_method = oh.get("pay_method")

    if REAL:
        cur.execute("""INSERT OR IGNORE INTO order_header(dealer_platform_id,order_no,order_time,customer_id,
            order_status,pay_method,pay_status,order_source,order_type,downstream_order_no,batch_id)
            VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (DP, ono, order_time, cid, order_status, pay_method, oh.get("pay_status"),
             oh.get("order_source"), oh.get("order_type"), downstream, BATCH))
        if cur.rowcount == 0:
            hdr_ignored += 1
            oid = cur.execute("SELECT order_id FROM order_header WHERE dealer_platform_id=? AND order_no=?", (DP, ono)).fetchone()[0]
        else:
            hdr_inserted += 1
            oid = cur.lastrowid
    else:
        _synth += 1
        oid = _synth
        hdr_inserted += 1

    # fulfillment: 仅 XD 命中的单
    if xd:
        if REAL:
            cur.execute("""INSERT OR IGNORE INTO fulfillment(order_id,order_status,completed_at,t2_release_candidate,return_qty)
                VALUES(?,?,?,?,?)""", (oid, xd["status_agg"], xd["completed_at"] or None, 0, xd["return_qty"]))
            ful_inserted += cur.rowcount
        else:
            ful_inserted += 1

    # order_line: 逐行过商品桥, 按(pid或原始键)聚合
    line_agg = {}
    for seq, lm in enumerate(order_lines[ono]):
        bc = norm_id(lm.get("商品条码"))
        nm = (lm.get("商品名称") or "").strip()
        pno_sxd = (lm.get("商品编号") or "").strip()
        pid, ptier = match_product(downstream, bc, nm, prod_stat)
        if pid is None and len(unresolved_prod) < 50:
            unresolved_prod.append((ono, nm[:16], bc, pno_sxd, downstream))
        key = pid if pid is not None else ("RAW:" + (bc or nm or pno_sxd or f"seq{seq}"))
        qty = to_num(lm.get("订货数量"))
        pre = to_num(lm.get("优惠前金额"))
        paid = to_num(lm.get("实付金额"))
        price = to_num(lm.get("单价"))
        unit = (lm.get("订货单位") or "").strip()
        unit_dist[unit] += 1
        disc = (pre - paid) if (pre is not None and paid is not None) else None
        a = line_agg.get(key)
        if a is None:
            line_agg[key] = dict(pid=pid, qty=qty or 0.0, pre=pre or 0.0, paid=paid, disc=disc or 0.0,
                                 price=price, unit=unit, nm=nm, bc=bc)
        else:
            a["qty"] += qty or 0.0
            a["pre"] += pre or 0.0
            a["disc"] += disc or 0.0
            if paid is not None:
                a["paid"] = (a["paid"] or 0.0) + paid if a["paid"] is not None else paid
            if price is not None and a["price"] is not None and abs(price - a["price"]) > 1e-9:
                line_price_conflict += 1  # 合并但单价不同 → 保留首行单价
            line_merged += 1

    for key, a in line_agg.items():
        per_box = prod_boxqty.get(a["pid"]) if a["pid"] is not None else None
        base_qty = r2(a["qty"] * per_box) if (per_box and a["unit"]) else None
        if base_qty is None:
            base_qty_null += 1
        if REAL:
            cur.execute("""INSERT INTO order_line(order_id,product_id,order_qty,order_unit,base_qty,base_unit,
                pre_discount_amount,discount_amount,unit_price,return_qty) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (oid, a["pid"], r2(a["qty"]), a["unit"], base_qty, None, r2(a["pre"]), r2(a["disc"]),
                 r2(a["price"]), None))
        line_inserted += 1

    if ono == sample_target:
        sample_dump = dict(ono=ono, downstream=downstream, order_status=order_status, status_src=("XD" if xd else "SXD"),
                           cust=(sxd_cname, cid, ctier), n_lines=len(line_agg),
                           lines=[(a["nm"][:16], a["bc"], a["pid"], a["qty"], a["unit"], r2(a["pre"]), r2(a["disc"])) for a in line_agg.values()])

w(f"  order_header: 插入={hdr_inserted} OR_IGNORE去重={hdr_ignored}")
w(f"  order_line: 插入={line_inserted} 合并的同品多行={line_merged} 合并但单价不同={line_price_conflict}")
w(f"  base_qty 为空(无per_box/无pid)={base_qty_null}")
w(f"  订货单位分布(top): {dict(sorted(unit_dist.items(), key=lambda x:-x[1])[:8])}")
w(f"  fulfillment 插入={ful_inserted}")

w("\n  [验证#7] SXD→XD 过桥:")
w(f"    有XD命中={orders_with_xd}  无XD={orders_without_xd}")
w(f"    无XD细分: ①无下游编号(Rule1正常)={fallback_no_downstream}  ②有下游编号但XD不在窗口(覆盖缺口)={fallback_gap}")
w(f"    回退SXD状态分布: {dict(fallback_status_dist)}   order_status空(源即空)={status_blank}")

w("\n  [验证#9] order_status 来源分布(决策5):", dict(status_src))
w(f"    SXD'已完成'但XD权威≠已完成(应为~136): {dict(divergent)}  合计={sum(divergent.values())}")

w("\n  [验证#8] 客户三级命中:", dict(cust_stat))
w(f"    置空未决样例(前50存清单, 显示前8): {unresolved_cust[:8]}")
w("\n  [验证#8b] 商品三级命中:", dict(prod_stat))
w(f"    置空未决样例(前50存清单, 显示前8): {unresolved_prod[:8]}")

if sample_dump:
    w(f"\n  [验证#6] 抽样订单 {sample_target}:")
    w("    ", {k: sample_dump[k] for k in ("ono", "downstream", "order_status", "status_src", "cust", "n_lines")})
    for ln in sample_dump["lines"][:20]:
        w("      line(名称,条码,pid,数量,单位,优惠前,优惠额):", ln)
else:
    w(f"\n  [验证#6] 未找到抽样订单 {sample_target}(可能不在本轮窗口)")

# ─────────────────────────── 6.5 XD-only 建单(结算改造: XD已完成即结算, 不管有无SXD) ───────────────────────────
# 用户规则(2026-09-24): 结算触发以 XD 履约'已完成'为准, 与是否关联 SXD 无关; SXD 仅代表用户下单.
# 现状缺口: XD 文件里 2856 单无任何 SXD 引用(XD-only), 其中 2709 已完成, 旧 SXD-中心模型完全漏掉.
# 本块: 独立二次读取 XD 文件(不碰已验证的 §5 桥), 对 XD-only 且 XD 开头(排除 TD 退货/测试客户)的单,
#        用 XD 自带字段建 order_header + order_line + fulfillment. 客户经'名称|助记码'复合键桥, 商品经'商品id'桥.
w("\n" + "=" * 78)
w("[6.5] XD-only 建单  ← 二次读取 2 个 XD 文件 (仅未被 SXD 引用者)")

# 下单数量列名回退链(满减XD 单列'下单数量'; 满赠XD 拆大/中/小, 取基本单位'（小）')
QTY_COLS = ["下单数量", "下单数量（小）", "下单数量(小)", "下单数量（中）", "下单数量（大）"]
xdonly_hdr = xdonly_line = xdonly_ful = 0
xdonly_skip_td = xdonly_skip_test = xdonly_referenced = xdonly_skip_other = 0
xdonly_cust_hit = xdonly_cust_miss = 0
xdonly_prod_hit = xdonly_prod_miss = 0
xdonly_status_dist = defaultdict(int)
xdonly_amt_sum = 0.0
td_cnt = 0; td_amt = 0.0
seen_docs = set()   # 跨文件同单据只分类/建单一次(首次为准); 所有诊断计数按 distinct doc, 不被双文件重复计

for f in XD_FILES:
    sig, sheet, hdr, rows = read_table(f, header_row=HR)
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

    def qty_of(row, gr2=gr2):
        for c in QTY_COLS:
            v = to_num(gr2(row, c))
            if v is not None:
                return v
        return None

    # 先按 doc 聚合本文件内的行(状态/时间/客户/行级)
    doc_rows = defaultdict(list)
    for row in rows:
        doc = str(gv2(row, "XD单号")).strip()
        if doc:
            doc_rows[doc].append(row)
    del rows

    for doc, drows in doc_rows.items():
        if doc in seen_docs:
            continue   # 跨文件同单据: 首次已分类/建单, 不重复计数
        seen_docs.add(doc)
        if doc in referenced_xd:
            xdonly_referenced += 1
            continue
        if doc.startswith("TD"):
            xdonly_skip_td += 1
            for row in drows:
                a = to_num(gr2(row, "下单金额"))
                if a: td_amt += a
            td_cnt += 1
            continue
        if not doc.startswith("XD"):
            xdonly_skip_other += 1   # 表尾'合计'总计行等非单据行, 严禁建单(否则灌入 300万假单)
            continue
        # 客户复合键 + 状态聚合 + 单据时间(取首个非空)
        cname = mnem = doctime = ""
        statuses = []; signs = []; outs = []
        for row in drows:
            if not cname: cname = str(gv2(row, "客户名称")).strip()
            if not mnem:  mnem = str(gv2(row, "客户助记码")).strip()
            if not doctime:
                dt = to_datetime_text(gr2(row, "单据时间"))
                if dt: doctime = dt
            statuses.append(str(gv2(row, "履约订单状态")).strip())
            sg = to_datetime_text(gv2(row, "完成时间"))
            if sg: signs.append(sg)
            ot = to_datetime_text(gv2(row, "出库时间"))
            if ot: outs.append(ot)
        if cname == "测试":
            xdonly_skip_test += 1
            continue
        status_agg = agg_status(statuses)
        completed_at = max(signs) if signs else (max(outs) if outs else "")
        xdonly_status_dist[status_agg or "(空)"] += 1

        cid = cust_id_by_composite.get(f"{cname}|{mnem}")
        if cid is not None: xdonly_cust_hit += 1
        else: xdonly_cust_miss += 1

        order_time = doctime or completed_at or ""
        if REAL:
            cur.execute("""INSERT OR IGNORE INTO order_header(dealer_platform_id,order_no,order_time,customer_id,
                order_status,pay_method,pay_status,order_source,order_type,downstream_order_no,batch_id)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (DP, doc, order_time, cid, status_agg, None, None, "XD履约(无SXD)", None, None, BATCH))
            if cur.rowcount == 0:
                oid = cur.execute("SELECT order_id FROM order_header WHERE dealer_platform_id=? AND order_no=?", (DP, doc)).fetchone()[0]
            else:
                oid = cur.lastrowid
                xdonly_hdr += 1
        else:
            _synth += 1; oid = _synth; xdonly_hdr += 1

        # fulfillment(XD 本身即履约)
        if REAL:
            cur.execute("""INSERT OR IGNORE INTO fulfillment(order_id,order_status,completed_at,t2_release_candidate,return_qty)
                VALUES(?,?,?,?,?)""", (oid, status_agg, completed_at or None, 0, None))
            xdonly_ful += cur.rowcount
        else:
            xdonly_ful += 1

        # order_line: 按 product_id 聚合(桥不到则按原始名称), 金额=下单金额, 数量=下单数量回退链
        line_agg2 = {}
        for row in drows:
            pid_no = norm_id(gv2(row, "商品id"))
            nm = str(gv2(row, "商品名称")).strip()
            pid = prod_id_by_no.get(pid_no) if pid_no else None
            if pid is not None: xdonly_prod_hit += 1
            else: xdonly_prod_miss += 1
            amt = to_num(gr2(row, "下单金额"))
            if amt: xdonly_amt_sum += amt
            q = qty_of(row)
            key = pid if pid is not None else ("RAW:" + (nm or pid_no or "x"))
            a = line_agg2.get(key)
            if a is None:
                line_agg2[key] = dict(pid=pid, qty=q or 0.0, pre=amt or 0.0)
            else:
                a["qty"] += q or 0.0
                a["pre"] += amt or 0.0
        for key, a in line_agg2.items():
            if REAL:
                cur.execute("""INSERT INTO order_line(order_id,product_id,order_qty,order_unit,base_qty,base_unit,
                    pre_discount_amount,discount_amount,unit_price,return_qty) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (oid, a["pid"], r2(a["qty"]), None, None, None, r2(a["pre"]), 0, None, None))
            xdonly_line += 1
    del doc_rows

w(f"  XD-only 建单: order_header={xdonly_hdr}  order_line={xdonly_line}  fulfillment={xdonly_ful}")
w(f"  跳过(distinct doc): 被SXD引用={xdonly_referenced}  TD退货单={xdonly_skip_td}(金额={r2(td_amt)})  测试客户={xdonly_skip_test}  非XD单据行(合计等)={xdonly_skip_other}")
w(f"  客户桥: 命中={xdonly_cust_hit}  未命中={xdonly_cust_miss}   商品桥行: 命中={xdonly_prod_hit}  未命中={xdonly_prod_miss}")
w(f"  XD-only 状态分布: {dict(xdonly_status_dist)}   下单金额合计={r2(xdonly_amt_sum)}")

# ─────────────────────────── 7. 隔离性 + FK + 血缘 汇总 ───────────────────────────
if REAL:
    con.commit()

SNAP_AFTER = xingluqiang_counts()
w("\n" + "=" * 78)
w("[验证#4] 隔离性 — 兴路强(非舟谱)加载前/后计数(应逐一相等):")
for t in ("customer", "product", "order_header", "order_line", "fulfillment"):
    b, a = SNAP_BEFORE[t], SNAP_AFTER[t]
    flag = "OK" if b == a else "!! 变化 !!"
    w(f"    {t:14} before={b:6}  after={a:6}  Δ={a-b:+d}  {flag}")

if REAL:
    fk = cur.execute("PRAGMA foreign_key_check").fetchall()
    w(f"\n[验证#6/#9b] PRAGMA foreign_key_check: {fk if fk else '无输出(通过)'}")
    zp = DP
    w("\n[汇总] 羿柏各表行数:")
    for t, col in (("customer", "dealer_platform_id"), ("product", "dealer_platform_id"), ("order_header", "dealer_platform_id")):
        n = cur.execute(f"SELECT count(*) FROM {t} WHERE {col}=?", (zp,)).fetchone()[0]
        w(f"    {t:16} = {n}")
    oid_sub = "SELECT order_id FROM order_header WHERE dealer_platform_id=?"
    for t in ("order_line", "fulfillment"):
        n = cur.execute(f"SELECT count(*) FROM {t} WHERE order_id IN ({oid_sub})", (zp,)).fetchone()[0]
        w(f"    {t:16} = {n}")
    w(f"    downstream_order_no 非空 = {cur.execute('SELECT count(*) FROM order_header WHERE dealer_platform_id=? AND downstream_order_no IS NOT NULL', (zp,)).fetchone()[0]}")
    # 主数据键唯一性
    dupc = cur.execute("SELECT platform_customer_no,count(*) c FROM customer WHERE dealer_platform_id=? GROUP BY platform_customer_no HAVING c>1", (zp,)).fetchall()
    dupp = cur.execute("SELECT platform_product_no,count(*) c FROM product WHERE dealer_platform_id=? GROUP BY platform_product_no HAVING c>1", (zp,)).fetchall()
    w(f"    [验证#5] 客户复合键重复组={len(dupc)}  商品编号重复组={len(dupp)}  (应均为0)")
    dupbc = cur.execute("SELECT barcode,count(*) c FROM product WHERE dealer_platform_id=? AND barcode IS NOT NULL AND barcode<>'' GROUP BY barcode HAVING c>1", (zp,)).fetchall()
    w(f"    [风险#6] 商品条码重复组={len(dupbc)}  样例={dupbc[:3]}")

w(f"\n[验证#10] RAW 血缘: raw_file 登记={len(RAW_ROWS)} 行 (应=12: 2主数据+8SXD+2XD), header_row 均={HR}")
for fn, mod, sig, sheet, hr, nr in RAW_ROWS:
    w(f"    [{mod:5}] {fn}  sig={sig} rows={nr} header_row={hr}")

w("\n[验证#11] 未映射列汇总(应为空或仅确认无需入库的列):")
w(f"    客户资料: {unmappedC}")
w(f"    商品资料: {unmappedP}")
for fn, (nc, nr, um) in per_file_unmapped.items():
    if um:
        w(f"    订单明细/{fn}: {um}")
w("    订单履约: 见步骤5各文件行")

w("\n" + "=" * 78)
w("完成. 模式 =", "REAL(已写库并commit)" if REAL else "DRY(未写库)")
w("报告 ->", REPORT)
con.close()
rep.close()
