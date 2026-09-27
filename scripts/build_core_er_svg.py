from pathlib import Path
from xml.sax.saxutils import escape


OUT = Path(__file__).resolve().parents[1] / "docs" / "diagrams" / "ec101-mvp-core-er.svg"
W, H = 2200, 1980
BOX_W = 310
ROW_H = 27
HEADER_H = 42

COLORS = {
    "master": ("#E8F5F2", "#167E6D"),
    "order": ("#EEF4FF", "#3B67B1"),
    "activity": ("#FFF4E6", "#B16A13"),
    "mapping": ("#F4EEFF", "#7851A9"),
}


entities = {
    "dealer_platform": {"title": "经销商·平台", "domain": "master", "xy": (890, 50), "rows": [
        ("dealer_platform_id", "INTEGER", "PK", "内部主键"), ("dealer_name", "TEXT", "", "经销商名称"),
        ("platform_name", "TEXT", "", "第三方平台"), ("swire_partner_code", "TEXT", "", "太古合作伙伴编号"),
        ("admission_status", "TEXT", "", "准入状态"),
    ]},
    "tpm_application": {"title": "TPM 促销申请", "domain": "master", "xy": (1270, 50), "rows": [
        ("tpm_id", "INTEGER", "PK", "内部主键"), ("tpm_code", "TEXT", "UK", "TPM 单号"),
        ("theme", "TEXT", "", "促销主题"), ("promo_type", "TEXT", "", "促销类型"),
        ("apply_amount", "NUMERIC", "", "预算金额"), ("fee_pay_dept", "TEXT", "", "费用承担方"),
        ("plan_start / plan_end", "TEXT", "", "计划期间"), ("approval_status", "TEXT", "", "审批状态"),
    ]},
    "customer": {"title": "客户", "domain": "master", "xy": (70, 390), "rows": [
        ("customer_id", "INTEGER", "PK", "内部主键"), ("dealer_platform_id", "INTEGER", "FK", "→ dealer_platform"),
        ("platform_customer_no", "TEXT", "UK", "平台客户编号"), ("customer_name", "TEXT", "", "客户名称"),
        ("customer_type / level", "TEXT", "", "客户类型 / 等级"), ("customer_region", "TEXT", "", "区域"),
        ("salesperson_name", "TEXT", "", "业务员"), ("swire_outlet_no", "TEXT", "", "太古售点号"),
        ("status", "TEXT", "", "状态"),
    ]},
    "product": {"title": "商品", "domain": "master", "xy": (430, 390), "rows": [
        ("product_id", "INTEGER", "PK", "内部主键"), ("dealer_platform_id", "INTEGER", "FK", "→ dealer_platform"),
        ("platform_product_no", "TEXT", "UK", "平台商品编号"), ("product_name", "TEXT", "", "商品名称"),
        ("brand / category", "TEXT", "", "品牌 / 品类"), ("spec / barcode", "TEXT", "", "规格 / 条码"),
        ("base_unit", "TEXT", "", "基本单位"), ("actual_stock", "NUMERIC", "", "实际库存"),
        ("swire_product_code", "TEXT", "", "太古产品代码"),
    ]},
    "activity": {"title": "活动", "domain": "activity", "xy": (890, 390), "rows": [
        ("activity_id", "INTEGER", "PK", "内部主键"), ("dealer_platform_id", "INTEGER", "FK", "→ dealer_platform"),
        ("tpm_id", "INTEGER", "FK", "→ tpm_application"), ("activity_name", "TEXT", "UK", "活动名称"),
        ("activity_category", "TEXT", "", "券类 / 非券类"), ("promotion_type", "TEXT", "", "满减 / 满赠"),
        ("start_time / end_time", "TEXT", "", "活动期间"), ("activity_status", "TEXT", "", "活动状态"),
        ("rule_version", "TEXT", "", "规则版本"),
    ]},
    "order_header": {"title": "订单头", "domain": "order", "xy": (40, 900), "rows": [
        ("order_id", "INTEGER", "PK", "内部主键"), ("dealer_platform_id", "INTEGER", "FK", "→ dealer_platform"),
        ("order_no", "TEXT", "UK", "订单号（字符串）"), ("order_time", "TEXT", "", "下单时间"),
        ("customer_id", "INTEGER", "FK", "→ customer"), ("order_status", "TEXT", "", "订单状态"),
        ("downstream_order_no", "TEXT", "", "下游履约单号"), ("batch_id", "INTEGER", "FK", "→ raw_import_batch"),
    ]},
    "activity_rule": {"title": "活动规则", "domain": "activity", "xy": (890, 900), "rows": [
        ("rule_id", "INTEGER", "PK", "内部主键"), ("activity_id", "INTEGER", "FK", "→ activity"),
        ("tier_no", "INTEGER", "UK", "阶梯序号"), ("threshold_type", "TEXT", "", "金额 / 数量"),
        ("threshold_value", "NUMERIC", "", "门槛值"), ("reduce_amount", "NUMERIC", "", "立减金额"),
        ("free_shipping", "INTEGER", "", "是否免邮"),
    ]},
    "activity_scope": {"title": "活动范围", "domain": "activity", "xy": (1260, 900), "rows": [
        ("scope_id", "INTEGER", "PK", "内部主键"), ("activity_id", "INTEGER", "FK", "→ activity"),
        ("scope_category", "TEXT", "", "商品 / 客户"), ("scope_dimension", "TEXT", "", "品牌 / 商品 / 区域"),
        ("scope_value", "TEXT", "", "范围取值"),
    ]},
    "activity_rule_benefit": {"title": "规则权益", "domain": "activity", "xy": (1630, 900), "rows": [
        ("benefit_id", "INTEGER", "PK", "内部主键"), ("rule_id", "INTEGER", "FK", "→ activity_rule"),
        ("benefit_type", "TEXT", "", "立减 / 赠品 / 送券"), ("gift_product_no", "TEXT", "", "赠品编号"),
        ("gift_product_name", "TEXT", "", "赠品名称"), ("gift_qty", "NUMERIC", "", "赠品数量"),
        ("coupon_id / coupon_name", "TEXT", "", "优惠券信息"),
    ]},
    "order_line": {"title": "订单明细", "domain": "order", "xy": (40, 1430), "rows": [
        ("order_line_id", "INTEGER", "PK", "内部主键"), ("order_id", "INTEGER", "FK", "→ order_header"),
        ("product_id", "INTEGER", "FK", "→ product"), ("order_qty / order_unit", "NUMERIC / TEXT", "", "订货数量 / 单位"),
        ("base_qty / base_unit", "NUMERIC / TEXT", "", "基准数量 / 单位"), ("pre_discount_amount", "NUMERIC", "", "折前金额"),
        ("discount_amount", "NUMERIC", "", "优惠金额"), ("unit_price", "NUMERIC", "", "单价"),
    ]},
    "order_activity": {"title": "订单活动关系", "domain": "activity", "xy": (430, 1430), "rows": [
        ("order_activity_id", "INTEGER", "PK", "内部主键"), ("order_id", "INTEGER", "FK", "→ order_header"),
        ("activity_id", "INTEGER", "FK", "→ activity"), ("rule_id", "INTEGER", "FK", "→ activity_rule"),
        ("activity_product_amount", "NUMERIC", "", "命中商品金额"), ("platform_actual_benefit", "NUMERIC", "", "平台实际权益"),
        ("gift_qty_actual", "NUMERIC", "", "实际赠品数"), ("exec_status", "TEXT", "", "执行状态"),
        ("evidence_ref", "TEXT", "", "证据引用"),
    ]},
    "fulfillment": {"title": "履约", "domain": "order", "xy": (850, 1430), "rows": [
        ("fulfillment_id", "INTEGER", "PK", "内部主键"), ("order_id", "INTEGER", "FK,UK", "→ order_header"),
        ("order_status", "TEXT", "", "履约状态"), ("completed_at", "TEXT", "", "完成时间"),
        ("t2_release_candidate", "INTEGER", "", "T-2 释放候选"), ("return_qty", "NUMERIC", "", "退货数量"),
        ("special_reason", "TEXT", "", "例外原因"),
    ]},
    "coupon_ledger": {"title": "优惠券台账", "domain": "activity", "xy": (1220, 1430), "rows": [
        ("coupon_id", "INTEGER", "PK", "内部主键"), ("dealer_platform_id", "INTEGER", "FK", "→ dealer_platform"),
        ("coupon_no", "TEXT", "UK", "券号（字符串）"), ("coupon_name", "TEXT", "", "券名称"),
        ("customer_id", "INTEGER", "FK", "→ customer"), ("use_order_no", "TEXT", "", "使用订单号"),
        ("coupon_status", "TEXT", "", "券状态"), ("discount_amount", "NUMERIC", "", "优惠金额"),
        ("fee_month", "TEXT", "", "费用月份"),
    ]},
    "cross_mapping": {"title": "跨系统映射", "domain": "mapping", "xy": (1590, 1430), "rows": [
        ("mapping_id", "INTEGER", "PK", "内部主键"), ("dealer_platform_id", "INTEGER", "FK", "→ dealer_platform"),
        ("mapping_object_type", "TEXT", "", "客户 / 商品"), ("ec101_key", "TEXT", "UK", "EC101 主键"),
        ("swire_key", "TEXT", "", "太古侧编号"), ("match_status", "TEXT", "", "匹配状态"),
        ("fuzzy_score", "NUMERIC", "", "模糊匹配分"), ("manual_corrected", "INTEGER", "", "人工修正"),
    ]},
}


