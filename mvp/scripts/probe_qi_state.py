# -*- coding: utf-8 -*-
import sqlite3
db = sqlite3.connect("ec101_mvp.db")
c = db.cursor()
print("== columns ==")
for r in c.execute("PRAGMA table_info(result_quality_issue)"):
    print(r[1], r[2])
print("== max issue_id ==")
print(c.execute("SELECT MAX(issue_id), COUNT(*) FROM result_quality_issue").fetchone())
print("== 羿柏(calc_batch=11) rows ==")
for r in c.execute("SELECT issue_id,level,issue_type,calc_batch_id FROM result_quality_issue WHERE calc_batch_id=11 ORDER BY issue_id"):
    print(r)
print("== issue_id 65 detail ==")
print(c.execute("SELECT * FROM result_quality_issue WHERE issue_id=65").fetchone())
db.close()
