# -*- coding: utf-8 -*-
"""舟谱/羿柏 接入后 独立端到端验证 (只读). 对应计划"验证"12项.
不信任 ingest 报告: 直接查已 commit 的活库; 隔离性对比加载前备份库.
用法: PYTHONIOENCODING=utf-8 python verify_zhoupu.py
"""
import os
import sqlite3

HERE = os.path.dirname(os.path.abspath(__file__))
MVP = os.path.dirname(HERE)
DB = os.path.join(MVP, "ec101_mvp.db")
BAK = os.path.join(MVP, "ec101_mvp.db.bak-pre-zhoupu-20260923")

con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row
cur = con.cursor()

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(("  [PASS] " if cond else "  [FAIL] ") + name + (("  — " + detail) if detail else ""))


def one(sql, args=()):
    return cur.execute(sql, args).fetchone()[0]


# 定位平台 id
XL = one("SELECT dealer_platform_id FROM dealer_platform WHERE platform_name<>'舟谱' LIMIT 1")
ZP = one("SELECT dealer_platform_id FROM dealer_platform WHERE dealer_name='羿柏' AND platform_name='舟谱'")
print("=" * 78)
print("独立验证  兴路强 dealer_platform_id=%s   羿柏/舟谱 dealer_platform_id=%s" % (XL, ZP))
print("=" * 78)

# ── #2 DDL 加列 ──
print("\n[#2] order_header.downstream_order_no 列")
cols = [r[1] for r in cur.execute("PRAGMA table_info(order_header)")]
check("downstream_order_no 列存在", "downstream_order_no" in cols)
xl_notnull = one("SELECT count(*) FROM order_header WHERE dealer_platform_id=? AND downstream_order_no IS NOT NULL", (XL,))
check("兴路强既有行 downstream_order_no 全 NULL", xl_notnull == 0, "非空=%d" % xl_notnull)

# ── #3 STANDARD 非空 ──
print("\n[#3] STANDARD 层 std_field_mapping(舟谱)")
n_map = one("SELECT count(*) FROM std_field_mapping WHERE platform='舟谱'")
check("舟谱映射行 > 0", n_map > 0, "共 %d 行" % n_map)
for raw, mod, exp in [("片区", "客户资料", "客户区域"), ("支付时间", "订单明细", "支付方式"),
                      ("客户助记码", "订单履约", "客户助记码"), ("单据", "订单履约", "XD单号")]:
    got = one("SELECT ec101_field FROM std_field_mapping WHERE platform='舟谱' AND module=? AND raw_field=?", (mod, raw))
    check("抽查 %s.%s -> %s" % (mod, raw, exp), got == exp, "实得=%s" % got)

# ── #4 隔离性 (对比加载前备份库) ──
print("\n[#4] 隔离性 — 兴路强计数 活库 vs 加载前备份库")
cur.execute("ATTACH DATABASE ? AS bak", (BAK,))
iso_ok = True
for t in ("customer", "product", "order_header", "order_line", "fulfillment"):
    if t in ("order_line", "fulfillment"):
        live = one("SELECT count(*) FROM %s WHERE order_id IN (SELECT order_id FROM order_header WHERE dealer_platform_id=?)" % t, (XL,))
        bakn = one("SELECT count(*) FROM bak.%s WHERE order_id IN (SELECT order_id FROM bak.order_header WHERE dealer_platform_id=?)" % t, (XL,))
    else:
        live = one("SELECT count(*) FROM %s WHERE dealer_platform_id=?" % t, (XL,))
        bakn = one("SELECT count(*) FROM bak.%s WHERE dealer_platform_id=?" % t, (XL,))
    ok = live == bakn
    iso_ok = iso_ok and ok
    print("    %-14s live=%-7d bak=%-7d Δ=%+d %s" % (t, live, bakn, live - bakn, "OK" if ok else "!!变化!!"))
check("兴路强五表逐一不变", iso_ok)
# 备份库应无舟谱
bak_zp = one("SELECT count(*) FROM bak.dealer_platform WHERE platform_name='舟谱'")
check("备份库确无舟谱(证明对比基线正确)", bak_zp == 0, "舟谱行=%d" % bak_zp)
cur.execute("DETACH DATABASE bak")

