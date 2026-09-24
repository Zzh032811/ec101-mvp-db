# -*- coding: utf-8 -*-
"""只读探查: 为"给舟谱的 XD-only 确认问题清单"准备真实素材(不写库).
抓 order_source='XD履约(无SXD)' 订单的画像 + 样例单号 + 关键论点证据(与被引用XD不相交).
用法: PYTHONIOENCODING=utf-8 python probe_xdonly_profile.py
"""
import os, sqlite3

MVP = r"D:\Peggy zhan\智能EC101\数据底座\第三阶段数据库设计\mvp"
DB = os.path.join(MVP, "ec101_mvp.db")
con = sqlite3.connect(DB); con.row_factory = sqlite3.Row; cur = con.cursor()
ZP = cur.execute("SELECT dealer_platform_id FROM dealer_platform WHERE dealer_name='羿柏' AND platform_name='舟谱'").fetchone()[0]
SRC = "XD履约(无SXD)"


def one(sql, a=()): return cur.execute(sql, a).fetchone()[0]
def rows(sql, a=()): return cur.execute(sql, a).fetchall()


print("=" * 72)
print("order_header 列:", [r[1] for r in rows("PRAGMA table_info(order_header)")])
print("fulfillment  列:", [r[1] for r in rows("PRAGMA table_info(fulfillment)")])
print("=" * 72)

n = one("SELECT count(*) FROM order_header WHERE dealer_platform_id=? AND order_source=?", (ZP, SRC))
print(f"\n[XD-only 总数] {n}")

print("\n[状态分布]")
for r in rows("SELECT order_status,count(*) c FROM order_header WHERE dealer_platform_id=? AND order_source=? GROUP BY order_status ORDER BY c DESC", (ZP, SRC)):
    print(f"  {r[0]}: {r[1]}")

print("\n[单号前缀分布]")
for r in rows("SELECT substr(order_no,1,2) p,count(*) c FROM order_header WHERE dealer_platform_id=? AND order_source=? GROUP BY p ORDER BY c DESC", (ZP, SRC)):
    print(f"  前缀'{r[0]}': {r[1]}")

nn = one("SELECT count(*) FROM order_header WHERE dealer_platform_id=? AND order_source=? AND downstream_order_no IS NOT NULL AND downstream_order_no<>''", (ZP, SRC))
print(f"\n[downstream_order_no 非空] {nn} (应=0: XD-only 无下游号)")

cn = one("SELECT count(*) FROM order_header WHERE dealer_platform_id=? AND order_source=? AND customer_id IS NULL", (ZP, SRC))
ncust = one("SELECT count(DISTINCT customer_id) FROM order_header WHERE dealer_platform_id=? AND order_source=?", (ZP, SRC))
print(f"[客户桥] customer_id 置空={cn} (应=0)  涉及去重客户数={ncust}")

print("\n[完成时间月份分布 fulfillment.completed_at]")
for r in rows("""SELECT substr(f.completed_at,1,7) m,count(*) c FROM fulfillment f
                 JOIN order_header h ON h.order_id=f.order_id
                 WHERE h.dealer_platform_id=? AND h.order_source=? AND f.completed_at IS NOT NULL AND f.completed_at<>''
                 GROUP BY m ORDER BY m""", (ZP, SRC)):
    print(f"  {r[0]}: {r[1]}")

amt = one("""SELECT round(sum(ol.pre_discount_amount),2) FROM order_line ol
             JOIN order_header h ON h.order_id=ol.order_id
             WHERE h.dealer_platform_id=? AND h.order_source=?""", (ZP, SRC))
nline = one("""SELECT count(*) FROM order_line ol JOIN order_header h ON h.order_id=ol.order_id
               WHERE h.dealer_platform_id=? AND h.order_source=?""", (ZP, SRC))
print(f"\n[金额/行] XD-only order_line={nline}  优惠前金额合计={amt}")

pil = one("""SELECT count(DISTINCT h.order_id) FROM order_header h
             JOIN order_line ol ON ol.order_id=h.order_id
             JOIN product p ON p.product_id=ol.product_id
             WHERE h.dealer_platform_id=? AND h.order_source=? AND p.product_name='(赠品)雪碧抱枕'""", (ZP, SRC))
pilq = one("""SELECT count(*) FROM (SELECT h.order_id FROM order_header h
             JOIN order_line ol ON ol.order_id=h.order_id JOIN product p ON p.product_id=ol.product_id
             WHERE h.dealer_platform_id=? AND h.order_source=? AND p.product_name LIKE '雪碧%'
             GROUP BY h.order_id HAVING sum(ol.pre_discount_amount)>=100)""", (ZP, SRC))
print(f"[满赠参与] 含'(赠品)雪碧抱枕'的 XD-only 单={pil}  雪碧>=100(满赠合格)的 XD-only 单={pilq}")

print("\n[关键论点: XD-only 单号 与 SXD下游XD单号 是否相交]")
xonly = set(r[0] for r in rows("SELECT order_no FROM order_header WHERE dealer_platform_id=? AND order_source=?", (ZP, SRC)))
ref = set(r[0] for r in rows("SELECT DISTINCT downstream_order_no FROM order_header WHERE dealer_platform_id=? AND downstream_order_no IS NOT NULL AND downstream_order_no<>''", (ZP,)))
print(f"  XD-only 单号数={len(xonly)}  被SXD引用的下游XD单号数={len(ref)}  交集={len(xonly & ref)} (应=0=完全不相交)")

print("\n[样例 XD-only 已完成单 前15 (按完成时间倒序, 给舟谱核查)]")
for r in rows("""SELECT h.order_no, c.customer_name, f.order_status, f.completed_at,
                        (SELECT round(sum(ol.pre_discount_amount),2) FROM order_line ol WHERE ol.order_id=h.order_id) amt,
                        (SELECT count(*) FROM order_line ol WHERE ol.order_id=h.order_id) nl
                 FROM order_header h JOIN fulfillment f ON f.order_id=h.order_id
                 LEFT JOIN customer c ON c.customer_id=h.customer_id
                 WHERE h.dealer_platform_id=? AND h.order_source=? AND f.order_status='已完成'
                 ORDER BY f.completed_at DESC LIMIT 15""", (ZP, SRC)):
    print(f"  {r['order_no']}  客户={r['customer_name']}  完成={r['completed_at']}  金额={r['amt']}  行数={r['nl']}")

print("\n[样例 XD-only 含抱枕单 前8 (满赠相关, 给舟谱核查)]")
for r in rows("""SELECT DISTINCT h.order_no, c.customer_name, f.completed_at
                 FROM order_header h JOIN order_line ol ON ol.order_id=h.order_id
                 JOIN product p ON p.product_id=ol.product_id
                 JOIN fulfillment f ON f.order_id=h.order_id
                 LEFT JOIN customer c ON c.customer_id=h.customer_id
                 WHERE h.dealer_platform_id=? AND h.order_source=? AND p.product_name='(赠品)雪碧抱枕'
                 ORDER BY f.completed_at DESC LIMIT 8""", (ZP, SRC)):
    print(f"  {r['order_no']}  客户={r['customer_name']}  完成={r['completed_at']}")

con.close()
