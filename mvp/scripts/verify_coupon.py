# -*- coding: utf-8 -*-
# 一次性核验：满赠去TPM/费用口径 + 优惠券接入后的全库快照，供 memory.md §6 回写
import sqlite3, os, io

DB = os.path.join(os.path.dirname(__file__), "..", "ec101_mvp.db")
OUT = os.path.join(os.path.dirname(__file__), "..", "verify_coupon.txt")
con = sqlite3.connect(DB)
con.execute("PRAGMA foreign_keys = ON")
cur = con.cursor()
buf = io.StringIO()
def w(s=""):
    buf.write(str(s) + "\n")

def one(sql, *a):
    cur.execute(sql, a)
    r = cur.fetchone()
    return r[0] if r else None

w("== A. 全表行数快照 ==")
tables = [
    "dealer_platform","customer","product","order_header","order_line",
    "tpm_application","activity","activity_rule","activity_rule_benefit","activity_scope",
    "order_activity","fulfillment","cross_mapping","coupon_ledger",
    "rule_catalog","result_calc_batch","result_entitlement","result_release_candidate",
    "result_fee","result_quality_issue","raw_import_batch","raw_file",
    "std_field_mapping","std_quality_check",
]
for t in tables:
    try:
        w(f"  {t:28s} = {one('SELECT COUNT(*) FROM '+t)}")
    except Exception as e:
        w(f"  {t:28s} ERR {e}")

w("\n== B. 满赠 activity (应 tpm_id=NULL) ==")
for r in cur.execute("SELECT activity_id,activity_name,tpm_id,activity_category FROM activity ORDER BY activity_id"):
    w("  " + str(r))

w("\n== C. result_fee 全部 (满赠应 settle_status=按赠品数量统计) ==")
for r in cur.execute("SELECT fee_id,tpm_id,activity_id,settle_status,actual_discount_total,gift_cost_total,settle_amount FROM result_fee ORDER BY fee_id"):
    w("  " + str(r))

w("\n== D. coupon_ledger 明细 ==")
for r in cur.execute("SELECT coupon_id,coupon_no,coupon_name,customer_id,salesperson_name,receive_time,use_period,coupon_status,use_time,use_order_no,discount_amount,fee_month FROM coupon_ledger ORDER BY coupon_id"):
    w("  " + str(r))

w("\n== E. 券->订单关联核验 ==")
cur.execute("""SELECT cl.coupon_no, cl.use_order_no, oh.order_id, oh.order_status, oh.order_time
               FROM coupon_ledger cl LEFT JOIN order_header oh
               ON oh.order_no = cl.use_order_no""")
for r in cur.fetchall():
    w("  " + str(r))

w("\n== F. result_quality_issue 按批次分组 ==")
cur.execute("""SELECT COALESCE(rc.operator,'(无批次)') AS op, rq.calc_batch_id, rq.issue_type, rq.level
               FROM result_quality_issue rq
               LEFT JOIN result_calc_batch rc ON rc.calc_batch_id = rq.calc_batch_id
               ORDER BY rq.calc_batch_id, rq.issue_id""")
for r in cur.fetchall():
    w("  " + str(r))

w("\n== G. result_calc_batch 全部 ==")
for r in cur.execute("SELECT calc_batch_id,calc_date,rule_version,input_batch_id,operator FROM result_calc_batch ORDER BY calc_batch_id"):
    w("  " + str(r))

w("\n== H. raw_import_batch / raw_file ==")
for r in cur.execute("SELECT batch_id,batch_code,source_platform,dealer_name,operator FROM raw_import_batch ORDER BY batch_id"):
    w("  BATCH " + str(r))
cur.execute("SELECT batch_id,COUNT(*),GROUP_CONCAT(module) FROM raw_file GROUP BY batch_id ORDER BY batch_id")
for r in cur.fetchall():
    w("  FILES " + str(r))

w("\n== I. 满减/满赠权益与释放复核 ==")
w(f"  entitlement 总 = {one('SELECT COUNT(*) FROM result_entitlement')}")
w(f"  满减(batch1) 权益 = {one('SELECT COUNT(*) FROM result_entitlement WHERE calc_batch_id=1')}")
w(f"  满赠(batch2) 权益 = {one('SELECT COUNT(*) FROM result_entitlement WHERE calc_batch_id=2')}")
w(f"  一致性分布 = {cur.execute('SELECT consistency,COUNT(*) FROM result_entitlement GROUP BY consistency').fetchall()}")
w(f"  释放候选(是) batch1 = {one('SELECT COUNT(*) FROM result_release_candidate WHERE calc_batch_id=1 AND is_candidate=1')}")
w(f"  释放候选(否) batch1 = {one('SELECT COUNT(*) FROM result_release_candidate WHERE calc_batch_id=1 AND is_candidate=0')}")
w(f"  释放候选(是) batch2 = {one('SELECT COUNT(*) FROM result_release_candidate WHERE calc_batch_id=2 AND is_candidate=1')}")

w("\n== J. FK 违例 ==")
w("  " + str(cur.execute("PRAGMA foreign_key_check").fetchall()))

con.close()
data = buf.getvalue()
with open(OUT, "w", encoding="utf-8") as f:
    f.write(data)
print("WROTE", os.path.abspath(OUT))
