# -*- coding: utf-8 -*-
"""EC101 MVP — 舟谱-羿柏 返券(288返15)+满赠(雪碧满100送抱枕) RESULT 层核算.
前置: ingest_zhoupu.py 已 --real 运行(羿柏 dealer_platform 与订单/主数据已入库).
口径(spec 2026-09-23): D1 返券只算使用侧; D3 实赠=本活动配置赠品"(赠品)雪碧抱枕"行(不含沥水篮/水盆等他活动赠品);
                      D4 已完成+T-2; D5 赠品数量口径/不走TPM; D6 羿柏作用域; D7 幂等.
用法: python ingest_result_zhoupu.py         # DRY 只打印不写库
      python ingest_result_zhoupu.py --real  # 真实写库
"""
import os, re, sys, sqlite3
from datetime import datetime, timedelta
sys.path.insert(0, os.path.dirname(__file__))
from readers import read_table, to_num, to_datetime_text

MVP    = r"D:\Peggy zhan\智能EC101\数据底座\第三阶段数据库设计\mvp"
BASE   = r"D:\Peggy zhan\智能EC101\数据底座\第三阶段数据库设计\舟谱-羿柏-试点"
DB     = os.path.join(MVP, "ec101_mvp.db")
REPORT = os.path.join(MVP, "ingest_report_result_zhoupu.txt")
F_COUPON = os.path.join(BASE, "满减", "舟谱-羿柏-活动明细-20260826-20260908.xls")

DEALER, PLATFORM = "羿柏", "舟谱"
BATCH_CODE = "ZP-YP-RESULT-20260923"
OPERATOR   = "舟谱RESULT"
CALC_DATE  = "2026-09-23"
MZ_START, MZ_END = "2026-08-19 00:00:00", "2026-08-27 00:00:00"
GIFT_PRODUCT = "(赠品)雪碧抱枕"   # 本活动唯一赠品; 实赠只认此品(羿柏另有沥水篮/水盆等他活动赠品, 不得计入)
SNOW = "雪碧"
ACT_FQ = "可口可乐产品288返15元券"
ACT_MZ = "雪碧系列满100元送抱枕"
REAL = "--real" in sys.argv
TEARDOWN_ONLY = "--teardown-only" in sys.argv   # 只清理羿柏RESULT作用域(§1)后退出, 不重建; 供CORE重灌前先拆RESULT(避FK崩溃)

rep = open(REPORT, "w", encoding="utf-8")
def w(*a):
    s = " ".join(str(x) for x in a); print(s); rep.write(s + "\n")
def r2(x): return None if x is None else round(float(x) + 0.0, 2)
def cell(row, i, default=""):
    if i is None or i < 0 or i >= len(row): return default
    v = row[i]; return v if v is not None else default

_synth = [0]
def ins(sql, params=()):
    if not REAL:
        _synth[0] += 1; return _synth[0]
    cur.execute(sql, params); return cur.lastrowid

con = sqlite3.connect(DB); con.execute("PRAGMA foreign_keys = ON"); cur = con.cursor()
DP = cur.execute("SELECT dealer_platform_id FROM dealer_platform WHERE dealer_name=? AND platform_name=?",
                 (DEALER, PLATFORM)).fetchone()[0]
w(f"== 0 == REAL={REAL} dealer_platform_id={DP}")

# ---------- 1. 幂等清理(仅羿柏作用域; 破坏性删除+commit 仅 REAL, DRY 全程只读) ----------
old_acts = [r[0] for r in cur.execute(
    "SELECT activity_id FROM activity WHERE dealer_platform_id=? AND activity_name IN (?,?)",
    (DP, ACT_FQ, ACT_MZ))]
