# -*- coding: utf-8 -*-
"""EC101 MVP 接入 — 满减(可口可乐满减)全流程.
重建库 -> RAW登记 -> CORE(客户/商品/订单/订单行/TPM/活动/订单活动/履约)
-> RESULT(规则目录/计算批/理论权益/T-2候选/费用结算/质量问题).
所有控制数写入 UTF-8 报告 ingest_report.txt.
"""
import os, sys, sqlite3
from collections import defaultdict, Counter
from datetime import datetime
sys.path.insert(0, os.path.dirname(__file__))
from readers import read_table, to_num, to_datetime_text
from promotion_calculator import calculate_activity

MVP   = r"D:\Peggy zhan\智能EC101\数据底座\第三阶段数据库设计\mvp"
BASE  = r"D:\Peggy zhan\智能EC101\数据底座\第三阶段数据库设计\快马-兴路强-试点"
DB    = os.path.join(MVP, "ec101_mvp.db")
DDL   = os.path.join(MVP, "ddl", "ec101_mvp_sqlite.sql")
REPORT= os.path.join(MVP, "ingest_report.txt")

F_ORDER = os.path.join(BASE, "满减", "快马-兴路强-满减-订单明细-20260831-20260917.xls")
F_SALES = os.path.join(BASE, "满减", "快马-兴路强-满减-销售明细-20260831-20260917.xlsx")
F_ACT   = os.path.join(BASE, "满减", "快马-兴路强-满减-活动明细-20260831-20260917.xls")
F_CUST  = os.path.join(BASE, "User-202609221722.xlsx")   # 客户主数据 9/22 快照(2292客户); 旧 9/14 快照(2273)缺 2 个 9/16 下单客户已补齐
F_PROD  = os.path.join(BASE, "Product-202609141043.xlsx")  # 商品主数据 9/14 快照(9129商品), 仅文件名变更内容不变

CALC_DATE   = "2026-09-22"
T2_CUTOFF   = "2026-09-20 00:00:00"   # 计算日 T-2
ACT_START   = "2026-08-31 10:58:00"
ACT_END     = "2026-09-17 23:59:00"
THRESHOLD   = 300.0
REDUCE      = 15.0
BUDGET      = 30000.0

rep = open(REPORT, "w", encoding="utf-8")
def w(*a):
    s = " ".join(str(x) for x in a)
    print(s); rep.write(s + "\n")

def r2(x):
    return None if x is None else round(float(x) + 0.0, 2)

def cell(row, idx, default=""):
    if idx is None or idx < 0 or idx >= len(row):
        return default
    v = row[idx]
    return v if v is not None else default

# ============ 0. 重建库 ============
if os.path.exists(DB):
    os.remove(DB)
con = sqlite3.connect(DB)
con.execute("PRAGMA foreign_keys = ON")
with open(DDL, encoding="utf-8") as f:
    con.executescript(f.read())