# ── #5 主数据 ──
print("\n[#5] 羿柏主数据")
nc = one("SELECT count(*) FROM customer WHERE dealer_platform_id=?", (ZP,))
np_ = one("SELECT count(*) FROM product WHERE dealer_platform_id=?", (ZP,))
print("    customer=%d  product=%d" % (nc, np_))
check("客户 platform_customer_no 全非空", one("SELECT count(*) FROM customer WHERE dealer_platform_id=? AND (platform_customer_no IS NULL OR platform_customer_no='')", (ZP,)) == 0)
check("客户复合键唯一", one("SELECT count(*) FROM (SELECT platform_customer_no FROM customer WHERE dealer_platform_id=? GROUP BY platform_customer_no HAVING count(*)>1)", (ZP,)) == 0)
check("商品 platform_product_no 全非空", one("SELECT count(*) FROM product WHERE dealer_platform_id=? AND (platform_product_no IS NULL OR platform_product_no='')", (ZP,)) == 0)
check("商品编号唯一", one("SELECT count(*) FROM (SELECT platform_product_no FROM product WHERE dealer_platform_id=? GROUP BY platform_product_no HAVING count(*)>1)", (ZP,)) == 0)
s = cur.execute("SELECT platform_customer_no FROM customer WHERE dealer_platform_id=? AND platform_customer_no LIKE '%|%' LIMIT 3", (ZP,)).fetchall()
check("客户复合键含分隔符 '|' 且格式=名称|助记码", len(s) == 3, "样例=%s" % [r[0] for r in s])

# ── #6 SXD 订单 ──
print("\n[#6] 羿柏 SXD 订单")
noh = one("SELECT count(*) FROM order_header WHERE dealer_platform_id=?", (ZP,))
n_sxd = one("SELECT count(*) FROM order_header WHERE dealer_platform_id=? AND order_source IS NULL", (ZP,))
n_xdonly = one("SELECT count(*) FROM order_header WHERE dealer_platform_id=? AND order_source='XD履约(无SXD)'", (ZP,))
check("order_header=6697 (SXD4053 + XD-only2644)", noh == 6697 and n_sxd == 4053 and n_xdonly == 2644,
      "总=%d SXD=%d XD-only=%d" % (noh, n_sxd, n_xdonly))
fk = cur.execute("PRAGMA foreign_key_check").fetchall()
check("PRAGMA foreign_key_check 无输出", not fk, str(fk[:3]))
check("order_header.order_time 全非空(NOT NULL守卫)", one("SELECT count(*) FROM order_header WHERE dealer_platform_id=? AND (order_time IS NULL OR order_time='')", (ZP,)) == 0)
check("order_header.order_status 全非空", one("SELECT count(*) FROM order_header WHERE dealer_platform_id=? AND (order_status IS NULL OR order_status='')", (ZP,)) == 0)
# 抽样订单
r = cur.execute("SELECT order_id,order_no,downstream_order_no,order_status,customer_id FROM order_header WHERE dealer_platform_id=? AND order_no='SXD260827000153'", (ZP,)).fetchone()
check("抽样 SXD260827000153 存在", r is not None)
if r:
    check("  其 downstream=XD260827000227", r["downstream_order_no"] == "XD260827000227", str(r["downstream_order_no"]))
    check("  其 order_status=已完成(XD权威)", r["order_status"] == "已完成", str(r["order_status"]))
    nl = one("SELECT count(*) FROM order_line WHERE order_id=?", (r["order_id"],))
    check("  其 order_line=16 行", nl == 16, "实得=%d" % nl)
    check("  其 customer_id 非空(桥命中)", r["customer_id"] is not None, str(r["customer_id"]))

# ── #6b XD-only 建单 (XD驱动结算改造 2026-09-24) ──
print("\n[#6b] XD-only 建单 (order_source='XD履约(无SXD)')")
check("XD-only建单=2644", n_xdonly == 2644, "实得=%d" % n_xdonly)
xd_no_cust = one("SELECT count(*) FROM order_header WHERE dealer_platform_id=? AND order_source='XD履约(无SXD)' AND customer_id IS NULL", (ZP,))
check("XD-only客户桥全命中(customer_id无置空)", xd_no_cust == 0, "置空=%d" % xd_no_cust)
check("XD表尾'合计'总计行未误建单", one("SELECT count(*) FROM order_header WHERE dealer_platform_id=? AND order_no='合计'", (ZP,)) == 0)
check("TD退货单未建单", one("SELECT count(*) FROM order_header WHERE dealer_platform_id=? AND order_no LIKE 'TD%'", (ZP,)) == 0)

