# -*- coding: utf-8 -*-
"""灌 std_field_mapping (platform=舟谱) — 配置驱动映射真源.

来源:
  skill outputs/*/run.json 中 platform=='舟谱' 的 field_mappings, 只取"真实列名"行
  (排除 经销商原始字段 为 '—'/'Skill计算' 的 Gap/计算行, 避免 UNIQUE(platform,module,raw_field) 撞键).

手工补 (run.json 基于 phase-2, 不满足本轮 phase-3 两层加载):
  (A) SXD 订单明细: 3 个"本轮需要但被 skill 标为非V1"的列 -> INSERT OR REPLACE 翻正为 V1
      下游订单编号 -> 下游订单编号 (order_header.downstream_order_no)
      订单数量（大） -> 订货数量   (满减 SXD 数量列别名)
      单位名称（大） -> 订货单位   (满减 SXD 单位列别名)
  (B) XD 履约侧: module='订单履约' 全新手工映射 (skill 把 XD 列丢进"销售明细"且全标非V1)

幂等: 先 DELETE FROM std_field_mapping WHERE platform='舟谱'; 只动舟谱, 不碰其他平台.
用法: python seed_std_mapping_zhoupu.py [--dry]
"""
import os, sys, json, glob, sqlite3

HERE  = os.path.dirname(os.path.abspath(__file__))
MVP   = os.path.dirname(HERE)
sys.path.insert(0, HERE)
DB    = os.path.join(MVP, "ec101_mvp.db")
BASE3 = r"D:\Peggy zhan\智能EC101\数据底座\第三阶段数据库设计"
OUT   = os.path.join(BASE3, "ec101-promotion-closure-validator",
                     "ec101-promotion-closure-validator", "outputs")
DRY   = "--dry" in sys.argv

REAL_EXCLUDE = {"—", "Skill计算", ""}

# (A) 翻正为 V1 的列: (module, raw_field, ec101_field)
#   skill 基于 phase-2 把这些标为非V1, 但本轮两层加载/匹配需要它们进入映射字典.
OVERRIDES = [
    ("客户资料", "助记码",       "客户助记码"),     # 客户复合主键 名称|助记码 的组成部分
    ("订单明细", "下游订单编号",   "下游订单编号"),   # -> order_header.downstream_order_no
    ("订单明细", "订单数量（大）", "订货数量"),       # 满减 SXD 数量列别名
    ("订单明细", "单位名称（大）", "订货单位"),       # 满减 SXD 单位列别名
    ("订单明细", "客户名称",       "客户名称"),       # 客户名称回退匹配用
    ("订单明细", "商品条码",       "商品条码"),       # 商品条码回退匹配用
    ("商品资料", "小单位条码",     "商品条码"),       # -> product.barcode (SXD 订单行按此回连)
]

# (B) XD 履约侧 module='订单履约' 手工映射: (raw_field, ec101_field)
XD_FULFILL_MAP = [
    ("单据",        "XD单号"),
    ("商品id",      "商品id"),
    ("条形码",      "商品条码"),
    ("商品名称",     "商品名称"),
    ("客户名称",     "客户名称"),
    ("客户助记码",   "客户助记码"),
    ("老板电话",     "老板电话"),
    ("客户片区",     "客户区域"),
    ("客户等级",     "客户等级"),
    ("订单状态",     "履约订单状态"),
    ("结款状态",     "结款状态"),
    ("签收时间",     "完成时间"),
    ("出(入)库时间", "出库时间"),
    ("退货结算数量", "退货数量"),
]


def find_zhoupu_runjson():
    cands = sorted(glob.glob(os.path.join(OUT, "*", "run.json")))
    for p in cands:
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
        if data.get("platform") == "舟谱":
            return p, data
    raise SystemExit(f"未找到 platform=='舟谱' 的 run.json; 候选={cands}")


def upsert(cur, module, raw, ec, confidence, is_non_v1, gap):
    cur.execute(
        """INSERT OR REPLACE INTO std_field_mapping
           (platform,module,raw_field,ec101_field,confidence,is_non_v1,gap_flag)
           VALUES('舟谱',?,?,?,?,?,?)""",
        (module, raw, ec, confidence, is_non_v1, gap))


