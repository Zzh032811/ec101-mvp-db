# -*- coding: utf-8 -*-
import sqlite3
db = sqlite3.connect("ec101_mvp.db"); c = db.cursor()
def q(sql):
    return c.execute(sql).fetchone()[0]
print("result_quality_issue 全库:", q("SELECT COUNT(*) FROM result_quality_issue"))
print("  羿柏(batch11):", q("SELECT COUNT(*) FROM result_quality_issue WHERE calc_batch_id=11"))
print("  兴路强(非batch11):", q("SELECT COUNT(*) FROM result_quality_issue WHERE calc_batch_id!=11 OR calc_batch_id IS NULL"))
print("  issue_id=66 存在:", q("SELECT COUNT(*) FROM result_quality_issue WHERE issue_id=66"))
print("FK违例:", c.execute("PRAGMA foreign_key_check").fetchall())
print("-- 结算数字未变(证据) --")
print("  实赠抱枕(order_activity gift_qty_actual sum, activity18):",
      q("SELECT SUM(gift_qty_actual) FROM order_activity WHERE activity_id=18"))
print("  满赠合格/一致/差异:",
      c.execute("SELECT consistency, COUNT(*) FROM result_entitlement WHERE order_activity_id IN (SELECT order_activity_id FROM order_activity WHERE activity_id=18) GROUP BY consistency").fetchall())
print("  返券 fee actual_discount_total:",
      c.execute("SELECT fee_id, actual_discount_total, settle_status FROM result_fee WHERE calc_batch_id=11").fetchall())
print("  release 候选(羿柏):",
      c.execute("SELECT is_candidate, COUNT(*) FROM result_release_candidate WHERE calc_batch_id=11 GROUP BY is_candidate").fetchall())
print("  兴路强 order_header/result_fee:",
      q("SELECT COUNT(*) FROM order_header WHERE dealer_platform_id=1"),
      c.execute("SELECT COUNT(*) FROM result_fee WHERE calc_batch_id IN (1,2,3)").fetchone()[0])
db.close()
