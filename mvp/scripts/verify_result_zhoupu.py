# -*- coding: utf-8 -*-
"""独立验证: 舟谱-羿柏 返券+满赠 RESULT 核算. 读提交后 DB + ATTACH 备份做兴路强隔离核验.
口径(用户确认2026-09-23): 返券只算使用侧且双单号券不猜测(45单/675元); 满赠应赠单客最多1次,
实赠只认本活动赠品"(赠品)雪碧抱枕"(不含沥水篮/水盆等他活动赠品).
XD驱动改造(用户规则2026-09-24): 以XD履约'已完成'结算,不管是否关联SXD; CORE新增XD-only建单
(order_source='XD履约(无SXD)'), 满赠合格域含 SXD命中XD + XD-only 已完成单(§7 EXISTS守卫).
退出码: 全 PASS -> 0; 有 FAIL -> 1.
"""
import os, sqlite3, sys
from datetime import datetime, timedelta
MVP = r"D:\Peggy zhan\智能EC101\数据底座\第三阶段数据库设计\mvp"
DB  = os.path.join(MVP, "ec101_mvp.db")
BAK = os.path.join(MVP, "ec101_mvp.db.bak-pre-xd-driven-20260924")
if not os.path.exists(BAK):
    print(f"[FAIL] 备份库不存在, 无法做隔离核验: {BAK}"); sys.exit(1)
con = sqlite3.connect(DB); cur = con.cursor()
cur.execute("ATTACH ? AS bak", (BAK,))
PASS = []; FAIL = []
def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}")
def one(sql, args=()): return cur.execute(sql, args).fetchone()[0]

ZP = one("SELECT dealer_platform_id FROM dealer_platform WHERE dealer_name='羿柏'")
XL = one("SELECT dealer_platform_id FROM dealer_platform WHERE dealer_name='深圳市兴路强商贸有限公司'")
CB = one("SELECT max(calc_batch_id) FROM result_calc_batch WHERE operator='舟谱RESULT'")
FQ = one("SELECT activity_id FROM activity WHERE dealer_platform_id=? AND activity_name='可口可乐产品288返15元券'", (ZP,))
MZ = one("SELECT activity_id FROM activity WHERE dealer_platform_id=? AND activity_name='雪碧系列满100元送抱枕'", (ZP,))

# ---------- 1. 隔离: 兴路强(XL) 各表行数 前后Δ=0 ----------
#   order_activity/result_* 无 dealer_platform_id, 须经 activity 或 order_header 归属到 XL,
#   否则会把本轮新增的羿柏行算进来 -> 误报 FAIL.
ACT_OF_DP = "(SELECT activity_id FROM {p}activity WHERE dealer_platform_id=?)"
ISO = {
    "coupon_ledger":   "SELECT count(*) FROM {p}coupon_ledger WHERE dealer_platform_id=?",
    "activity":        "SELECT count(*) FROM {p}activity WHERE dealer_platform_id=?",
    "order_activity":  f"SELECT count(*) FROM {{p}}order_activity WHERE activity_id IN {ACT_OF_DP}",
    "result_fee":      f"SELECT count(*) FROM {{p}}result_fee WHERE activity_id IN {ACT_OF_DP}",
    "result_entitlement":
        f"SELECT count(*) FROM {{p}}result_entitlement WHERE order_activity_id IN "
        f"(SELECT order_activity_id FROM {{p}}order_activity WHERE activity_id IN {ACT_OF_DP})",
    "result_release_candidate":
        "SELECT count(*) FROM {p}result_release_candidate WHERE order_id IN "
        "(SELECT order_id FROM {p}order_header WHERE dealer_platform_id=?)",
    "result_quality_issue":
        "SELECT count(*) FROM {p}result_quality_issue WHERE calc_batch_id IN "
        "(SELECT calc_batch_id FROM {p}result_calc_batch WHERE operator<>'舟谱RESULT')",
    "result_calc_batch":
        "SELECT count(*) FROM {p}result_calc_batch WHERE operator<>'舟谱RESULT'",
}
for t, tpl in ISO.items():
    sql_now, sql_bak = tpl.format(p=""), tpl.format(p="bak.")
    args = (XL,) if "?" in sql_now else ()   # quality_issue/calc_batch 模板无占位符, 不能多传绑定
    a = one(sql_now, args); b = one(sql_bak, args)
    check(f"隔离 {t} Δ=0", a == b, f"now={a} bak={b}")

