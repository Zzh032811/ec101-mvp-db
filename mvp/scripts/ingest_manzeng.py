# -*- coding: utf-8 -*-
"""EC101 MVP 接入 — 满赠(满赠优惠)追加接入.
前置: 已运行 ingest_manjian.py(重建库+满减). 本脚本在现有库上追加满赠, 不重建.
权益口径: 满赠无金额优惠(促销优惠金额=0), 权益=赠品数(抱枕348721357×1/单, 每用户限购1).
赠品执行证据=订单明细中商品编号348721357的赠品行. 结算单价未确认(主数据成本价0/批发价99为标价)→记Gap.
"""
import os, sys, sqlite3
from collections import defaultdict, Counter
from datetime import datetime
sys.path.insert(0, os.path.dirname(__file__))
from readers import read_table, to_num, to_datetime_text

MVP   = r"D:\Peggy zhan\智能EC101\数据底座\第三阶段数据库设计\mvp"
BASE  = r"D:\Peggy zhan\智能EC101\数据底座\第三阶段数据库设计\快马-兴路强-试点"
DB    = os.path.join(MVP, "ec101_mvp.db")
REPORT= os.path.join(MVP, "ingest_report_manzeng.txt")

F_ORDER = os.path.join(BASE, "满赠", "快马-兴路强-满赠-订单明细-20260819-20260831.xls")
F_ACT   = os.path.join(BASE, "满赠", "快马-兴路强-满赠-活动明细-20260819-20260831.xls")
F_SALES = os.path.join(BASE, "满赠", "快马-兴路强-满赠-销售明细-20260819-20260831.xls")
F_SCOPE = os.path.join(BASE, "满赠", "满赠指定商品列表.xlsx")   # 18个雪碧SKU(编号=platform_product_no)
GIFT_NO = "348721357"

BATCH_CODE = "KM-XLQ-MZ-20260819-20260831"
CALC_DATE  = "2026-09-22"
T2_CUTOFF  = "2026-09-20 00:00:00"
ACT_NAME   = "满赠优惠"
ACT_START  = "2026-08-19 15:15:00"
ACT_END    = "2026-08-31 23:59:00"
THRESHOLD  = 100.0
GIFT_QTY   = 1

rep = open(REPORT, "w", encoding="utf-8")
def w(*a):
    s = " ".join(str(x) for x in a); print(s); rep.write(s + "\n")
def r2(x):
    return None if x is None else round(float(x) + 0.0, 2)
def cell(row, idx, default=""):
    if idx is None or idx < 0 or idx >= len(row): return default
    v = row[idx]; return v if v is not None else default

con = sqlite3.connect(DB); con.execute("PRAGMA foreign_keys = ON"); cur = con.cursor()

# 0. 确保赠品列存在(兼容旧DDL建的库)
def has_col(t, c):
    return any(r[1] == c for r in cur.execute(f"PRAGMA table_info({t})"))
if not has_col("order_activity", "gift_qty_actual"):
    cur.execute("ALTER TABLE order_activity ADD COLUMN gift_qty_actual NUMERIC")
if not has_col("result_entitlement", "gift_qty_entitled"):
    cur.execute("ALTER TABLE result_entitlement ADD COLUMN gift_qty_entitled NUMERIC")
    cur.execute("ALTER TABLE result_entitlement ADD COLUMN gift_qty_actual NUMERIC")
con.commit()

# 1. 幂等清理(满赠作用域)
cur.execute("SELECT activity_id FROM activity WHERE activity_name=?", (ACT_NAME,))
row = cur.fetchone()
if row:
    aid = row[0]
    cur.execute("DELETE FROM result_entitlement WHERE order_activity_id IN (SELECT order_activity_id FROM order_activity WHERE activity_id=?)", (aid,))
    cur.execute("DELETE FROM result_fee WHERE activity_id=?", (aid,))
    cur.execute("DELETE FROM order_activity WHERE activity_id=?", (aid,))
    cur.execute("DELETE FROM activity_scope WHERE activity_id=?", (aid,))
    cur.execute("DELETE FROM activity_rule_benefit WHERE rule_id IN (SELECT rule_id FROM activity_rule WHERE activity_id=?)", (aid,))
    cur.execute("DELETE FROM activity_rule WHERE activity_id=?", (aid,))
    cur.execute("DELETE FROM activity WHERE activity_id=?", (aid,))