old_cb = [r[0] for r in cur.execute("SELECT calc_batch_id FROM result_calc_batch WHERE operator=?", (OPERATOR,))]
if REAL:
    if old_acts:
        ph = ",".join("?" * len(old_acts))
        cur.execute(f"DELETE FROM result_entitlement WHERE order_activity_id IN "
                    f"(SELECT order_activity_id FROM order_activity WHERE activity_id IN ({ph}))", old_acts)
        cur.execute(f"DELETE FROM result_fee WHERE activity_id IN ({ph})", old_acts)
        cur.execute(f"DELETE FROM order_activity WHERE activity_id IN ({ph})", old_acts)
        cur.execute(f"DELETE FROM activity_rule_benefit WHERE rule_id IN "
                    f"(SELECT rule_id FROM activity_rule WHERE activity_id IN ({ph}))", old_acts)
        cur.execute(f"DELETE FROM activity_rule WHERE activity_id IN ({ph})", old_acts)
        cur.execute(f"DELETE FROM activity_scope WHERE activity_id IN ({ph})", old_acts)
        cur.execute(f"DELETE FROM activity WHERE activity_id IN ({ph})", old_acts)
    if old_cb:
        ph = ",".join("?" * len(old_cb))
        cur.execute(f"DELETE FROM result_release_candidate WHERE calc_batch_id IN ({ph})", old_cb)
        cur.execute(f"DELETE FROM result_quality_issue WHERE calc_batch_id IN ({ph})", old_cb)
        cur.execute(f"DELETE FROM result_calc_batch WHERE calc_batch_id IN ({ph})", old_cb)
    cur.execute("DELETE FROM coupon_ledger WHERE dealer_platform_id=?", (DP,))
    for b in [r[0] for r in cur.execute("SELECT batch_id FROM raw_import_batch WHERE batch_code=?", (BATCH_CODE,)).fetchall()]:
        cur.execute("DELETE FROM raw_file WHERE batch_id=?", (b,))
        cur.execute("DELETE FROM raw_import_batch WHERE batch_id=?", (b,))
    con.commit()
w(f"  清理: REAL={REAL} 旧activity={len(old_acts)} 旧calc_batch={len(old_cb)} (仅羿柏{'' if REAL else '; DRY不删不写'})")

if TEARDOWN_ONLY:
    if not REAL:
        w("== teardown-only 但未加 --real: §1 未真正删除(DRY). 如需拆除请加 --real ==")
    else:
        w("== teardown-only: 羿柏RESULT作用域已拆除并commit, 不重建. 现在可安全重灌CORE ==")
    con.close()
    sys.exit(0)

# ---------- 2. RAW 血缘(append-only 新批次) ----------
NOW = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
sig, sheet, HDR, ROWS = read_table(F_COUPON, header_row=3)
BATCH = ins("INSERT INTO raw_import_batch(batch_code,source_platform,dealer_name,imported_at,operator) "
            "VALUES(?,?,?,?,?)", (BATCH_CODE, PLATFORM, DEALER, NOW, OPERATOR))
ins("INSERT INTO raw_file(batch_id,file_name,module,file_signature,read_method,sheet_name,header_row,data_rows) "
    "VALUES(?,?,?,?,?,?,?,?)",
    (BATCH, os.path.basename(F_COUPON), "活动明细(券台账)", sig, "readers.read_table", sheet, 3, len(ROWS)))
w(f"== 1. RAW == sig={sig} sheet={sheet} 行={len(ROWS)} header={HDR}")

# ---------- 3. 计算批次(先建, 供 RESULT 行引用) ----------
CB = ins("INSERT INTO result_calc_batch(calc_date,rule_version,input_batch_id,operator,created_at) "
         "VALUES(?,?,?,?,?)", (CALC_DATE, "v1", BATCH, OPERATOR, NOW))
w(f"== 2. calc_batch == id={CB}")

# ---------- 4. coupon_ledger(102行) ----------
ai = {h: i for i, h in enumerate(HDR)}
cust_by_name = {n: i for (n, i) in cur.execute(
    "SELECT customer_name,customer_id FROM customer WHERE dealer_platform_id=?", (DP,))}