# ---------- 2. 返券使用侧 ----------
check("coupon_ledger羿柏=102", one("SELECT count(*) FROM coupon_ledger WHERE dealer_platform_id=?", (ZP,)) == 102)
check("已用券=48", one("SELECT count(*) FROM coupon_ledger WHERE dealer_platform_id=? AND coupon_status='已使用'", (ZP,)) == 48)
hit = 0
used_nos = [r[0] for r in cur.execute("SELECT use_order_no FROM coupon_ledger WHERE dealer_platform_id=? AND use_order_no IS NOT NULL", (ZP,)).fetchall()]
for no in used_nos:   # 先 fetchall 再遍历: 循环内复用同一 cursor 会失效外层迭代
    if one("SELECT count(*) FROM order_header WHERE dealer_platform_id=? AND order_no=?", (ZP, no)): hit += 1
check("券->订单唯一命中=45(3张双单号不计)", hit == 45, f"hit={hit}")
n_ent_fq = one("SELECT count(*) FROM result_entitlement WHERE calc_batch_id=? AND formula_ref LIKE '券面值%'", (CB,))
n_cons   = one("SELECT count(*) FROM result_entitlement WHERE calc_batch_id=? AND consistency='一致' AND formula_ref LIKE '券面值%'", (CB,))
check("返券entitlement=45且全一致", n_ent_fq == 45 and n_cons == 45, f"ent={n_ent_fq} cons={n_cons}")
fq_fee = one("SELECT actual_discount_total FROM result_fee WHERE activity_id=?", (FQ,))
fq_sum = one("SELECT sum(platform_actual_benefit) FROM result_entitlement WHERE order_activity_id IN (SELECT order_activity_id FROM order_activity WHERE activity_id=?)", (FQ,))
check("返券fee=675且=entitlement合计", fq_fee == 675 and abs((fq_fee or 0) - (fq_sum or 0)) < 0.01, f"fee={fq_fee} ent_sum={fq_sum}")
check("返券双单号台账已记", one("SELECT count(*) FROM result_quality_issue WHERE calc_batch_id=? AND issue_type='返券双单号无法唯一归因'", (CB,)) == 1)

# ---------- 3. 满赠 应赠vs实赠(单客最多1次) ----------
n_mz = one("SELECT count(*) FROM result_entitlement WHERE order_activity_id IN (SELECT order_activity_id FROM order_activity WHERE activity_id=?)", (MZ,))
check("满赠entitlement=142(合格单=雪碧≥100;含XD-only已完成)", n_mz == 142, f"n={n_mz}")
granted_rows = one("SELECT count(*) FROM result_entitlement WHERE order_activity_id IN (SELECT order_activity_id FROM order_activity WHERE activity_id=?) AND gift_qty_entitled=1", (MZ,))
granted_cust = one("SELECT count(DISTINCT h.customer_id) FROM result_entitlement re JOIN order_activity oa ON oa.order_activity_id=re.order_activity_id JOIN order_header h ON h.order_id=oa.order_id WHERE oa.activity_id=? AND re.gift_qty_entitled=1", (MZ,))
check("满赠单客最多1次(应赠行=应赠客户数)", granted_rows == granted_cust, f"应赠行={granted_rows} 客户={granted_cust}")
n_bad = one("SELECT count(*) FROM result_entitlement WHERE order_activity_id IN (SELECT order_activity_id FROM order_activity WHERE activity_id=?) AND consistency='差异'", (MZ,))
check("满赠差异=43(应赠≠实赠;含XD-only扩展域,待业务确认)", n_bad == 43, f"差异={n_bad}")
mz_fee = cur.execute("SELECT actual_discount_total,gift_cost_total,tpm_id,settle_status FROM result_fee WHERE activity_id=?", (MZ,)).fetchone()
check("满赠fee数量口径(金额0,tpm=NULL)", mz_fee[0] == 0 and mz_fee[1] == 0 and mz_fee[2] is None, str(mz_fee))

# ---------- 3a. 实赠只认抱枕(缺陷修复回归守卫): 独立从 order_line 重算, 证明未混入沥水篮/水盆等他活动赠品 ----------
GIFT = "(赠品)雪碧抱枕"
stored_gift = one("SELECT sum(gift_qty_actual) FROM result_entitlement WHERE order_activity_id IN (SELECT order_activity_id FROM order_activity WHERE activity_id=?)", (MZ,))
pillow = one("SELECT coalesce(sum(ol.order_qty),0) FROM order_line ol JOIN product p ON p.product_id=ol.product_id "
             "WHERE p.product_name=? AND ol.order_id IN (SELECT order_id FROM order_activity WHERE activity_id=?)", (GIFT, MZ))