cur.execute("SELECT calc_batch_id FROM result_calc_batch WHERE operator LIKE ?", ("满赠%",))
for (cb,) in cur.fetchall():
    cur.execute("DELETE FROM result_release_candidate WHERE calc_batch_id=?", (cb,))
    cur.execute("DELETE FROM result_quality_issue WHERE calc_batch_id=?", (cb,))
    cur.execute("DELETE FROM result_calc_batch WHERE calc_batch_id=?", (cb,))
cur.execute("SELECT batch_id FROM raw_import_batch WHERE batch_code=?", (BATCH_CODE,))
for (b,) in cur.fetchall():
    cur.execute("DELETE FROM raw_file WHERE batch_id=?", (b,))
    cur.execute("DELETE FROM raw_import_batch WHERE batch_id=?", (b,))
con.commit()

NOW = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
cur.execute("INSERT INTO raw_import_batch(batch_code,source_platform,dealer_name,imported_at,operator) VALUES(?,?,?,?,?)",
            (BATCH_CODE, "快马", "深圳市兴路强商贸有限公司", NOW, "满赠接入"))
BATCH = cur.lastrowid
def reg_file(fname, module, path):
    sig, sheet, hdr, rows = read_table(path)
    cur.execute("INSERT INTO raw_file(batch_id,file_name,module,file_signature,read_method,sheet_name,header_row,data_rows) VALUES(?,?,?,?,?,?,?,?)",
                (BATCH, fname, module, sig, "readers.read_table", sheet, 1, len(rows)))
    return sig, sheet, hdr, rows
w("== 0. 满赠追加 == batch_id=", BATCH)
sig_o, sh_o, HDR_O, ROWS_O = reg_file(os.path.basename(F_ORDER), "订单", F_ORDER)
sig_a, sh_a, HDR_A, ROWS_A = reg_file(os.path.basename(F_ACT),   "活动明细", F_ACT)
sig_s, sh_s, HDR_S, ROWS_S = reg_file(os.path.basename(F_SALES), "销售", F_SALES)
for t, s, sh, n in [("订单", sig_o, sh_o, len(ROWS_O)), ("活动明细", sig_a, sh_a, len(ROWS_A)), ("销售", sig_s, sh_s, len(ROWS_S))]:
    w(f"  {t}: sig={s} sheet={sh} 行={n}")

cur.execute("SELECT dealer_platform_id FROM dealer_platform WHERE dealer_name=? AND platform_name=?",
            ("深圳市兴路强商贸有限公司", "快马"))
DP = cur.fetchone()[0]

# 2. 基础查找表(客户/商品 已由满减加载; 这里仅取索引)
cust_id_by_no = {no: i for (no, i) in cur.execute("SELECT platform_customer_no,customer_id FROM customer WHERE dealer_platform_id=?", (DP,))}
prod_id_by_no = {no: i for (no, i) in cur.execute("SELECT platform_product_no,product_id FROM product WHERE dealer_platform_id=?", (DP,))}
prod_id_by_bc = {}
for (bc, i) in cur.execute("SELECT barcode,product_id FROM product WHERE dealer_platform_id=? AND barcode<>''", (DP,)):
    prod_id_by_bc.setdefault(bc.strip(), i)
GIFT_PID = prod_id_by_no.get(GIFT_NO)
w("\n== 1. 基础 == dealer=", DP, " 赠品product_id=", GIFT_PID)

# 3. 订单头/订单行(新增08-19~08-30; 08-31与满减重叠用 OR IGNORE)
oi = {h: i for i, h in enumerate(HDR_O)}
order_meta = {}
for r in ROWS_O:
    no = cell(r, oi.get("订单编号")).strip()
    if not no or no in order_meta: continue
    order_meta[no] = dict(time=to_datetime_text(cell(r, oi.get("下单时间"))), cust=cell(r, oi.get("客户编号")).strip(),
        status=cell(r, oi.get("订单状态")).strip(), pay=cell(r, oi.get("支付方式")).strip(),
        payst=cell(r, oi.get("支付状态")).strip(), src=cell(r, oi.get("订单来源")).strip(), otype=cell(r, oi.get("订单类型")).strip())