# ── #7 过桥命中率 ──
print("\n[#7] SXD→XD 过桥 + XD-only 履约")
n_down = one("SELECT count(*) FROM order_header WHERE dealer_platform_id=? AND downstream_order_no IS NOT NULL AND downstream_order_no<>''", (ZP,))
n_ful = one("SELECT count(*) FROM fulfillment WHERE order_id IN (SELECT order_id FROM order_header WHERE dealer_platform_id=?)", (ZP,))
n_ful_sxd = one("SELECT count(*) FROM fulfillment WHERE order_id IN (SELECT order_id FROM order_header WHERE dealer_platform_id=? AND order_source IS NULL)", (ZP,))
print("    有下游编号=%d  fulfillment总=%d (SXD命中=%d + XD-only=%d)  SXD无XD=%d" % (n_down, n_ful, n_ful_sxd, n_ful - n_ful_sxd, n_sxd - n_ful_sxd))
check("SXD→XD命中=3474", n_ful_sxd == 3474, "实得=%d" % n_ful_sxd)
check("SXD无XD=579", n_sxd - n_ful_sxd == 579, "实得=%d" % (n_sxd - n_ful_sxd))
check("有下游编号=4050(XD-only downstream全NULL)", n_down == 4050, "实得=%d" % n_down)
check("XD-only均有fulfillment=2644", n_ful - n_ful_sxd == 2644, "实得=%d" % (n_ful - n_ful_sxd))

# ── #8 客户三级命中 (DB侧) ──
print("\n[#8] 客户匹配 (order_header.customer_id)")
cust_null = one("SELECT count(*) FROM order_header WHERE dealer_platform_id=? AND customer_id IS NULL", (ZP,))
check("customer_id 置空=1 (D_none 洋洋百货)", cust_null == 1, "实得=%d" % cust_null)
# 所有非空 customer_id 必须指向羿柏客户
bad_cid = one("SELECT count(*) FROM order_header WHERE dealer_platform_id=? AND customer_id IS NOT NULL AND customer_id NOT IN (SELECT customer_id FROM customer WHERE dealer_platform_id=?)", (ZP, ZP))
check("非空 customer_id 全指向羿柏客户(无跨平台错配)", bad_cid == 0, "越界=%d" % bad_cid)

# ── #8b 商品三级命中 (DB侧) ──
print("\n[#8b] 商品匹配 (order_line.product_id)")
nol = one("SELECT count(*) FROM order_line WHERE order_id IN (SELECT order_id FROM order_header WHERE dealer_platform_id=?)", (ZP,))
prod_null = one("SELECT count(*) FROM order_line WHERE order_id IN (SELECT order_id FROM order_header WHERE dealer_platform_id=?) AND product_id IS NULL", (ZP,))
print("    order_line=%d  product_id置空=%d" % (nol, prod_null))
check("order_line=76055 (SXD61412 + XD-only14643)", nol == 76055, "实得=%d" % nol)
check("product_id 置空=86 (SXD83 + XD-only3; 赠品/劲酒未桥接)", prod_null == 86, "实得=%d" % prod_null)
bad_pid = one("SELECT count(*) FROM order_line WHERE order_id IN (SELECT order_id FROM order_header WHERE dealer_platform_id=?) AND product_id IS NOT NULL AND product_id NOT IN (SELECT product_id FROM product WHERE dealer_platform_id=?)", (ZP, ZP))
check("非空 product_id 全指向羿柏商品", bad_pid == 0, "越界=%d" % bad_pid)
# 关键: 宝矿力500ml 的 platform_product_no 非空(=XD商品id桥). 按名称定位, 不硬编码易变的自增id(重灌后id会漂移).
pid_baokuangli = one("SELECT product_id FROM product WHERE dealer_platform_id=? AND product_name LIKE '宝矿力500ml%' LIMIT 1", (ZP,))
if pid_baokuangli is not None:
    pno = one("SELECT platform_product_no FROM product WHERE product_id=?", (pid_baokuangli,))
    check("宝矿力500ml platform_product_no(=XD商品id) 非空", pno not in (None, ""), "product_id=%s 商品唯一序号=%s" % (pid_baokuangli, pno))
else:
    check("宝矿力500ml 存在于羿柏商品主数据", False, "按名称未找到")

# ── #9 order_status 取 XD (决策5) ──
print("\n[#9] order_status 权威口径 (决策5)")
# 所有 XD命中单: order_header.order_status 必=fulfillment.order_status(XD聚合)
mism = one("""SELECT count(*) FROM fulfillment f JOIN order_header h ON f.order_id=h.order_id
              WHERE h.dealer_platform_id=? AND h.order_status<>f.order_status""", (ZP,))