gift_kinds = one("SELECT count(DISTINCT p.product_name) FROM order_line ol JOIN product p ON p.product_id=ol.product_id "
                 "JOIN order_header h ON h.order_id=ol.order_id WHERE h.dealer_platform_id=? AND p.product_name LIKE '(赠品)%'", (ZP,))
check("满赠实赠只认抱枕(stored=抱枕重算=100;羿柏赠品种类>1证明他赠品未混入)",
      stored_gift == pillow == 100 and gift_kinds > 1,
      f"stored实赠={stored_gift} 抱枕重算={pillow} 羿柏赠品种类={gift_kinds}")

# ---------- 3b. release 候选逻辑复核(已完成 + completed_at≤calc_date-2) ----------
calc_date = one("SELECT calc_date FROM result_calc_batch WHERE calc_batch_id=?", (CB,))
CUTOFF = (datetime.strptime(calc_date, "%Y-%m-%d") - timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S")
rel_ids = [r[0] for r in cur.execute(
    "SELECT order_id FROM result_release_candidate WHERE calc_batch_id=?", (CB,)).fetchall()]
rel_mism = 0
for oid in rel_ids:   # 镜像 ingest §8 的取数(LEFT JOIN fulfillment 取首行), 避免多履约行歧义
    stored = one("SELECT is_candidate FROM result_release_candidate WHERE calc_batch_id=? AND order_id=?", (CB, oid))
    st = cur.execute("SELECT h.order_status, f.completed_at FROM order_header h "
                     "LEFT JOIN fulfillment f ON f.order_id=h.order_id WHERE h.order_id=?", (oid,)).fetchone()
    exp = 1 if (st and st[0] == "已完成" and st[1] and st[1] <= CUTOFF) else 0
    if exp != stored: rel_mism += 1
n_cand = one("SELECT count(*) FROM result_release_candidate WHERE calc_batch_id=? AND is_candidate=1", (CB,))
check("release T-2逻辑自洽(已完成且completed_at≤calc_date-2)", rel_mism == 0 and len(rel_ids) > 0,
      f"cutoff={CUTOFF} 复核{len(rel_ids)}单 候选={n_cand} 不一致={rel_mism}")

# ---------- 3c. XD驱动改造回归守卫 ----------
n_xdonly = one("SELECT count(*) FROM order_header WHERE dealer_platform_id=? AND order_source='XD履约(无SXD)'", (ZP,))
check("XD-only建单=2644(order_source='XD履约(无SXD)')", n_xdonly == 2644, f"n={n_xdonly}")
n_xdonly_noful = one("SELECT count(*) FROM order_header h WHERE h.dealer_platform_id=? AND h.order_source='XD履约(无SXD)' "
                     "AND NOT EXISTS(SELECT 1 FROM fulfillment f WHERE f.order_id=h.order_id)", (ZP,))
check("XD-only单均有fulfillment(XD本身即履约)", n_xdonly_noful == 0, f"缺fulfillment={n_xdonly_noful}")
n_mz_noful = one("SELECT count(*) FROM order_activity oa JOIN order_header h ON h.order_id=oa.order_id "
                 "WHERE oa.activity_id=? AND NOT EXISTS(SELECT 1 FROM fulfillment f WHERE f.order_id=h.order_id AND f.order_status='已完成')", (MZ,))
check("满赠合格单均有XD履约'已完成'(§7 EXISTS守卫生效)", n_mz_noful == 0, f"无XD已完成的满赠单={n_mz_noful}")
n_heji = one("SELECT count(*) FROM order_header WHERE dealer_platform_id=? AND order_no='合计'", (ZP,))
check("XD表尾'合计'总计行未误建单", n_heji == 0, f"合计单={n_heji}")

# ---------- 4. FK ----------
fk = cur.execute("PRAGMA foreign_key_check").fetchall()
check("外键约束无违反", not fk, str(fk[:3]))

print(f"\n==== PASS={len(PASS)} FAIL={len(FAIL)} ====")
if FAIL:
    print("FAIL:", FAIL); sys.exit(1)
