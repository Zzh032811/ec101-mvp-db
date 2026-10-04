# -*- coding: utf-8 -*-
"""EC101 MVP 接入 — 优惠券(定向优惠券)模块接入.
前置: 已运行 ingest_manjian.py + ingest_manzeng.py(客户/商品/订单已加载).
范围(本次): ① 注册券类3个文件的 RAW 血缘; ② 把"活动明细"载入 coupon_ledger(字符串单号,精度保住);
            ③ 解析 customer_id; ④ 验证 use_order_no -> order_header 关联(精度修复的端到端证据).
不做(避免猜测): 不杜撰券活动规则/理论优惠核算 —— 新导出"活动明细"仅1条且为测试券(test1/可口可乐客户测试),
            无结构化券规则(门槛/面额),按"只报告不猜测"原则,券类 entitlement/fee 暂不计算,记质量台账说明.
幂等: 按 dealer+batch_code 作用域清理后重载.
"""
import os, sys, sqlite3
from datetime import datetime
sys.path.insert(0, os.path.dirname(__file__))
from readers import read_table, to_num, to_datetime_text
from migrate_coupon_core import load_coupon_activities, migrate_schema

MVP   = r"D:\Peggy zhan\智能EC101\数据底座\第三阶段数据库设计\mvp"
BASE  = r"D:\Peggy zhan\智能EC101\数据底座\第三阶段数据库设计\快马-兴路强-试点"
DB    = os.path.join(MVP, "ec101_mvp.db")
REPORT= os.path.join(MVP, "ingest_report_coupon.txt")

F_ACT   = os.path.join(BASE, "优惠券", "快马-兴路强-优惠券-test1优惠券-活动明细-20260909-20260912.xls")
F_ORDER = os.path.join(BASE, "优惠券", "快马-兴路强-优惠券-test1优惠券-订单明细-20260909-20260912.xls")
F_SALES = os.path.join(BASE, "优惠券", "快马-兴路强-优惠券-test1优惠券-销售明细-20260909-20260912.xlsx")

BATCH_CODE = "KM-XLQ-YHQ-20260909-20260912"
DEALER     = "深圳市兴路强商贸有限公司"
PLATFORM   = "快马"

rep = open(REPORT, "w", encoding="utf-8")
def w(*a):
    s = " ".join(str(x) for x in a); print(s); rep.write(s + "\n")
def r2(x):
    return None if x is None else round(float(x) + 0.0, 2)
def cell(row, idx, default=""):
    if idx is None or idx < 0 or idx >= len(row): return default
    v = row[idx]; return v if v is not None else default

con = sqlite3.connect(DB); con.execute("PRAGMA foreign_keys = ON"); cur = con.cursor()
migrate_schema(con)

# 1. 幂等清理(券类作用域): coupon_ledger 按 dealer; raw 批次按 batch_code
cur.execute("SELECT dealer_platform_id FROM dealer_platform WHERE dealer_name=? AND platform_name=?", (DEALER, PLATFORM))
DP = cur.fetchone()[0]
cur.execute("DELETE FROM coupon_ledger WHERE dealer_platform_id=?", (DP,))
cur.execute("SELECT batch_id FROM raw_import_batch WHERE batch_code=?", (BATCH_CODE,))
for (b,) in cur.fetchall():
    cur.execute("DELETE FROM raw_file WHERE batch_id=?", (b,))
    cur.execute("DELETE FROM raw_import_batch WHERE batch_id=?", (b,))
cur.execute("SELECT calc_batch_id FROM result_calc_batch WHERE operator LIKE ?", ("优惠券%",))
for (cb,) in cur.fetchall():
    cur.execute("DELETE FROM result_quality_issue WHERE calc_batch_id=?", (cb,))
    cur.execute("DELETE FROM result_calc_batch WHERE calc_batch_id=?", (cb,))
con.commit()

# 2. RAW 血缘
NOW = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
cur.execute("INSERT INTO raw_import_batch(batch_code,source_platform,dealer_name,imported_at,operator) VALUES(?,?,?,?,?)",
            (BATCH_CODE, PLATFORM, DEALER, NOW, "优惠券接入"))
BATCH = cur.lastrowid
def reg_file(fname, module, path):
    sig, sheet, hdr, rows = read_table(path)
    cur.execute("INSERT INTO raw_file(batch_id,file_name,module,file_signature,read_method,sheet_name,header_row,data_rows) VALUES(?,?,?,?,?,?,?,?)",
                (BATCH, fname, module, sig, "readers.read_table", sheet, 1, len(rows)))
    return sig, sheet, hdr, rows
w("== 0. 优惠券接入 == batch_id=", BATCH, " dealer_platform_id=", DP)
sig_a, sh_a, HDR_A, ROWS_A = reg_file(os.path.basename(F_ACT),   "活动明细", F_ACT)
sig_o, sh_o, HDR_O, ROWS_O = reg_file(os.path.basename(F_ORDER), "订单",     F_ORDER)
sig_s, sh_s, HDR_S, ROWS_S = reg_file(os.path.basename(F_SALES), "销售",     F_SALES)
for t, s, sh, n in [("活动明细", sig_a, sh_a, len(ROWS_A)), ("订单", sig_o, sh_o, len(ROWS_O)), ("销售", sig_s, sh_s, len(ROWS_S))]:
    w(f"  {t}: sig={s} sheet={sh} 行={n}")

