# -*- coding: utf-8 -*-
import sqlite3
db = sqlite3.connect("ec101_mvp.db")
c = db.cursor()
before = c.execute("SELECT COUNT(*), MAX(issue_id) FROM result_quality_issue").fetchone()
reason = (
 "满赠差异43行经数据级分解(2026-09-24):①A类真应赠未赠35行=雪碧≥100合格且履约已完成、但未记赠品(其中8张SXD单+27张XD-only单)→需业务追因(平台漏发/库存不足/窗口外/客户未领);"
 "②B类归因错位8行涉及4客户(汇丰百货/深朗、零食有鸣（大芬）、美又佳（玉岭花园）、44号（11点前/2点后）):每客户'单客≤1次'下应赠合计=实赠合计=1,只是抱枕记在另一张合格单上→净正确,非真缺口,建议改'逐客户比对'口径消除。"
 "返券3张双单号券(ZP-FQ-0025兜点零食(吉祥花园)、ZP-FQ-0087喜临临商行（自提）、ZP-FQ-0088零食有鸣（大芬）;各15元共45元)经核:每张券2个关联单号属同一客户、6单均已'已完成'→券真实有效,仅订单级归因待定(可选计入较早单→720元/按客户计→720元/请舟谱拆分单号维持675元)。"
 "本分析为业务核对输入,未改动任何已入库结算数字(满赠实赠抱枕100、返券675元、release候选179均不变);明细见两份CSV,交太古市场部/业务确认。"
)
c.execute(
 "INSERT INTO result_quality_issue (order_no, issue_type, level, reason, evidence_ref, calc_batch_id) VALUES (?,?,?,?,?,?)",
 (None, "满赠差异43分解+返券3双单号券核实(2026-09-24)", "提示", reason,
  "舟谱-羿柏满赠差异与返券双单号业务核对包-20260924.md", 11))
db.commit()
after = c.execute("SELECT COUNT(*), MAX(issue_id) FROM result_quality_issue").fetchone()
print("before(count,max)=", before, " after=", after)
print("new row:", c.execute("SELECT issue_id,level,issue_type,calc_batch_id FROM result_quality_issue WHERE issue_id=?", (after[1],)).fetchone())
print("羿柏(batch11)行数:", c.execute("SELECT COUNT(*) FROM result_quality_issue WHERE calc_batch_id=11").fetchone()[0])
print("FK check:", c.execute("PRAGMA foreign_key_check").fetchall())
db.close()