new_orders = 0
order_id_by_no = {}
for no in order_meta:
    cur.execute("SELECT order_id FROM order_header WHERE dealer_platform_id=? AND order_no=?", (DP, no))
    ex = cur.fetchone()
    if ex:
        order_id_by_no[no] = ex[0]
    else:
        m = order_meta[no]
        cur.execute("INSERT INTO order_header(dealer_platform_id,order_no,order_time,customer_id,order_status,pay_method,pay_status,order_source,order_type,batch_id) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (DP, no, m["time"], cust_id_by_no.get(m["cust"]), m["status"], m["pay"], m["payst"], m["src"], m["otype"], BATCH))
        order_id_by_no[no] = cur.lastrowid; new_orders += 1
w("== 2. order_header == 满赠文件唯一订单=", len(order_meta), " 新增=", new_orders, " 复用(与满减重叠)=", len(order_meta) - new_orders)

line_agg = {}
for r in ROWS_O:
    no = cell(r, oi.get("订单编号")).strip()
    if not no: continue
    oid = order_id_by_no.get(no)
    pno = cell(r, oi.get("商品编号")).strip(); bc = cell(r, oi.get("商品条码")).strip()
    pid = prod_id_by_no.get(pno) or prod_id_by_bc.get(bc)
    key = (oid, pid if pid else ("RAW:" + (pno or bc)))
    v = dict(qty=to_num(cell(r, oi.get("订货数量"))) or 0.0, qunit=cell(r, oi.get("订货数量单位")).strip(),
             bqty=to_num(cell(r, oi.get("基本单位数量"))) or 0.0, bunit=cell(r, oi.get("基本单位")).strip(),
             pre=to_num(cell(r, oi.get("优惠前金额"))) or 0.0, disc=to_num(cell(r, oi.get("优惠金额"))) or 0.0,
             price=to_num(cell(r, oi.get("订货单价"))), pid=pid)
    if key in line_agg:
        for k in ("qty", "bqty", "pre", "disc"): line_agg[key][k] += v[k]
    else:
        line_agg[key] = v
new_lines = 0
for (oid, pk), v in line_agg.items():
    cur.execute("SELECT 1 FROM order_line WHERE order_id=? AND (product_id IS ? OR product_id=?)", (oid, v["pid"], v["pid"]))
    if cur.fetchone(): continue
    cur.execute("INSERT INTO order_line(order_id,product_id,order_qty,order_unit,base_qty,base_unit,pre_discount_amount,discount_amount,unit_price) VALUES(?,?,?,?,?,?,?,?,?)",
        (oid, v["pid"], r2(v["qty"]), v["qunit"], r2(v["bqty"]), v["bunit"], r2(v["pre"]), r2(v["disc"]), r2(v["price"])))
    new_lines += 1
w("== 2b. order_line == 新增行=", new_lines)

# 履约(仅新增订单)
for no, oid in order_id_by_no.items():
    cur.execute("SELECT 1 FROM fulfillment WHERE order_id=?", (oid,))
    if cur.fetchone(): continue
    m = order_meta[no]; completed = (m["status"] == "已完成")
    cur.execute("INSERT INTO fulfillment(order_id,order_status,completed_at,t2_release_candidate) VALUES(?,?,?,?)",
        (oid, m["status"], m["time"] if completed else None, 1 if (completed and m["time"] and m["time"] <= T2_CUTOFF) else 0))

# 4. 活动/规则/权益/范围
# 满赠不走 TPM（2026-09-22 业务决策）：activity.tpm_id 与 result_fee.tpm_id 均置 NULL
TPM = None
cur.execute("""INSERT INTO activity(dealer_platform_id,tpm_id,activity_name,activity_category,promo_method,
    promotion_type,product_scope_type,purchase_limit_type,purchase_limit_value,customer_scope_type,use_device,
    limit_recharge_gift,start_time,end_time,use_scene,allow_stack,allow_coupon,min_sku_count,activity_status,rule_version)
    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
    (DP, TPM, ACT_NAME, "非券类", "阶梯", "满一定金额立赠", "指定商品", "每用户限购", GIFT_QTY,
     "指定客户类型", "不限", "关闭", ACT_START, ACT_END, "客户自下单可用", "是", "是", 0, "已结束", "v1"))
ACT = cur.lastrowid
cur.execute("INSERT INTO activity_rule(activity_id,tier_no,threshold_type,threshold_value,reduce_amount,free_shipping) VALUES(?,?,?,?,?,?)",
    (ACT, 1, "金额", THRESHOLD, 0, 0))
RULE = cur.lastrowid
cur.execute("INSERT INTO activity_rule_benefit(rule_id,benefit_type,gift_product_no,gift_product_name,gift_qty) VALUES(?,?,?,?,?)",
    (RULE, "赠品", GIFT_NO, "雪碧 冰丝抱枕（赠品勿下）", GIFT_QTY))
# 满赠指定商品清单(2026-09-22业务决策已拿到): 18个雪碧SKU, 编号=platform_product_no(字符串, P8)
sig_sc, sheet_sc, hdr_sc, rows_sc = read_table(F_SCOPE)
ix_sc = {h: i for i, h in enumerate(hdr_sc)}
scope_n = 0
for r in rows_sc:
    no = cell(r, ix_sc.get("编号")).strip()
    if not no: continue
    cur.execute("INSERT INTO activity_scope(activity_id,scope_category,scope_dimension,scope_value) VALUES(?,?,?,?)",
                (ACT, "商品", "商品", no))
    scope_n += 1
for ct in ["西乡", "零售", "线下付款客户", "闪电仓", "可口可乐业务"]:
    cur.execute("INSERT INTO activity_scope(activity_id,scope_category,scope_dimension,scope_value) VALUES(?,?,?,?)",
                (ACT, "客户", "类型", ct))
w("\n== 3. activity == id=", ACT, " 满赠优惠 满100立赠抱枕x1 指定商品", scope_n, "项 限购1 客户类型5项")

# 5. 赠品实际发放数(按订单, 来自赠品行)
gift_qty_by_order = defaultdict(float)
for (oid, q) in cur.execute("SELECT order_id, SUM(order_qty) FROM order_line WHERE product_id=? GROUP BY order_id", (GIFT_PID,)):
    gift_qty_by_order[oid] = q
gift_order_nos = {no for no, oid in order_id_by_no.items() if gift_qty_by_order.get(oid)}

# 6. order_activity(活动明细按订单聚合)
ai = {h: i for i, h in enumerate(HDR_A)}
agg = defaultdict(lambda: dict(amt=0.0, disc=0.0, pol=""))
for r in ROWS_A:
    no = cell(r, ai.get("订单号")).strip()
    if not no: continue
    g = agg[no]
    g["amt"] += to_num(cell(r, ai.get("商品总金额"))) or 0.0
    g["disc"] += to_num(cell(r, ai.get("促销优惠金额"))) or 0.0
    if not g["pol"]: g["pol"] = cell(r, ai.get("享受促销政策")).strip()
oa_by_order = {}
unmatched = []
for no, g in agg.items():
    oid = order_id_by_no.get(no)
    if not oid: unmatched.append(no); continue
    cur.execute("""INSERT INTO order_activity(order_id,activity_id,rule_id,activity_product_amount,
        platform_actual_benefit,gift_qty_actual,policy_text,exec_status,evidence_ref) VALUES(?,?,?,?,?,?,?,?,?)""",
        (oid, ACT, RULE, r2(g["amt"]), r2(g["disc"]), gift_qty_by_order.get(oid, 0), g["pol"], "已执行", "活动明细HTML+赠品行"))
    oa_by_order[no] = cur.lastrowid
orphan_gifts = gift_order_nos - set(oa_by_order.keys())
w("== 4. order_activity == 活动明细订单=", len(agg), " 入库=", len(oa_by_order), " 未匹配=", len(unmatched),
  " 孤儿赠品行订单(有赠品无活动明细)=", len(orphan_gifts), sorted(orphan_gifts)[:5])

# 7. RESULT
cur.execute("INSERT INTO rule_catalog(rule_topic,version,effective_from,confirmed_by,scope,rule_text) VALUES(?,?,?,?,?,?)",
    ("满赠权益重算", "v1", CALC_DATE, "截图配置(满赠优惠)", "快马-兴路强-满赠",
     "满100立赠抱枕x1(每用户限购1);权益=赠品数非金额(促销优惠金额=0);应赠=1/合格单,实赠=订单明细赠品行数量"))
cur.execute("INSERT INTO result_calc_batch(calc_date,rule_version,input_batch_id,operator,created_at) VALUES(?,?,?,?,?)",
    (CALC_DATE, "v1", BATCH, "满赠接入", NOW))
CB = cur.lastrowid
w("\n== 5. RESULT == calc_batch_id=", CB)

ent = cons_ok = cons_bad = 0
sum_gift_ent = sum_gift_act = 0.0
not_completed = []
for no, oa in oa_by_order.items():
    oid = order_id_by_no[no]; g = agg[no]
    tm = order_meta[no]["time"]; st = order_meta[no]["status"]
    in_window = bool(tm and ACT_START <= tm <= ACT_END)
    entitled = GIFT_QTY if (g["amt"] >= THRESHOLD - 1e-9 and in_window) else 0
    actual = gift_qty_by_order.get(oid, 0)
    cons = "一致" if abs(entitled - actual) < 1e-9 else "差异"
    cur.execute("""INSERT INTO result_entitlement(order_activity_id,theoretical_benefit,platform_actual_benefit,
        gift_qty_entitled,gift_qty_actual,consistency,diff_amount,formula_ref,calc_batch_id) VALUES(?,?,?,?,?,?,?,?,?)""",
        (oa, 0.0, r2(g["disc"]), entitled, actual, cons, r2(actual - entitled), "满100立赠x1;实赠=赠品行", CB))
    ent += 1; sum_gift_ent += entitled; sum_gift_act += actual
    if cons == "一致": cons_ok += 1
    else: cons_bad += 1
    if st != "已完成": not_completed.append((no, st, tm))
w("== 5a. result_entitlement == 计=", ent, " 一致=", cons_ok, " 差异=", cons_bad,
  " Σ应赠=", sum_gift_ent, " Σ实赠=", sum_gift_act)

cand_yes = cand_no = 0
for no, oa in oa_by_order.items():
    oid = order_id_by_no[no]; tm = order_meta[no]["time"]; st = order_meta[no]["status"]
    is_c = 1 if (st == "已完成" and tm and tm <= T2_CUTOFF) else 0
    cur.execute("INSERT OR IGNORE INTO result_release_candidate(order_id,calc_date,is_candidate,reason,calc_batch_id) VALUES(?,?,?,?,?)",
        (oid, CALC_DATE, is_c, "已完成且≤T-2" if is_c else f"未达释放节点(状态={st})", CB))
    cand_yes += is_c; cand_no += (1 - is_c)
w("== 5b. release == 可释放=", cand_yes, " 暂不可释放=", cand_no)

# 费用: 满赠无金额优惠; 不结算单价, 只按赠品数量统计(2026-09-22业务决策); 不走TPM
SETTLE_STATUS = "按赠品数量统计(不结算单价)"
cur.execute("""INSERT INTO result_fee(tpm_id,activity_id,actual_discount_total,gift_cost_total,fee_bearer,
    settle_target,budget_amount,budget_reserve_no,settle_amount,diff_amount,settle_status,calc_batch_id)
    VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
    (TPM, ACT, 0.0, 0.0, "渠道市场部(发票抬头:装瓶厂)", "深圳市兴路强商贸有限公司",
     None, None, 0.0, None, SETTLE_STATUS, CB))
w("== 5c. result_fee == 金额优惠=0 赠品结算基础(数)=", sum_gift_act, " 不结算单价 金额=0 状态=", SETTLE_STATUS, " tpm_id=NULL(不走TPM)")

qi = 0
def issue(no, typ, lvl, reason):
    global qi
    cur.execute("INSERT INTO result_quality_issue(order_no,issue_type,level,reason,evidence_ref,calc_batch_id) VALUES(?,?,?,?,?,?)",
                (no, typ, lvl, reason, "满赠", CB)); qi += 1
for no in sorted(orphan_gifts):
    issue(no, "赠品已发但无活动明细记录", "警告", "订单明细存在赠品行但活动明细无该单,参与台账缺口")
for no, st, tm in not_completed:
    issue(no, "权益已计未达释放节点", "提示", f"订单状态={st}")
# 2026-09-22 业务决策已关闭：赠品不结算单价(只统计数量)、满赠不走TPM、18个指定商品已落 activity_scope —— 原三条质量台账不再记录
w("== 5d. quality_issue == 记录=", qi)

con.commit()
w("\n== 6. 汇总 ==")
for t in ["order_header", "order_line", "activity", "order_activity", "result_entitlement", "result_release_candidate", "result_fee", "result_quality_issue"]:
    w(f"  {t}: {cur.execute('SELECT count(*) FROM ' + t).fetchone()[0]}")
w("FK violations:", cur.execute("PRAGMA foreign_key_check").fetchall())
con.close(); rep.close()
print("\nREPORT ->", REPORT)