check("XD命中单 order_header.status 全=fulfillment.status(即取XD)", mism == 0, "不一致=%d" % mism)
# 待签收/待出库 的羿柏单必然有 fulfillment(=来自XD), 证明这些非完成态是XD权威值
non_done_no_ful = one("""SELECT count(*) FROM order_header h WHERE h.dealer_platform_id=?
                         AND h.order_status IN ('待签收','待出库','待入库','待审核')
                         AND h.order_id NOT IN (SELECT order_id FROM fulfillment)""", (ZP,))
check("非完成态(待签收/待出库..)全部来自XD(有fulfillment)", non_done_no_ful == 0, "无fulfillment却非完成=%d" % non_done_no_ful)
print("    羿柏 order_status 分布:", dict((r[0], r[1]) for r in cur.execute("SELECT order_status,count(*) FROM order_header WHERE dealer_platform_id=? GROUP BY order_status", (ZP,))))

# ── #9b fulfillment ──
print("\n[#9b] fulfillment")
check("fulfillment总=6118 (SXD命中3474 + XD-only2644)", n_ful == 6118, "实得=%d" % n_ful)
check("fulfillment.order_id 唯一(1:1)", one("SELECT count(*) FROM (SELECT order_id FROM fulfillment GROUP BY order_id HAVING count(*)>1)") == 0)
check("fulfillment.order_status 全非空", one("SELECT count(*) FROM fulfillment WHERE order_status IS NULL OR order_status=''") == 0)
ret_null = one("SELECT count(*) FROM fulfillment WHERE order_id IN (SELECT order_id FROM order_header WHERE dealer_platform_id=?) AND return_qty IS NULL", (ZP,))
ret_notnull = n_ful - ret_null
print("    return_qty: NULL=%d  非NULL=%d (满赠XD无该列→NULL; 满减有退货才非NULL)" % (ret_null, ret_notnull))
check("t2_release_candidate 全=0 (核算轮再算)", one("SELECT count(*) FROM fulfillment WHERE order_id IN (SELECT order_id FROM order_header WHERE dealer_platform_id=?) AND t2_release_candidate<>0", (ZP,)) == 0)

# ── 决策: order_line.return_qty 留空(无退货冲回) ──
print("\n[范围] order_line.return_qty 留空(答案C: 舟谱不算退货冲回)")
check("order_line.return_qty 全 NULL", one("SELECT count(*) FROM order_line WHERE order_id IN (SELECT order_id FROM order_header WHERE dealer_platform_id=?) AND return_qty IS NOT NULL", (ZP,)) == 0)

# ── #10 血缘 ──
print("\n[#10] RAW 血缘")
nb = one("SELECT count(*) FROM raw_import_batch WHERE batch_code='ZHOUPU-YIBAI-MASTER-ORDER-XD-20260923'")
check("raw_import_batch=1 行", nb == 1, "实得=%d" % nb)
bid = one("SELECT batch_id FROM raw_import_batch WHERE batch_code='ZHOUPU-YIBAI-MASTER-ORDER-XD-20260923'")
nf = one("SELECT count(*) FROM raw_file WHERE batch_id=?", (bid,))
check("raw_file=12 行", nf == 12, "实得=%d" % nf)
check("raw_file header_row 全=4", one("SELECT count(*) FROM raw_file WHERE batch_id=? AND header_row<>4", (bid,)) == 0)
mods = dict((r[0], r[1]) for r in cur.execute("SELECT module,count(*) FROM raw_file WHERE batch_id=? GROUP BY module", (bid,)))
print("    模块分布:", mods)

# ── #12 冲突检测 ──
print("\n[#12] 冲突检测")
dupname = one("SELECT count(*) FROM (SELECT customer_name FROM customer WHERE dealer_platform_id=? GROUP BY customer_name HAVING count(*)>1)", (ZP,))
print("    羿柏客户重名组=%d (助记码入键后重名不一定歧义)" % dupname)
dupline = one("SELECT count(*) FROM (SELECT order_id,product_id FROM order_line WHERE order_id IN (SELECT order_id FROM order_header WHERE dealer_platform_id=?) AND product_id IS NOT NULL GROUP BY order_id,product_id HAVING count(*)>1)", (ZP,))
check("order_line 无重复(order_id,product_id) [UNIQUE守住]", dupline == 0, "重复组=%d" % dupline)

print("\n" + "=" * 78)
print("验证结果: PASS=%d  FAIL=%d" % (len(PASS), len(FAIL)))
if FAIL:
    print("失败项:")
    for f in FAIL:
        print("   -", f)
else:
    print("全部通过 ✅")
print("=" * 78)
con.close()
