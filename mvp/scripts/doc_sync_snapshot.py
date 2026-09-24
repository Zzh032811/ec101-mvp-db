# -*- coding: utf-8 -*-
"""一次性只读探查: 为更新《EC101_MVP数据库使用说明V1.md》采集数据库现状权威快照.
不写库. 输出 UTF-8 报告到 mvp/scripts/doc_sync_snapshot.txt.
"""
import os, sqlite3
MVP = r"D:\Peggy zhan\智能EC101\数据底座\第三阶段数据库设计\mvp"
DB  = os.path.join(MVP, "ec101_mvp.db")
OUT = os.path.join(MVP, "scripts", "doc_sync_snapshot.txt")

con = sqlite3.connect(DB); con.execute("PRAGMA foreign_keys = ON"); cur = con.cursor()
rep = open(OUT, "w", encoding="utf-8")
def w(*a):
    s = " ".join("" if x is None else str(x) for x in a); rep.write(s + "\n")
def q1(sql, args=()):
    return cur.execute(sql, args).fetchone()
def qall(sql, args=()):
    return cur.execute(sql, args).fetchall()

# 0. 文件大小
w("== 0. DB 文件 ==")
w("  path =", DB)
w("  size_bytes =", os.path.getsize(DB), " size_MB =", round(os.path.getsize(DB)/1048576, 2))