def main():
    if not os.path.exists(DB):
        raise SystemExit(f"DB 不存在: {DB}")
    con = sqlite3.connect(DB)
    cur = con.cursor()
    if not cur.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='std_field_mapping'").fetchone():
        raise SystemExit("std_field_mapping 表不存在; 请先确认 DDL 已建库")

    before_other = cur.execute(
        "SELECT COUNT(*) FROM std_field_mapping WHERE platform<>'舟谱'").fetchone()[0]
    cur.execute("DELETE FROM std_field_mapping WHERE platform='舟谱'")

    path, data = find_zhoupu_runjson()
    fm = data.get("field_mappings", [])
    n_run = n_ovr = n_xd = 0
    per_module = {}
    for r in fm:
        raw = (r.get("经销商原始字段") or "").strip()
        if raw in REAL_EXCLUDE:
            continue
        module = (r.get("模块") or "").strip()
        ec = (r.get("EC101标准字段") or "").strip()
        ec = None if ec in ("—", "") else ec
        conf = (r.get("证据等级") or "").strip() or None
        is_non_v1 = 1 if r.get("字段关系") == "非V1字段" else 0
        gap = (r.get("状态") or "").strip() or None
        if not DRY:
            upsert(cur, module, raw, ec, conf, is_non_v1, gap)
        per_module[module] = per_module.get(module, 0) + 1
        n_run += 1

    for module, raw, ec in OVERRIDES:
        if not DRY:
            upsert(cur, module, raw, ec, "高", 0, "已映射(手工翻正V1)")
        n_ovr += 1

    for raw, ec in XD_FULFILL_MAP:
        if not DRY:
            upsert(cur, "订单履约", raw, ec, "高", 0, "已映射(XD手工补)")
        n_xd += 1

    if not DRY:
        con.commit()

    tag = "[DRY-RUN 未写库]" if DRY else "[已写库]"
    print(f"{tag} run.json = {path}")
    print(f"  platform=舟谱 插入: run.json真实列={n_run}  SXD翻正={n_ovr}  XD订单履约={n_xd}  合计={n_run+n_ovr+n_xd}")
    print(f"  run.json 真实列按模块: {per_module}")
    print(f"  其他平台行数(应不变)={before_other}")

    if not DRY:
        import std_mapping
        print("\n== 写库后核验 ==")
        for module in ["客户资料", "商品资料", "订单明细", "订单履约", "销售明细"]:
            tot = cur.execute("SELECT COUNT(*) FROM std_field_mapping WHERE platform='舟谱' AND module=?",
                              (module,)).fetchone()[0]
            v1 = std_mapping.load_mapping(con, "舟谱", module)
            print(f"  模块 {module}: 总行={tot}  V1可加载映射={len(v1)}")
        print("\n== 关键抽查 (V1 映射命中) ==")
        checks = [
            ("客户资料", "片区", "客户区域"),
            ("客户资料", "门店状态", "客户状态"),
            ("商品资料", "商品唯一序号", "平台商品编号"),
            ("商品资料", "单位换算", "箱规"),
            ("商品资料", "小单位条码", "商品条码"),
            ("订单明细", "支付时间", "支付方式"),
            ("订单明细", "客户名称", "客户名称"),
            ("订单明细", "商品条码", "商品条码"),
            ("订单明细", "下游订单编号", "下游订单编号"),
            ("订单明细", "订单数量（大）", "订货数量"),
            ("订单明细", "单位名称（大）", "订货单位"),
            ("订单明细", "实际数量", "订货数量"),
            ("订单履约", "单据", "XD单号"),
            ("订单履约", "客户助记码", "客户助记码"),
            ("订单履约", "订单状态", "履约订单状态"),
            ("订单履约", "签收时间", "完成时间"),
            ("订单履约", "退货结算数量", "退货数量"),
        ]
        for module, raw, expect in checks:
            m = std_mapping.load_mapping(con, "舟谱", module)
            got = m.get(raw)
            flag = "OK" if got == expect else "!!不符"
            print(f"  [{flag}] {module}.{raw} -> {got}  (期望 {expect})")
    con.close()


if __name__ == "__main__":
    main()