loaded = 0; used_rows = []; cust_unmatched = []
for i, r in enumerate(ROWS):
    name = str(cell(r, ai.get("券名"))).strip()
    if not name: continue
    m = re.search(r"返(\d+(?:\.\d+)?)元?", name)
    face = float(m.group(1)) if m else None
    cname = str(cell(r, ai.get("领取客户"))).strip()
    cid = cust_by_name.get(cname)
    if cid is None and cname: cust_unmatched.append(cname)
    used = (to_num(cell(r, ai.get("已使用张数"))) or 0) > 0
    use_no = str(cell(r, ai.get("关联单据编号"))).strip()
    cno = f"ZP-FQ-{i:04d}"
    ins("""INSERT INTO coupon_ledger(dealer_platform_id,coupon_no,coupon_name,customer_id,salesperson_name,
        receive_time,use_period,coupon_status,use_time,use_order_no,discount_amount,fee_month)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
        (DP, cno, name, cid, None, None, None,
         "已使用" if used else "已领取", None, use_no or None,
         face if used else None, None))
    loaded += 1
    if used and use_no: used_rows.append((cno, use_no, face))
w(f"== 3. coupon_ledger == 载入={loaded} 已用且带单号={len(used_rows)} 客户未匹配={len(cust_unmatched)} {cust_unmatched[:5]}")

# ---------- 5. activity + rule + benefit + scope ----------
ACT_FQ_ID = ins("""INSERT INTO activity(dealer_platform_id,tpm_id,activity_name,activity_category,promo_method,
    promotion_type,product_scope_type,purchase_limit_type,customer_scope_type,start_time,end_time,
    activity_status,rule_version) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
    (DP, None, ACT_FQ, "券类", "满返", "满288返15元券", "不限", None, "不限",
     "2026-08-26 00:00:00", "2026-09-08 23:59:59", "已结束", "v1"))
RULE_FQ = ins("INSERT INTO activity_rule(activity_id,tier_no,threshold_type,threshold_value,reduce_amount,free_shipping) "
              "VALUES(?,?,?,?,?,?)", (ACT_FQ_ID, 1, "金额", 288, 0, 0))
ins("""INSERT INTO activity_rule_benefit(rule_id,benefit_type,gift_product_no,gift_product_name,gift_qty,
    coupon_id,coupon_name,coupon_qty) VALUES(?,?,?,?,?,?,?,?)""",
    (RULE_FQ, "返券", None, None, None, None, ACT_FQ, 1))