edges = [
    ("dealer_platform", "customer", "1:N"), ("dealer_platform", "product", "1:N"),
    ("dealer_platform", "order_header", "1:N"), ("dealer_platform", "activity", "1:N"),
    ("dealer_platform", "coupon_ledger", "1:N"), ("dealer_platform", "cross_mapping", "1:N"),
    ("tpm_application", "activity", "1:N"), ("customer", "order_header", "1:N"),
    ("customer", "coupon_ledger", "1:N"), ("product", "order_line", "1:N"),
    ("order_header", "order_line", "1:N"), ("order_header", "order_activity", "1:N"),
    ("order_header", "fulfillment", "1:1"), ("activity", "activity_rule", "1:N"),
    ("activity", "activity_scope", "1:N"), ("activity", "order_activity", "1:N"),
    ("activity_rule", "activity_rule_benefit", "1:N"), ("activity_rule", "order_activity", "1:N"),
]


def box_height(entity):
    return HEADER_H + len(entity["rows"]) * ROW_H + 12


def anchor(entity, side):
    x, y = entity["xy"]
    h = box_height(entity)
    return {"top": (x + BOX_W / 2, y), "right": (x + BOX_W, y + h / 2), "bottom": (x + BOX_W / 2, y + h), "left": (x, y + h / 2)}[side]