# 1. 全部表 + 行数
w("\n== 1. 全表行数 ==")
tables = [r[0] for r in qall("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
w("  表数量 =", len(tables))
for t in tables:
    w(f"  {t:28s} = {q1('SELECT COUNT(*) FROM ' + t)[0]}")

# 2. activity
w("\n== 2. activity 全部 ==")
for r in qall("SELECT activity_id,activity_name,tpm_id,activity_category,promo_method,promotion_type,product_scope_type,purchase_limit_type,purchase_limit_value,start_time,end_time,allow_stack,allow_coupon,activity_status,rule_version FROM activity ORDER BY activity_id"):
    w("  ", r)

# 3. activity_rule / benefit
w("\n== 3. activity_rule ==")
for r in qall("SELECT rule_id,activity_id,tier_no,threshold_type,threshold_value,reduce_amount,free_shipping FROM activity_rule ORDER BY rule_id"):
    w("  ", r)
w("== 3b. activity_rule_benefit ==")
for r in qall("SELECT benefit_id,rule_id,benefit_type,gift_product_no,gift_product_name,gift_qty FROM activity_rule_benefit ORDER BY benefit_id"):
    w("  ", r)

# 4. activity_scope 按活动+类别统计
w("\n== 4. activity_scope 分布 ==")
for r in qall("SELECT activity_id, scope_category, scope_dimension, COUNT(*) FROM activity_scope GROUP BY activity_id, scope_category, scope_dimension ORDER BY activity_id, scope_category"):
    w("  ", r)
w("  activity_scope 合计 =", q1("SELECT COUNT(*) FROM activity_scope")[0])
w("  满赠(2) 商品范围取值样例(前20):")
for r in qall("SELECT scope_value FROM activity_scope WHERE activity_id=2 AND scope_category='商品' ORDER BY scope_value LIMIT 20"):
    w("     ", r[0])

# 5. result_fee
w("\n== 5. result_fee 全部 ==")
for r in qall("SELECT fee_id,tpm_id,activity_id,actual_discount_total,gift_cost_total,fee_bearer,settle_target,budget_amount,budget_reserve_no,settle_amount,diff_amount,settle_status,calc_batch_id FROM result_fee ORDER BY fee_id"):
    w("  ", r)

# 6. result_calc_batch
w("\n== 6. result_calc_batch ==")
for r in qall("SELECT calc_batch_id,calc_date,rule_version,input_batch_id,operator,created_at FROM result_calc_batch ORDER BY calc_batch_id"):
    w("  ", r)

# 7. result_quality_issue 全部
w("\n== 7. result_quality_issue 全部 ==")
for r in qall("SELECT issue_id,calc_batch_id,level,issue_type,order_no,reason FROM result_quality_issue ORDER BY calc_batch_id, issue_id"):
    w("  ", r)
w("  按批次计数:", qall("SELECT calc_batch_id, COUNT(*) FROM result_quality_issue GROUP BY calc_batch_id ORDER BY calc_batch_id"))

# 8. rule_catalog
w("\n== 8. rule_catalog ==")
for r in qall("SELECT rule_id,rule_topic,version,effective_from,confirmed_by,scope FROM rule_catalog ORDER BY rule_id"):
    w("  ", r)

# 9. coupon_ledger
w("\n== 9. coupon_ledger 全部 ==")
for r in qall("SELECT coupon_id,dealer_platform_id,coupon_no,coupon_name,customer_id,salesperson_name,receive_time,use_period,coupon_status,use_time,use_order_no,discount_amount,fee_month FROM coupon_ledger ORDER BY coupon_id"):
    w("  ", r)
w("  券->订单关联核验:")
for r in qall("""SELECT cl.coupon_no, cl.use_order_no, oh.order_id, oh.order_status, oh.order_time
                 FROM coupon_ledger cl LEFT JOIN order_header oh
                   ON oh.order_no = cl.use_order_no AND oh.dealer_platform_id = cl.dealer_platform_id"""):
    w("     ", r)

# 10. raw_import_batch / raw_file
w("\n== 10. raw_import_batch ==")
for r in qall("SELECT batch_id,batch_code,source_platform,dealer_name,imported_at,operator FROM raw_import_batch ORDER BY batch_id"):
    w("  ", r)
w("== 10b. raw_file (按批次) ==")
for r in qall("SELECT batch_id, COUNT(*), GROUP_CONCAT(module) FROM raw_file GROUP BY batch_id ORDER BY batch_id"):
    w("  ", r)
w("== 10c. raw_file 明细 ==")
for r in qall("SELECT file_id,batch_id,module,file_name,file_signature,read_method,data_rows FROM raw_file ORDER BY file_id"):
    w("  ", r)

# 11. entitlement / release 复核
w("\n== 11. result_entitlement 复核 ==")
w("  总数 =", q1("SELECT COUNT(*) FROM result_entitlement")[0])
w("  按批次一致性:", qall("SELECT calc_batch_id, consistency, COUNT(*) FROM result_entitlement GROUP BY calc_batch_id, consistency ORDER BY calc_batch_id"))
w("  满减(1) Σ理论/Σ实际:", q1("SELECT SUM(theoretical_benefit), SUM(platform_actual_benefit) FROM result_entitlement WHERE calc_batch_id=1"))
w("  满赠(2) Σ应赠/Σ实赠/Σ理论金额/Σ实际金额:", q1("SELECT SUM(gift_qty_entitled), SUM(gift_qty_actual), SUM(theoretical_benefit), SUM(platform_actual_benefit) FROM result_entitlement WHERE calc_batch_id=2"))
w("== 11b. result_release_candidate 复核 ==")
w("  按批次是否候选:", qall("SELECT calc_batch_id, is_candidate, COUNT(*) FROM result_release_candidate GROUP BY calc_batch_id, is_candidate ORDER BY calc_batch_id, is_candidate"))

# 12. 主数据/匹配缺口
w("\n== 12. 匹配缺口 ==")
w("  customer 总数 =", q1("SELECT COUNT(*) FROM customer")[0])
w("  customer_type 空值数 =", q1("SELECT COUNT(*) FROM customer WHERE customer_type IS NULL OR customer_type=''")[0])
w("  customer_type 分布:")
for r in qall("SELECT COALESCE(NULLIF(customer_type,''),'(空)'), COUNT(*) FROM customer GROUP BY COALESCE(NULLIF(customer_type,''),'(空)') ORDER BY COUNT(*) DESC"):
    w("     ", r)
w("  order_header 总数 =", q1("SELECT COUNT(*) FROM order_header")[0])
w("  order_header customer_id 空值 =", q1("SELECT COUNT(*) FROM order_header WHERE customer_id IS NULL")[0])
w("  order_line 总数 =", q1("SELECT COUNT(*) FROM order_line")[0])
w("  order_line product_id 空值 =", q1("SELECT COUNT(*) FROM order_line WHERE product_id IS NULL")[0])
w("  product_id 空值占比 =", round(100.0*q1("SELECT COUNT(*) FROM order_line WHERE product_id IS NULL")[0]/q1("SELECT COUNT(*) FROM order_line")[0], 2), "%")
w("  product 总数 =", q1("SELECT COUNT(*) FROM product")[0])
w("  cross_mapping 总数 =", q1("SELECT COUNT(*) FROM cross_mapping")[0])

# 13. tpm_application
w("\n== 13. tpm_application ==")
for r in qall("SELECT tpm_id,tpm_code,apply_amount,fee_pay_dept,invoice_title,plan_start,plan_end,approval_status FROM tpm_application ORDER BY tpm_id"):
    w("  ", r)

# 14. dealer_platform
w("\n== 14. dealer_platform ==")
for r in qall("SELECT dealer_platform_id,dealer_name,platform_name,swire_partner_code,admission_status FROM dealer_platform ORDER BY dealer_platform_id"):
    w("  ", r)

# 15. fulfillment T-2
w("\n== 15. fulfillment ==")
w("  总数 =", q1("SELECT COUNT(*) FROM fulfillment")[0])
w("  t2_release_candidate 分布:", qall("SELECT t2_release_candidate, COUNT(*) FROM fulfillment GROUP BY t2_release_candidate"))

# 16. FK
w("\n== 16. FK violations(应空) ==")
w("  ", qall("PRAGMA foreign_key_check"))

con.close(); rep.close()
print("WROTE", OUT)