ACT_MZ_ID = ins("""INSERT INTO activity(dealer_platform_id,tpm_id,activity_name,activity_category,promo_method,
    promotion_type,product_scope_type,purchase_limit_type,purchase_limit_value,customer_scope_type,
    start_time,end_time,activity_status,rule_version) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
    (DP, None, ACT_MZ, "非券类", "阶梯", "满一定金额立赠", "指定商品", "每用户限购", 1, "不限",
     "2026-08-19 12:29:37", "2026-08-26 12:29:40", "已结束", "v1"))
RULE_MZ = ins("INSERT INTO activity_rule(activity_id,tier_no,threshold_type,threshold_value,reduce_amount,free_shipping) "
              "VALUES(?,?,?,?,?,?)", (ACT_MZ_ID, 1, "金额", 100, 0, 0))
ins("""INSERT INTO activity_rule_benefit(rule_id,benefit_type,gift_product_no,gift_product_name,gift_qty,
    coupon_id,coupon_name,coupon_qty) VALUES(?,?,?,?,?,?,?,?)""",
    (RULE_MZ, "赠品", None, GIFT_PRODUCT, 1, None, None, None))
snow_names = [r[0] for r in cur.execute(
    "SELECT DISTINCT product_name FROM product WHERE dealer_platform_id=? AND product_name LIKE ?",
    (DP, SNOW + "%"))] if REAL else ["雪碧<DRY>"]
for nm in snow_names:
    ins("INSERT INTO activity_scope(activity_id,scope_category,scope_dimension,scope_value) VALUES(?,?,?,?)",
        (ACT_MZ_ID, "商品", "商品", nm))
w(f"== 4. activity == 返券={ACT_FQ_ID} 满赠={ACT_MZ_ID} 雪碧scope行={len(snow_names)}")

# ---------- 6. 返券使用侧: order_activity + entitlement ----------
# D1 只算使用侧; 双单号(逗号拼接)券无法唯一归因 -> 不猜测, 不计入逐单entitlement/费用, 记质量台账(用户确认2026-09-23)
ent_fq = 0; cons_fq = 0; fq_fee = 0.0; unlinked = []
for cno, use_no, face in used_rows:
    row = cur.execute("SELECT order_id FROM order_header WHERE dealer_platform_id=? AND order_no=?",
                      (DP, use_no)).fetchone() if REAL else None
    if REAL and row is None:
        unlinked.append((cno, use_no, face)); continue
    oid = row[0] if REAL else _synth[0] + 1
    oa = ins("""INSERT INTO order_activity(order_id,activity_id,rule_id,activity_product_amount,
        platform_actual_benefit,policy_text,exec_status,evidence_ref,gift_qty_actual) VALUES(?,?,?,?,?,?,?,?,?)""",
        (oid, ACT_FQ_ID, RULE_FQ, None, r2(face), f"使用[{ACT_FQ}]抵扣{face}元", "已执行",
         "券台账+关联单据编号", None))
    ins("""INSERT INTO result_entitlement(order_activity_id,theoretical_benefit,platform_actual_benefit,
        gift_qty_entitled,gift_qty_actual,consistency,diff_amount,formula_ref,calc_batch_id)
        VALUES(?,?,?,?,?,?,?,?,?)""",
        (oa, r2(face), r2(face), None, None, "一致", 0, f"券面值{face}(券名解析)", CB))
    ent_fq += 1; cons_fq += 1; fq_fee += (face or 0)
w(f"== 5. 返券 == entitlement={ent_fq} 一致={cons_fq} 计入费用={r2(fq_fee)} 单号未命中={len(unlinked)} {[u[1] for u in unlinked][:5]}")

# ---------- 7. 满赠: order_activity + entitlement ----------
# 应赠口径(spec): 活动商品(雪碧)金额>=100 的合格单记应赠1, 单客最多1次(用户确认2026-09-23); 实赠=该单"(赠品)雪碧抱枕"行数量(只认本活动赠品).
# 按 customer_id,order_time 排序遍历, 每个客户只有首个雪碧>=100的单记应赠1, 其余记0(超出单客限次或赠了但未达标 -> 差异).
# XD驱动结算(用户规则2026-09-24): 满赠合格单必须 XD履约'已完成'(存在 fulfillment 且 order_status='已完成').
# 决策5下 XD命中单的 header 状态已=XD权威; 此 EXISTS 守卫主要排除"仅SXD'已完成'但无XD履约"的单(不结算).
mz_orders = cur.execute("SELECT h.order_id,h.customer_id,h.order_time FROM order_header h WHERE h.dealer_platform_id=? "
                        "AND h.order_time>=? AND h.order_time<? AND h.order_status='已完成' "
                        "AND EXISTS(SELECT 1 FROM fulfillment f WHERE f.order_id=h.order_id AND f.order_status='已完成') "
                        "ORDER BY h.customer_id,h.order_time", (DP, MZ_START, MZ_END)).fetchall() if REAL else []
mz_ent = 0; mz_cons = 0; mz_bad = 0; mz_qualified = 0; mz_granted = 0; mz_pillow_qty = 0.0
granted_cust = set()
touched = set()
for oid, cid, otime in mz_orders:
    snow_amt = 0.0; gift_qty = 0.0
    for nm, pre, qty in cur.execute(
            "SELECT p.product_name, ol.pre_discount_amount, ol.order_qty FROM order_line ol "
            "LEFT JOIN product p ON p.product_id=ol.product_id WHERE ol.order_id=?", (oid,)):
        nm = nm or ""
        if nm == GIFT_PRODUCT:
            gift_qty += qty or 0
        elif nm.startswith(SNOW):
            snow_amt += pre or 0
    if snow_amt < 100 and gift_qty <= 0: continue
    mz_pillow_qty += gift_qty
    ckey = cid if cid is not None else f"oid{oid}"   # 客户缺失则按单独立计(无法去重)
    if snow_amt >= 100 and ckey not in granted_cust:
        entitled = 1; granted_cust.add(ckey); mz_granted += 1
    else:
        entitled = 0
    mz_qualified += 1; touched.add(oid)
    oa = ins("""INSERT INTO order_activity(order_id,activity_id,rule_id,activity_product_amount,
        platform_actual_benefit,policy_text,exec_status,evidence_ref,gift_qty_actual) VALUES(?,?,?,?,?,?,?,?,?)""",
        (oid, ACT_MZ_ID, RULE_MZ, r2(snow_amt), 0, f"参与[{ACT_MZ}]满100送抱枕", "已执行",
         "订单行(赠品)雪碧抱枕", r2(gift_qty)))
    cons = "一致" if entitled == gift_qty else "差异"
    if cons == "一致": mz_cons += 1
    else: mz_bad += 1
    ins("""INSERT INTO result_entitlement(order_activity_id,theoretical_benefit,platform_actual_benefit,
        gift_qty_entitled,gift_qty_actual,consistency,diff_amount,formula_ref,calc_batch_id)
        VALUES(?,?,?,?,?,?,?,?,?)""",
        (oa, 0, 0, entitled, r2(gift_qty), cons, r2(gift_qty - entitled), "满100立赠x1(单客≤1次);实赠=(赠品)雪碧抱枕行", CB))
    mz_ent += 1
w(f"== 6. 满赠 == 已完成单={len(mz_orders)} 合格单={mz_qualified} entitlement={mz_ent} 应赠单(单客≤1)={mz_granted} 一致={mz_cons} 差异={mz_bad} 实赠抱枕合计={r2(mz_pillow_qty)}")

# ---------- 8. result_release_candidate(已完成+T-2) ----------
cutoff = (datetime.strptime(CALC_DATE, "%Y-%m-%d") - timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S")
for cno, use_no, face in used_rows:
    row = cur.execute("SELECT order_id FROM order_header WHERE dealer_platform_id=? AND order_no=?",
                      (DP, use_no)).fetchone() if REAL else None
    if row: touched.add(row[0])
rel_yes = rel_no = 0
for oid in sorted(touched):
    st = cur.execute("SELECT h.order_status, f.completed_at FROM order_header h "
                     "LEFT JOIN fulfillment f ON f.order_id=h.order_id WHERE h.order_id=?", (oid,)).fetchone() if REAL else None
    is_c = 1 if (st and st[0] == "已完成" and st[1] and st[1] <= cutoff) else 0
    reason = "已完成且≤T-2" if is_c else "未完成或>T-2"
    ins("INSERT OR IGNORE INTO result_release_candidate(order_id,calc_date,is_candidate,reason,calc_batch_id) "
        "VALUES(?,?,?,?,?)", (oid, CALC_DATE, is_c, reason, CB))
    if is_c: rel_yes += 1
    else: rel_no += 1
w(f"== 7. release == 候选={rel_yes} 非候选={rel_no}")

# ---------- 9. result_fee ----------
ins("""INSERT INTO result_fee(tpm_id,activity_id,actual_discount_total,gift_cost_total,fee_bearer,settle_target,
    budget_amount,budget_reserve_no,settle_amount,diff_amount,settle_status,calc_batch_id)
    VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
    (None, ACT_FQ_ID, r2(fq_fee), 0, None, None,
     None, None, None, None, "券抵扣(使用侧)", CB))