def route(a, b):
    ax, ay = a["xy"]
    bx, by = b["xy"]
    if ax + BOX_W < bx:
        return anchor(a, "right"), anchor(b, "left")
    if bx + BOX_W < ax:
        return anchor(a, "left"), anchor(b, "right")
    if ay + box_height(a) < by:
        return anchor(a, "bottom"), anchor(b, "top")
    return anchor(a, "top"), anchor(b, "bottom")


def render():
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="100%" viewBox="0 0 {W} {H}" role="img" aria-labelledby="title desc">', '<title id="title">EC101 CORE 业务事实层 ER 图</title>', '<desc id="desc">根据 ec101_mvp_sqlite.sql 生成的 CORE 层实体关系图</desc>', '<defs><filter id="shadow" x="-10%" y="-10%" width="120%" height="120%"><feDropShadow dx="2" dy="3" stdDeviation="3" flood-opacity="0.12"/></filter></defs>', '<rect width="100%" height="100%" fill="#ffffff"/>', '<text x="60" y="35" font-family="Arial, sans-serif" font-size="24" font-weight="700" fill="#102A43">EC101 CORE 业务事实层 ER 图</text>', '<text x="60" y="62" font-family="Arial, sans-serif" font-size="13" fill="#627D98">来源：mvp/ddl/ec101_mvp_sqlite.sql · 仅展示 CORE 层 14 张表 · PK 主键 / FK 外键 / UK 唯一键</text>']
    for source, target, label in edges:
        p1, p2 = route(entities[source], entities[target])
        mx, my = (p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2
        parts.append(f'<path d="M {p1[0]:.1f} {p1[1]:.1f} L {p2[0]:.1f} {p2[1]:.1f}" stroke="#9FB3C8" stroke-width="1.4" fill="none"/>')
        parts.append(f'<rect x="{mx-16:.1f}" y="{my-9:.1f}" width="32" height="18" rx="9" fill="#ffffff" stroke="#D9E2EC"/>')
        parts.append(f'<text x="{mx:.1f}" y="{my+4:.1f}" text-anchor="middle" font-family="Arial, sans-serif" font-size="10" fill="#52606D">{label}</text>')
    for name, entity in entities.items():
        x, y = entity["xy"]
        bg, accent = COLORS[entity["domain"]]
        h = box_height(entity)
        parts.append(f'<g filter="url(#shadow)"><rect x="{x}" y="{y}" width="{BOX_W}" height="{h}" rx="8" fill="#ffffff" stroke="{accent}" stroke-width="1.5"/><rect x="{x}" y="{y}" width="{BOX_W}" height="{HEADER_H}" rx="8" fill="{bg}"/><rect x="{x}" y="{y+HEADER_H-8}" width="{BOX_W}" height="8" fill="{bg}"/>')
        parts.append(f'<text x="{x+14}" y="{y+27}" font-family="Arial, sans-serif" font-size="16" font-weight="700" fill="{accent}">{escape(entity["title"])}</text><text x="{x+BOX_W-14}" y="{y+26}" text-anchor="end" font-family="Arial, sans-serif" font-size="11" fill="#829AB1">{escape(name)}</text>')
        for i, (field, typ, key, comment) in enumerate(entity["rows"]):
            yy = y + HEADER_H + i * ROW_H
            if i % 2 == 0:
                parts.append(f'<rect x="{x+1}" y="{yy}" width="{BOX_W-2}" height="{ROW_H}" fill="#F8FAFC"/>')
            parts.append(f'<text x="{x+12}" y="{yy+18}" font-family="Arial, sans-serif" font-size="11" fill="#52606D">{escape(typ)}</text>')
            parts.append(f'<text x="{x+86}" y="{yy+18}" font-family="Arial, sans-serif" font-size="11.5" fill="#102A43">{escape(field)}</text>')
            if key:
                parts.append(f'<text x="{x+225}" y="{yy+18}" font-family="Arial, sans-serif" font-size="10" font-weight="700" fill="{accent}">{escape(key)}</text>')
            parts.append(f'<text x="{x+BOX_W-10}" y="{yy+18}" text-anchor="end" font-family="Arial, sans-serif" font-size="10" fill="#829AB1">{escape(comment)}</text>')
        parts.append('</g>')
    parts.extend(['<g transform="translate(60,1910)"><rect width="420" height="34" rx="8" fill="#F8FAFC" stroke="#D9E2EC"/><circle cx="18" cy="17" r="6" fill="#167E6D"/><text x="32" y="21" font-family="Arial, sans-serif" font-size="11" fill="#52606D">主数据</text><circle cx="110" cy="17" r="6" fill="#3B67B1"/><text x="124" y="21" font-family="Arial, sans-serif" font-size="11" fill="#52606D">订单履约</text><circle cx="220" cy="17" r="6" fill="#B16A13"/><text x="234" y="21" font-family="Arial, sans-serif" font-size="11" fill="#52606D">活动权益</text><circle cx="340" cy="17" r="6" fill="#7851A9"/><text x="354" y="21" font-family="Arial, sans-serif" font-size="11" fill="#52606D">跨系统映射</text></g></svg>'])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(parts), encoding="utf-8")
    print(OUT)


if __name__ == "__main__":
    render()