con.commit()
cur = con.cursor()
w("== 0. 库重建 ==", "tables=",
  cur.execute("SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()[0])

NOW = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# ============ 1. RAW 登记 ============
cur.execute("INSERT INTO raw_import_batch(batch_code,source_platform,dealer_name,imported_at,operator) VALUES(?,?,?,?,?)",
            ("KM-XLQ-MJ-20260831-20260917", "快马", "深圳市兴路强商贸有限公司", NOW, "小凡"))
BATCH = cur.lastrowid

def reg_file(fname, module, path):
    sig, sheet, hdr, rows = read_table(path)
    cur.execute("""INSERT INTO raw_file(batch_id,file_name,module,file_signature,read_method,sheet_name,header_row,data_rows)
                   VALUES(?,?,?,?,?,?,?,?)""",
                (BATCH, fname, module, sig, "readers.read_table", sheet, 1, len(rows)))
    return sig, sheet, hdr, rows

w("\n== 1. RAW 登记 == batch_id=", BATCH)
sig_o, sh_o, HDR_O, ROWS_O = reg_file(os.path.basename(F_ORDER), "订单", F_ORDER)
sig_s, sh_s, HDR_S, ROWS_S = reg_file(os.path.basename(F_SALES), "销售", F_SALES)
sig_a, sh_a, HDR_A, ROWS_A = reg_file(os.path.basename(F_ACT),   "活动明细", F_ACT)
sig_c, sh_c, HDR_C, ROWS_C = reg_file(os.path.basename(F_CUST),  "客户", F_CUST)
sig_p, sh_p, HDR_P, ROWS_P = reg_file(os.path.basename(F_PROD),  "商品", F_PROD)
for tag, sig, sh, n in [("订单",sig_o,sh_o,len(ROWS_O)),("销售",sig_s,sh_s,len(ROWS_S)),
                         ("活动明细",sig_a,sh_a,len(ROWS_A)),("客户",sig_c,sh_c,len(ROWS_C)),
                         ("商品",sig_p,sh_p,len(ROWS_P))]:
    w(f"  {tag}: sig={sig} sheet={sh} 数据行={n}")

# ============ 2. dealer_platform ============
cur.execute("""INSERT INTO dealer_platform(dealer_name,platform_name,swire_partner_code,admission_status)
               VALUES(?,?,?,?)""", ("深圳市兴路强商贸有限公司", "快马", "0576259191", "已准入"))
DP = cur.lastrowid
w("\n== 2. dealer_platform == id=", DP)

# ============ 3. customer ============
ci = {h: i for i, h in enumerate(HDR_C)}
cust_rows = 0
for r in ROWS_C:
    no = cell(r, ci.get("客户编号")).strip()
    if not no:
        continue
    cur.execute("""INSERT OR IGNORE INTO customer(dealer_platform_id,platform_customer_no,customer_name,
        customer_type,customer_level,customer_tag,customer_region,salesperson_name,created_at,status)
        VALUES(?,?,?,?,?,?,?,?,?,?)""",
        (DP, no, cell(r, ci.get("客户名称")).strip(), cell(r, ci.get("客户类型")).strip(),
         cell(r, ci.get("客户等级")).strip(), cell(r, ci.get("客户标签")).strip(),
         cell(r, ci.get("客户区域")).strip(), cell(r, ci.get("所属业务员")).strip(),
         to_datetime_text(cell(r, ci.get("添加时间"))), cell(r, ci.get("状态")).strip()))
    cust_rows += 1
cust_id_by_no = {no: i for (no, i) in cur.execute(
    "SELECT platform_customer_no,customer_id FROM customer WHERE dealer_platform_id=?", (DP,))}
w("\n== 3. customer == 读取行=", cust_rows, " 入库唯一客户=", len(cust_id_by_no))

# ============ 4. product ============
pi = {h: i for i, h in enumerate(HDR_P)}
prod_rows = 0
for r in ROWS_P:
    no = cell(r, pi.get("商品编号")).strip()
    if not no:
        continue
    cur.execute("""INSERT OR IGNORE INTO product(dealer_platform_id,platform_product_no,product_name,
        brand,category,spec,barcode,base_unit,box_conversion,shelf_status,cost_avg_price,
        actual_stock,occupied_stock,available_stock)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (DP, no, cell(r, pi.get("商品名称")).strip(), cell(r, pi.get("品牌")).strip(),
         cell(r, pi.get("一级目录")).strip(), cell(r, pi.get("规格值1")).strip(),
         cell(r, pi.get("条形码")).strip(), cell(r, pi.get("单位")).strip(),
         cell(r, pi.get("换算关系1")).strip(), cell(r, pi.get("状态")).strip(),
         r2(to_num(cell(r, pi.get("成本价")))),
         r2(to_num(cell(r, pi.get("实际库存")))), r2(to_num(cell(r, pi.get("占用库存")))),
         r2(to_num(cell(r, pi.get("可用库存"))))))
    prod_rows += 1
prod_id_by_no = {no: i for (no, i) in cur.execute(
    "SELECT platform_product_no,product_id FROM product WHERE dealer_platform_id=?", (DP,))}
# 条码 -> product_id 兜底
prod_id_by_barcode = {}
for (bc, i) in cur.execute("SELECT barcode,product_id FROM product WHERE dealer_platform_id=? AND barcode<>''", (DP,)):
    prod_id_by_barcode.setdefault(bc.strip(), i)
w("\n== 4. product == 读取行=", prod_rows, " 入库唯一商品(按商品编号)=", len(prod_id_by_no),
  " 条码索引=", len(prod_id_by_barcode))

# ============ 5. order_header + order_line ============
oi = {h: i for i, h in enumerate(HDR_O)}
i_no=oi.get("订单编号"); i_time=oi.get("下单时间"); i_cust=oi.get("客户编号")
i_status=oi.get("订单状态"); i_pay=oi.get("支付方式"); i_payst=oi.get("支付状态")
i_src=oi.get("订单来源"); i_otype=oi.get("订单类型")
i_prod=oi.get("商品编号"); i_barcode=oi.get("商品条码")
i_qty=oi.get("订货数量"); i_qunit=oi.get("订货数量单位")
i_bqty=oi.get("基本单位数量"); i_bunit=oi.get("基本单位")
i_pre=oi.get("优惠前金额"); i_disc=oi.get("优惠金额"); i_price=oi.get("订货单价")

# 先建订单头(唯一订单号, 取首行属性)
order_meta = {}   # no -> dict
for r in ROWS_O:
    no = cell(r, i_no).strip()
    if not no or no in order_meta:
        continue
    order_meta[no] = dict(
        time=to_datetime_text(cell(r, i_time)), cust=cell(r, i_cust).strip(),
        status=cell(r, i_status).strip(), pay=cell(r, i_pay).strip(),
        payst=cell(r, i_payst).strip(), src=cell(r, i_src).strip(), otype=cell(r, i_otype).strip())

cust_hit = cust_miss = 0
order_id_by_no = {}
for no, m in order_meta.items():
    cid = cust_id_by_no.get(m["cust"])
    if cid: cust_hit += 1
    else:   cust_miss += 1
    cur.execute("""INSERT OR IGNORE INTO order_header(dealer_platform_id,order_no,order_time,customer_id,
        order_status,pay_method,pay_status,order_source,order_type,batch_id)
        VALUES(?,?,?,?,?,?,?,?,?,?)""",
        (DP, no, m["time"], cid, m["status"], m["pay"], m["payst"], m["src"], m["otype"], BATCH))
    order_id_by_no[no] = cur.lastrowid
w("\n== 5. order_header == 唯一订单=", len(order_id_by_no),
  " 客户匹配 hit=", cust_hit, " miss=", cust_miss)

# 订单行: 按(订单号,商品编号)聚合以尊重 UNIQUE(order_id,product_id)
line_agg = {}
prod_hit_no = prod_hit_bc = prod_miss = 0
merged_dup = 0
for r in ROWS_O:
    no = cell(r, i_no).strip()
    if not no:
        continue
    oid = order_id_by_no.get(no)
    pno = cell(r, i_prod).strip()
    bc  = cell(r, i_barcode).strip()
    pid = prod_id_by_no.get(pno)
    if pid: prod_hit_no += 1
    else:
        pid = prod_id_by_barcode.get(bc)
        if pid: prod_hit_bc += 1
        else:   prod_miss += 1
    key = (oid, pid if pid else ("RAW:"+ (pno or bc)))
    rec = line_agg.get(key)
    vals = dict(qty=to_num(cell(r,i_qty)) or 0.0, qunit=cell(r,i_qunit).strip(),
                bqty=to_num(cell(r,i_bqty)) or 0.0, bunit=cell(r,i_bunit).strip(),
                pre=to_num(cell(r,i_pre)) or 0.0, disc=to_num(cell(r,i_disc)) or 0.0,
                price=to_num(cell(r,i_price)), pid=pid)
    if rec is None:
        line_agg[key] = vals
    else:
        merged_dup += 1
        for k in ("qty","bqty","pre","disc"):
            rec[k] += vals[k]
line_rows = 0
for (oid, pk), v in line_agg.items():
    cur.execute("""INSERT OR IGNORE INTO order_line(order_id,product_id,order_qty,order_unit,base_qty,
        base_unit,pre_discount_amount,discount_amount,unit_price)
        VALUES(?,?,?,?,?,?,?,?,?)""",
        (oid, v["pid"], r2(v["qty"]), v["qunit"], r2(v["bqty"]), v["bunit"],
         r2(v["pre"]), r2(v["disc"]), r2(v["price"])))
    line_rows += 1
w("== 5b. order_line == 入库行=", line_rows, " 合并重复(订单,商品)=", merged_dup)
w("    商品匹配: 按商品编号 hit=", prod_hit_no, " 按条码兜底 hit=", prod_hit_bc, " miss=", prod_miss,
  f" 匹配率={(prod_hit_no+prod_hit_bc)/max(1,prod_hit_no+prod_hit_bc+prod_miss)*100:.1f}%")

# ============ 6. tpm_application ============
cur.execute("""INSERT INTO tpm_application(tpm_code,theme,promo_type,customer_scope,product_group,
    apply_amount,budget_reserve_no,target_volume_uc,target_revenue,target_customer_count,sales_org,
    marketing_org,bu,applicant,plan_owner,fee_pay_dept,invoice_title,plan_start,plan_end,
    release_start,release_end,closing_date,approval_status,tp_indicator)
    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
    ("DCN-9926018","EC101促销","DME市场营销活动-O","目标组 TG-13060-粤东所有售点","PS-13633-全系列",
     BUDGET,"3900088916",280000,587412,10,"广东","市场渠道部-粤东","粤东营运中心","卓梦宁","朴红禹",
     "渠道市场部","装瓶厂","2026-08-26","2026-10-31","2026-08-27","2027-01-29","2027-01-29",
     "已释放/已批准/审批通过","促销活动与订单无关"))
TPM = cur.lastrowid
w("\n== 6. tpm_application == id=", TPM, " 预算=", BUDGET, " 费用支付部门=渠道市场部 发票抬头=装瓶厂")

# ============ 7. activity + rule + benefit + scope ============
cur.execute("""INSERT INTO activity(dealer_platform_id,tpm_id,activity_name,activity_category,promo_method,
    promotion_type,product_scope_type,purchase_limit_type,purchase_limit_value,customer_scope_type,
    use_device,limit_recharge_gift,start_time,end_time,use_scene,allow_stack,allow_coupon,
    min_sku_count,activity_status,rule_version)
    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
    (DP, TPM, "可口可乐满减", "非券类", "阶梯", "满一定金额立减", "指定品牌", "每用户限购", 0,
     "指定客户类型", "不限", "关闭", ACT_START, ACT_END, "客户自下单可用", "是", "是", 0,
     "已结束", "v1"))
ACT = cur.lastrowid
cur.execute("""INSERT INTO activity_rule(activity_id,tier_no,threshold_type,threshold_value,reduce_amount,free_shipping)
               VALUES(?,?,?,?,?,?)""", (ACT, 1, "金额", THRESHOLD, REDUCE, 0))
RULE = cur.lastrowid
cur.execute("""INSERT INTO activity_rule_benefit(rule_id,benefit_type) VALUES(?,?)""", (RULE, "立减"))
# 范围: 商品=指定品牌可口可乐; 客户类型 6 项
cur.execute("INSERT INTO activity_scope(activity_id,scope_category,scope_dimension,scope_value) VALUES(?,?,?,?)",
            (ACT, "商品", "品牌", "可口可乐"))
for ct in ["测试类型","西乡","零售","线下付款客户","闪电仓","可口可乐业务"]:
    cur.execute("INSERT INTO activity_scope(activity_id,scope_category,scope_dimension,scope_value) VALUES(?,?,?,?)",
                (ACT, "客户", "类型", ct))
w("\n== 7. activity == id=", ACT, " 可口可乐满减 满300立减15(定额) 品牌=可口可乐 客户类型6项")

# ============ 8. order_activity (活动明细按订单号聚合) ============
ai = {h: i for i, h in enumerate(HDR_A)}
a_no=ai.get("订单号"); a_amt=ai.get("商品总金额"); a_disc=ai.get("促销优惠金额"); a_pol=ai.get("享受促销政策")
agg = defaultdict(lambda: dict(amt=0.0, disc=0.0, lines=0, pol=""))
act_unmatched = []
for r in ROWS_A:
    no = cell(r, a_no).strip()
    if not no:
        continue
    g = agg[no]
    g["amt"]  += to_num(cell(r, a_amt)) or 0.0
    g["disc"] += to_num(cell(r, a_disc)) or 0.0
    g["lines"]+= 1
    if not g["pol"]:
        g["pol"] = cell(r, a_pol).strip()
oa_id_by_order = {}
for no, g in agg.items():
    oid = order_id_by_no.get(no)
    if not oid:
        act_unmatched.append(no); continue
    cur.execute("""INSERT OR IGNORE INTO order_activity(order_id,activity_id,rule_id,
        activity_product_amount,platform_actual_benefit,policy_text,exec_status,evidence_ref)
        VALUES(?,?,?,?,?,?,?,?)""",
        (oid, ACT, RULE, r2(g["amt"]), r2(g["disc"]), g["pol"], "已执行",
         "活动明细HTML"))
    oa_id_by_order[no] = cur.lastrowid
w("\n== 8. order_activity == 活动明细唯一订单=", len(agg), " 入库=", len(oa_id_by_order),
  " 未匹配到订单=", len(act_unmatched))

# ============ 9. fulfillment (全部订单) ============
fulfil_cand = 0
for no, oid in order_id_by_no.items():
    st = order_meta[no]["status"]; tm = order_meta[no]["time"]
    completed = (st == "已完成")
    cand = 1 if (completed and tm and tm <= T2_CUTOFF) else 0
    fulfil_cand += cand
    cur.execute("""INSERT OR IGNORE INTO fulfillment(order_id,order_status,completed_at,t2_release_candidate)
        VALUES(?,?,?,?)""", (oid, st, tm if completed else None, cand))
w("\n== 9. fulfillment == 订单总数=", len(order_id_by_no), " T-2候选(已完成且≤", T2_CUTOFF, ")=", fulfil_cand)

# ============ 10. RESULT ============
cur.execute("INSERT INTO rule_catalog(rule_topic,version,effective_from,confirmed_by,scope,rule_text) VALUES(?,?,?,?,?,?)",
    ("满减权益重算","v1",CALC_DATE,"截图配置(可口可乐满减)","快马-兴路强-满减",
     "阶梯单单档:满300立减15(定额一次,非每满);活动明细优惠按商品行分摊,须按订单号汇总Σ优惠再与理论15比对"))
cur.execute("INSERT INTO rule_catalog(rule_topic,version,effective_from,confirmed_by,scope,rule_text) VALUES(?,?,?,?,?,?)",
    ("T-2释放节点","v1",CALC_DATE,"费用验证会议2026-09-15","全平台",
     "订单状态=已完成 且 下单时间≤计算日T-2 00:00:00 方可进入费用释放;支付方式不过滤"))
cur.execute("""INSERT INTO result_calc_batch(calc_date,rule_version,input_batch_id,operator,created_at)
               VALUES(?,?,?,?,?)""", (CALC_DATE, "v1", BATCH, "小凡", NOW))
CB = cur.lastrowid
w("\n== 10. RESULT == calc_batch_id=", CB, " calc_date=", CALC_DATE)

# 10a. result_entitlement
order_status_by_no = {no: order_meta[no]["status"] for no in order_id_by_no}
order_time_by_no   = {no: order_meta[no]["time"] for no in order_id_by_no}
ent_total = ent_consistent = ent_diff = 0
out_window = below_threshold = 0
sum_actual = 0.0
sum_theo   = 0.0
not_completed = []
for no, oa in oa_id_by_order.items():
    g = agg[no]
    actual = r2(g["disc"])
    st = order_status_by_no.get(no, "")
    tm = order_time_by_no.get(no, "")
    in_window = bool(tm and ACT_START <= tm <= ACT_END)
    completed = (st == "已完成")
    if not in_window:
        out_window += 1
    if g["amt"] < THRESHOLD - 1e-9:
        below_threshold += 1
    qualifies = (g["amt"] >= THRESHOLD - 1e-9) and in_window
    theo = r2(REDUCE) if qualifies else 0.0
    cons = "一致" if abs((actual or 0) - (theo or 0)) < 0.005 else "差异"
    diff = r2((actual or 0) - (theo or 0))
    cur.execute("""INSERT INTO result_entitlement(order_activity_id,theoretical_benefit,platform_actual_benefit,
        consistency,diff_amount,formula_ref,calc_batch_id) VALUES(?,?,?,?,?,?,?)""",
        (oa, theo, actual, cons, diff, "满300立减15定额;Σ活动明细优惠", CB))
    ent_total += 1; sum_actual += (actual or 0); sum_theo += (theo or 0)
    if cons == "一致": ent_consistent += 1
    else: ent_diff += 1
    if not completed:
        not_completed.append((no, st, tm))
w("== 10a. result_entitlement == 计=", ent_total, " 一致=", ent_consistent, " 差异=", ent_diff,
  " 窗外=", out_window, " 未达300=", below_threshold)
w("     Σ理论权益=", r2(sum_theo), " Σ平台实际优惠=", r2(sum_actual))

# 10b. result_release_candidate (仅活动订单)
cand_yes = cand_no = 0
released_actual = 0.0
for no, oa in oa_id_by_order.items():
    oid = order_id_by_no[no]
    st = order_status_by_no.get(no, ""); tm = order_time_by_no.get(no, "")
    is_cand = 1 if (st == "已完成" and tm and tm <= T2_CUTOFF) else 0
    reason = "已完成且≤T-2" if is_cand else f"未达释放节点(状态={st})"
    cur.execute("""INSERT OR IGNORE INTO result_release_candidate(order_id,calc_date,is_candidate,reason,calc_batch_id)
        VALUES(?,?,?,?,?)""", (oid, CALC_DATE, is_cand, reason, CB))
    if is_cand:
        cand_yes += 1; released_actual += (r2(agg[no]["disc"]) or 0)
    else:
        cand_no += 1
w("== 10b. result_release_candidate == 可释放=", cand_yes, " 暂不可释放=", cand_no,
  " 可释放实际优惠合计=", r2(released_actual))

# 10c. result_fee
fee_bearer = "渠道市场部(发票抬头:装瓶厂)"
settle_amount = r2(released_actual)
diff_budget = r2(BUDGET - released_actual)
cur.execute("""INSERT INTO result_fee(tpm_id,activity_id,actual_discount_total,gift_cost_total,fee_bearer,
    settle_target,budget_amount,budget_reserve_no,settle_amount,diff_amount,settle_status,calc_batch_id)
    VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
    (TPM, ACT, r2(sum_actual), 0.0, fee_bearer, "深圳市兴路强商贸有限公司", BUDGET, "3900088916",
     settle_amount, diff_budget, "待结算", CB))
w("== 10c. result_fee == 实际优惠总额=", r2(sum_actual), " 本次可结算(T-2)=", settle_amount,
  " 预算=", BUDGET, " 预算余量=", diff_budget, " 承担方=", fee_bearer)

# 10d. result_quality_issue
qi = 0
for no, st, tm in not_completed:
    cur.execute("""INSERT INTO result_quality_issue(order_no,issue_type,level,reason,evidence_ref,calc_batch_id)
        VALUES(?,?,?,?,?,?)""", (no, "权益已计未达释放节点", "提示", f"订单状态={st},未进入T-2释放", "活动明细", CB))
    qi += 1
for no in act_unmatched:
    cur.execute("""INSERT INTO result_quality_issue(order_no,issue_type,level,reason,evidence_ref,calc_batch_id)
        VALUES(?,?,?,?,?,?)""", (no, "活动明细订单未在订单明细", "警告", "无法建立订单活动关系", "活动明细", CB))
    qi += 1
if prod_miss:
    cur.execute("""INSERT INTO result_quality_issue(order_no,issue_type,level,reason,evidence_ref,calc_batch_id)
        VALUES(?,?,?,?,?,?)""", (None, "商品跨系统匹配缺口", "警告",
        f"{prod_miss}行订单商品未按编号/条码匹配到商品主数据,product_id为空", "订单明细", CB))
    qi += 1
if cust_miss:
    cur.execute("""INSERT INTO result_quality_issue(order_no,issue_type,level,reason,evidence_ref,calc_batch_id)
        VALUES(?,?,?,?,?,?)""", (None, "客户匹配缺口", "提示",
        f"{cust_miss}个订单客户编号未在客户主数据匹配", "订单明细", CB))
    qi += 1
w("== 10d. result_quality_issue == 记录数=", qi,
  " (未达释放", len(not_completed), "/活动未匹配", len(act_unmatched), "/商品缺口", bool(prod_miss), "/客户缺口", bool(cust_miss), ")")

con.commit()

# The shared framework owns the persisted entitlement, T-2 and fee conclusions.
# Keep the source-specific quality rows above as evidence for import gaps.
summary = calculate_activity(con, ACT, CB, CALC_DATE)
w("== 10e. 通用核算框架 ==", summary)

# ============ 11. 汇总核对 ============
w("\n== 11. 入库汇总 ==")
for t in ["customer","product","order_header","order_line","tpm_application","activity",
          "activity_rule","activity_scope","order_activity","fulfillment","result_entitlement",
          "result_release_candidate","result_fee","result_quality_issue"]:
    w(f"  {t}: {cur.execute('SELECT count(*) FROM '+t).fetchone()[0]}")
con.close()
rep.close()
print("\nREPORT ->", REPORT)
