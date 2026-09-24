# -*- coding: utf-8 -*-
"""按 2026-09-22 业务决策修正满赠: 不走TPM(tpm_id=NULL) + 费用改"按赠品数量统计"口径。
同步删除两条已被决策关闭的质量台账(赠品结算单价未确认 / 满赠窗口早于TPM计划开始)。
只改满赠(activity_name='满赠优惠'), 不动满减。可重复执行(幂等)。"""
import io, sqlite3

DB = r'D:\Peggy zhan\智能EC101\数据底座\第三阶段数据库设计\mvp\ec101_mvp.db'
ACT_NAME = '满赠优惠'
SETTLE_STATUS = '按赠品数量统计(不结算单价)'

out = io.open('fix_manzeng_tpm_fee.txt', 'w', encoding='utf-8')
def w(*a): out.write(' '.join(str(x) for x in a) + '\n')

con = sqlite3.connect(DB); cur = con.cursor()
cur.execute('PRAGMA foreign_keys=ON')

aid = cur.execute("SELECT activity_id FROM activity WHERE activity_name=?", (ACT_NAME,)).fetchone()[0]
w('满赠 activity_id =', aid)
w('--- BEFORE ---')
w('activity:', cur.execute("SELECT activity_id,activity_name,tpm_id FROM activity WHERE activity_id=?", (aid,)).fetchall())
w('result_fee:', cur.execute("SELECT fee_id,tpm_id,activity_id,settle_status,gift_cost_total,settle_amount FROM result_fee WHERE activity_id=?", (aid,)).fetchall())
w('quality(满赠批次):', cur.execute("SELECT issue_id,issue_type,level FROM result_quality_issue WHERE calc_batch_id=(SELECT calc_batch_id FROM result_fee WHERE activity_id=?)", (aid,)).fetchall())

# 1. 满赠不走 TPM
cur.execute("UPDATE activity SET tpm_id=NULL WHERE activity_id=?", (aid,))
# 2. 费用改数量口径 + 去 TPM 关联
cur.execute("UPDATE result_fee SET tpm_id=NULL, settle_status=? WHERE activity_id=?", (SETTLE_STATUS, aid))
# 3. 删除两条已决策关闭的质量台账
cur.execute("""DELETE FROM result_quality_issue
               WHERE calc_batch_id=(SELECT calc_batch_id FROM result_fee WHERE activity_id=?)
                 AND issue_type IN ('赠品结算单价未确认','满赠窗口早于TPM计划开始')""", (aid,))
w('deleted quality rows =', cur.rowcount)

con.commit()
w('--- AFTER ---')
w('activity:', cur.execute("SELECT activity_id,activity_name,tpm_id FROM activity WHERE activity_id=?", (aid,)).fetchall())
w('result_fee:', cur.execute("SELECT fee_id,tpm_id,activity_id,settle_status,gift_cost_total,settle_amount FROM result_fee WHERE activity_id=?", (aid,)).fetchall())
w('quality(满赠批次):', cur.execute("SELECT issue_id,issue_type,level FROM result_quality_issue WHERE calc_batch_id=(SELECT calc_batch_id FROM result_fee WHERE activity_id=?)", (aid,)).fetchall())
w('满减 activity tpm_id(应不变):', cur.execute("SELECT activity_id,activity_name,tpm_id FROM activity WHERE activity_name<>?", (ACT_NAME,)).fetchall())
w('满减 result_fee(应不变):', cur.execute("SELECT fee_id,tpm_id,activity_id,settle_status,settle_amount FROM result_fee WHERE activity_id<>?", (aid,)).fetchall())
w('FK violations:', cur.execute("PRAGMA foreign_key_check").fetchall())
con.close(); out.close(); print('done')