# 满赠费用=数量口径不走TPM; XD驱动改造后其合格域含 SXD命中XD + XD-only 已完成单(§7 EXISTS守卫)
ins("""INSERT INTO result_fee(tpm_id,activity_id,actual_discount_total,gift_cost_total,fee_bearer,settle_target,
    budget_amount,budget_reserve_no,settle_amount,diff_amount,settle_status,calc_batch_id)
    VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
    (None, ACT_MZ_ID, 0, 0, None, None, None, None, 0, None, "按赠品数量统计(不结算单价)", CB))
w("== 8. result_fee == 返券金额口径 + 满赠数量口径(tpm=NULL)")

# ---------- 10. 质量台账 ----------
def issue(typ, lvl, reason):
    ins("INSERT INTO result_quality_issue(order_no,issue_type,level,reason,evidence_ref,calc_batch_id) "
        "VALUES(?,?,?,?,?,?)", (None, typ, lvl, reason, "舟谱RESULT", CB))
issue("券面值列全空,15从券名解析", "警告", f"优惠券面值102/102为空;面值由券名'{ACT_FQ}'正则解析;券名变更需改解析")
issue("返券双计探针", "提示", f"对已归因{ent_fq}单核对order_line.discount_amount是否已含券15;若含则费用口径以券台账为准,避免与订单discount重复汇报")
if unlinked:
    ua = r2(sum((f or 0) for _, _, f in unlinked))
    issue("返券双单号无法唯一归因", "警告",
          f"{len(unlinked)}张已用券『关联单据编号』一格含2个已完成订单号(逗号拼接),无法唯一归因到单张订单,"
          f"按只报告不猜测原则未计入逐单entitlement;涉及金额{ua}元(未计入返券费用{r2(fq_fee)}元);"
          f"券={[u[0] for u in unlinked]};原始单号={[u[1] for u in unlinked]};待业务确认归属口径")
null_prod_lines = cur.execute("SELECT count(*) FROM order_line ol JOIN order_header h ON h.order_id=ol.order_id "
    "WHERE h.dealer_platform_id=? AND ol.product_id IS NULL", (DP,)).fetchone()[0] if REAL else 0
sxd_only_done = cur.execute("SELECT count(*) FROM order_header h WHERE h.dealer_platform_id=? "
    "AND h.order_status='已完成' AND NOT EXISTS(SELECT 1 FROM fulfillment f WHERE f.order_id=h.order_id)",
    (DP,)).fetchone()[0] if REAL else 0
issue("XD驱动结算改造(2026-09-24)", "提示",
    "用户规则:以XD履约'已完成'结算,不管是否关联SXD(SXD仅代表用户下单);本轮CORE新增XD-only建单"
    "(order_source='XD履约(无SXD)'),满赠/返券合格域随之扩展;满赠§7加EXISTS(fulfillment.order_status='已完成')守卫,"
    f"实赠抱枕合计={r2(mz_pillow_qty)}(应赠单{mz_granted},单客≤1次)")
issue("仅SXD'已完成'无XD履约单不结算", "提示",
    f"{sxd_only_done}单 header状态='已完成'但无fulfillment(无XD履约命中),按XD驱动规则经EXISTS守卫排除,不计入满赠/释放;"
    "此类单SXD侧'已完成'不代表XD已履约,待XD回传或业务确认")
issue("TD退货单/测试客户排除", "提示",
    "XD文件TD前缀退货单(金额为负)与客户名称='测试'的单在CORE §6.5建单前排除,不入order_header不参与结算;"
    "另XD表尾'合计'总计行非单据,按XD前缀过滤排除(避免灌入约300万假单)")
issue("赠品/商品未匹配(不影响满赠已完成口径)", "提示",
    f"order_line.product_id=NULL共{null_prod_lines}行(羿柏,含他活动赠品沥水篮/水盆及中国劲酒);满赠实赠只认精确匹配'{GIFT_PRODUCT}'的行;"
    "抱枕NULL行经核均属未完成单,未满'已完成+T-2'核算节点故正确排除,非漏算")
issue("576单XD不在窗口", "提示", "接入轮遗留:部分单无XD命中,已完成判定覆盖受限")
if cust_unmatched:
    issue("券领取客户未匹配", "警告", f"{len(cust_unmatched)}个领取客户名未命中customer: {cust_unmatched[:5]}")
w("== 9. quality_issue 已记")

if REAL:
    con.commit()
    fk = cur.execute("PRAGMA foreign_key_check").fetchall()
    w(f"\n== 10. FK == {fk if fk else '无输出(通过)'}")
    for t in ("coupon_ledger", "activity", "order_activity", "result_entitlement",
              "result_release_candidate", "result_fee", "result_quality_issue", "result_calc_batch"):
        w(f"  {t:26} = {cur.execute(f'SELECT count(*) FROM {t}').fetchone()[0]}")
else:
    w("\n== 10. DRY 模式, 未写库 ==")
con.close(); rep.close()