# 3. 客户索引
cust_id_by_no = {no: i for (no, i) in cur.execute("SELECT platform_customer_no,customer_id FROM customer WHERE dealer_platform_id=?", (DP,))}

# 4. 载入 coupon_ledger(活动明细)
ai = {h: i for i, h in enumerate(HDR_A)}
loaded = 0; cust_unmatched = []
link_rows = []
for r in ROWS_A:
    cno = str(cell(r, ai.get("优惠券编号"))).strip()
    if not cno: continue
    cust_no = str(cell(r, ai.get("客户编号"))).strip()
    cid = cust_id_by_no.get(cust_no)
    if cid is None and cust_no: cust_unmatched.append(cust_no)
    use_no = str(cell(r, ai.get("使用订单号"))).strip()
    use_t  = to_datetime_text(cell(r, ai.get("使用时间")))
    fee_month = use_t[:7] if use_t and len(use_t) >= 7 else None
    cur.execute("""INSERT INTO coupon_ledger(dealer_platform_id,coupon_no,coupon_name,customer_id,salesperson_name,
        receive_time,use_period,coupon_status,use_time,use_order_no,discount_amount,fee_month)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
        (DP, cno, str(cell(r, ai.get("优惠券名称"))).strip(), cid, str(cell(r, ai.get("所属业务员"))).strip(),
         to_datetime_text(cell(r, ai.get("领取时间"))), str(cell(r, ai.get("使用期限"))).strip(),
         str(cell(r, ai.get("状态"))).strip(), use_t, use_no,
         r2(to_num(cell(r, ai.get("优惠金额")))), fee_month))
    loaded += 1
    link_rows.append((cno, use_no))
w("\n== 1. coupon_ledger == 载入=", loaded, " 客户未匹配=", len(cust_unmatched), cust_unmatched[:5])
coupon_summary = load_coupon_activities(con, os.path.join(BASE, "优惠券"))
w("  券活动配置:", coupon_summary)

# 5. 关联验证: use_order_no -> order_header(精度修复端到端证据)
linked = 0; unlinked = []
for cno, use_no in link_rows:
    if not use_no: continue
    row = cur.execute("SELECT order_id,order_no,order_time,order_status FROM order_header WHERE dealer_platform_id=? AND order_no=?", (DP, use_no)).fetchone()
    if row:
        linked += 1
        w(f"  [OK] 券{cno} 使用订单号={use_no}(len={len(use_no)}) -> order_id={row[0]} 状态={row[3]} 下单={row[2]}")
    else:
        unlinked.append(use_no)
        w(f"  [NO] 券{cno} 使用订单号={use_no} 在 order_header 未找到")
w("== 2. 券->订单关联 == 命中=", linked, " 未命中=", len(unlinked), unlinked[:5])

# 6. RESULT: 计算批次 + 质量台账(说明券类核算暂不可行)
cur.execute("INSERT INTO result_calc_batch(calc_date,rule_version,input_batch_id,operator,created_at) VALUES(?,?,?,?,?)",
            ("2026-09-22", "v1", BATCH, "优惠券接入", NOW))
CB = cur.lastrowid
def issue(typ, lvl, reason):
    cur.execute("INSERT INTO result_quality_issue(order_no,issue_type,level,reason,evidence_ref,calc_batch_id) VALUES(?,?,?,?,?,?)",
                (None, typ, lvl, reason, "优惠券", CB))
issue("优惠券数据已按文本重导,精度阻断解除", "提示",
      f"新导出使用订单号为完整22位文本(如{link_rows[0][1] if link_rows else 'NA'}),券->订单关联命中{linked}笔;coupon_ledger已填充{loaded}条")
issue("券类理论优惠核算暂不可行", "警告",
      "本次定向优惠券活动明细仅1条且为测试券(test1/可口可乐客户测试/优惠200),无结构化券规则(门槛/面额/适用商品),"
      "按只报告不猜测原则,未建券活动/未算entitlement/fee;待平台提供真实券活动配置与全量领用数据后再核算")
w("\n== 3. RESULT == calc_batch_id=", CB, " 质量台账=2(精度解除提示 + 券核算暂不可行警告)")

con.commit()
w("\n== 4. 汇总 ==")
for t in ["coupon_ledger", "raw_import_batch", "raw_file", "result_calc_batch", "result_quality_issue"]:
    w(f"  {t}:", cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0])
w("  coupon_ledger 明细:", cur.execute("SELECT coupon_id,coupon_no,coupon_name,customer_id,coupon_status,use_order_no,discount_amount,fee_month FROM coupon_ledger").fetchall())
w("  FK violations:", cur.execute("PRAGMA foreign_key_check").fetchall())
con.close(); rep.close()
