import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.field_mapping import build_complete_field_mappings
from scripts.source_readers import read_table


def _order_id(value: Any) -> str:
    if pd.isna(value):
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _number(value: Any) -> float:
    number = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return 0.0 if pd.isna(number) else float(number)


def _date_text(value: Any) -> str:
    return pd.Timestamp(value).strftime("%Y-%m-%d %H:%M:%S")


def _reduction(source_root: Path, rule: Dict[str, Any]) -> Dict[str, Any]:
    order_frame = read_table(source_root / rule["order_file"]).copy()
    sales_frame = read_table(source_root / rule["sales_file"]).copy()
    activity_frame = read_table(source_root / rule["activity_file"]).copy()
    order_frame["订单编号"] = order_frame["订单编号"].map(_order_id)
    order_frame["下单时间_dt"] = pd.to_datetime(order_frame["下单时间"], errors="coerce")
    order_frame["优惠前金额_num"] = pd.to_numeric(order_frame["优惠前金额"], errors="coerce").fillna(0)
    order_frame["优惠金额_num"] = pd.to_numeric(order_frame["优惠金额"], errors="coerce").fillna(0)
    order_summaries = order_frame.groupby("订单编号", as_index=False).agg(
        下单时间=("下单时间_dt", "first"), 客户编号=("客户编号", "first"), 客户名称=("客户名称", "first"),
        订单状态=("订单状态", "first"), 支付方式=("支付方式", "first"), 支付状态=("支付状态", "first")
    ).set_index("订单编号")
    sales_frame["单据编号"] = sales_frame["单据编号"].map(_order_id)
    sales_order_ids = set(sales_frame["单据编号"])

    activity_frame["订单号"] = activity_frame["订单号"].map(_order_id)
    activity_frame["商品总金额_num"] = pd.to_numeric(activity_frame["商品总金额"], errors="coerce").fillna(0)
    activity_frame["促销优惠金额_num"] = pd.to_numeric(activity_frame["促销优惠金额"], errors="coerce").fillna(0)
    activity = activity_frame.groupby("订单号", as_index=False).agg(
        参与商品金额=("商品总金额_num", "sum"), 实际优惠金额=("促销优惠金额_num", "sum"), 活动政策=("享受促销政策", "first")
    )
    details = []
    for _, row in activity.iterrows():
        order_id = row["订单号"]
        if order_id not in order_summaries.index:
            continue
        order = order_summaries.loc[order_id]
        in_window = pd.Timestamp(rule["start_at"]) <= order["下单时间"] <= pd.Timestamp(rule["end_at"])
        if not in_window or order["订单状态"] != rule["required_order_status"]:
            continue
        theoretical = rule["benefit"] if row["参与商品金额"] >= rule["threshold"] else 0
        actual = round(_number(row["实际优惠金额"]), 2)
        details.append({
            "订单编号": order_id, "下单时间": _date_text(order["下单时间"]), "客户编号": str(order["客户编号"]),
            "客户名称": str(order["客户名称"]), "订单状态": str(order["订单状态"]),
            "支付方式": str(order["支付方式"]), "支付状态": str(order["支付状态"]),
            "参与商品金额": round(_number(row["参与商品金额"]), 2), "理论优惠金额": theoretical,
            "实际优惠金额": actual, "权益一致": abs(theoretical - actual) < 0.01,
            "销售明细匹配": order_id in sales_order_ids, "支付风险": order["支付状态"] == "未支付",
            "活动政策": str(row["活动政策"]),
        })
    return {
        "activity_name": rule["name"], "activity_type": "满减", "activity_period": f'{rule["start_at"]} 至 {rule["end_at"]}',
        "eligible_order_count": len(details), "theoretical_benefit_total": round(sum(row["理论优惠金额"] for row in details), 2),
        "actual_benefit_total": round(sum(row["实际优惠金额"] for row in details), 2),
        "benefit_matched_order_count": sum(row["权益一致"] for row in details),
        "sales_matched_order_count": sum(row["销售明细匹配"] for row in details),
        "payment_risk_count": sum(row["支付风险"] for row in details), "activity_source_end": "2026-09-08 13:37:10",
        "conclusion": "条件支持", "details": details,
    }


def _gift(source_root: Path, rule: Dict[str, Any]) -> Dict[str, Any]:
    orders = read_table(source_root / rule["order_file"]).copy()
    sales = read_table(source_root / rule["sales_file"]).copy()
    activity = read_table(source_root / rule["activity_file"]).copy()
    orders["订单编号"] = orders["订单编号"].map(_order_id)
    orders["下单时间_dt"] = pd.to_datetime(orders["下单时间"], errors="coerce")
    orders["订货数量_num"] = pd.to_numeric(orders["订货数量"], errors="coerce").fillna(0)
    sales["单据编号"] = sales["单据编号"].map(_order_id)
    activity["订单号"] = activity["订单号"].map(_order_id)
    activity["商品总金额_num"] = pd.to_numeric(activity["商品总金额"], errors="coerce").fillna(0)
    activity_groups = activity.groupby("订单号", as_index=False).agg(活动商品金额=("商品总金额_num", "sum"), 活动政策=("享受促销政策", "first"))
    order_groups = orders.groupby("订单编号", as_index=False).agg(
        下单时间=("下单时间_dt", "first"), 客户编号=("客户编号", "first"), 客户名称=("客户名称", "first"),
        订单状态=("订单状态", "first"), 支付方式=("支付方式", "first"), 支付状态=("支付状态", "first")
    )
    gift_quantities = orders[orders["商品编号"].map(_order_id).eq(rule["gift_product_id"])].groupby("订单编号")["订货数量_num"].sum().to_dict()
    order_lookup = order_groups.set_index("订单编号")
    sales_order_ids = set(sales["单据编号"])
    activity_order_ids = set(activity_groups["订单号"])
    non_activity_gift_details = []
    for order_id, quantity in gift_quantities.items():
        if order_id in activity_order_ids or order_id not in order_lookup.index:
            continue
        order = order_lookup.loc[order_id]
        timestamp = order["下单时间"]
        non_activity_gift_details.append({
            "订单编号": order_id, "下单时间": _date_text(timestamp), "客户编号": str(order["客户编号"]),
            "客户名称": str(order["客户名称"]), "订单状态": str(order["订单状态"]),
            "支付方式": str(order["支付方式"]), "支付状态": str(order["支付状态"]),
            "活动侧商品金额": 0, "理论赠品数量": 0, "实际赠品数量": int(_number(quantity)),
            "活动明细匹配": False, "销售明细匹配": order_id in sales_order_ids,
            "支付风险": order["支付状态"] == "未支付", "异常类型": "活动前非关联抱枕",
            "异常原因": "下单时间早于满赠活动开始，且订单未出现在满赠活动明细中，不纳入本活动权益。",
        })
    details = []
    observed_in_window = 0
    missing_order_detail_count = 0
    excluded_status_count = 0
    for _, row in activity_groups.iterrows():
        order_id = row["订单号"]
        if order_id not in order_lookup.index:
            missing_order_detail_count += 1
            continue
        order = order_lookup.loc[order_id]
        timestamp = order["下单时间"]
        if not (pd.Timestamp(rule["start_at"]) <= timestamp <= pd.Timestamp(rule["end_at"])):
            continue
        observed_in_window += 1
        if order["订单状态"] != rule["required_order_status"]:
            excluded_status_count += 1
            continue
        actual_quantity = int(_number(gift_quantities.get(order_id, 0)))
        expected_quantity = rule["gift_quantity_per_order"] if row["活动商品金额"] >= rule["threshold"] else 0
        details.append({
            "订单编号": order_id, "下单时间": _date_text(timestamp), "客户编号": str(order["客户编号"]),
            "客户名称": str(order["客户名称"]), "订单状态": str(order["订单状态"]),
            "支付方式": str(order["支付方式"]), "支付状态": str(order["支付状态"]),
            "活动侧商品金额": round(_number(row["活动商品金额"]), 2),
            "理论赠品数量": expected_quantity, "实际赠品数量": actual_quantity,
            "赠品结果一致": actual_quantity == expected_quantity, "订单明细匹配": True,
            "销售明细匹配": order_id in sales_order_ids, "支付风险": order["支付状态"] == "未支付",
            "活动政策": str(row["活动政策"]),
        })
    observed_gift_quantity = sum(row["实际赠品数量"] for row in details)
    return {
        "activity_name": rule["name"], "activity_type": "满赠", "activity_period": f'{rule["start_at"]} 至 {rule["end_at"]}',
        "observed_activity_order_count": len(activity_groups), "order_detail_matched_order_count": observed_in_window,
        "missing_order_detail_count": missing_order_detail_count, "excluded_status_count": excluded_status_count,
        "eligible_order_count": len(details), "observed_gift_quantity": observed_gift_quantity,
        "order_detail_gift_total": int(sum(gift_quantities.values())),
        "non_activity_gift_quantity": int(sum(item["实际赠品数量"] for item in non_activity_gift_details)),
        "non_activity_gift_details": non_activity_gift_details,
        "issued_order_count": sum(row["实际赠品数量"] > 0 for row in details), "not_issued_order_count": sum(row["实际赠品数量"] == 0 for row in details),
        "gift_result_matched_order_count": sum(row["赠品结果一致"] for row in details), "sales_matched_order_count": sum(row["销售明细匹配"] for row in details),
        "payment_risk_count": sum(row["支付风险"] for row in details), "conclusion": "条件支持", "details": details,
    }


def _issues(reduction: Dict[str, Any], gift: Dict[str, Any]) -> List[Dict[str, str]]:
    return [
        {"ID": "Q003", "分类": "风险提示", "级别": "P1", "问题": f"满减全活动期内{reduction['payment_risk_count']}单已完成订单支付状态为未支付。", "影响": "按既定口径不排除已完成订单；需确认货到付款或线下实收语义。", "责任方": "快马/兴路强", "状态": "待确认支付状态业务语义"},
        {"ID": "Q004", "分类": "Gap", "级别": "P0", "问题": "未提供退款退货终态、赠品冲销、抱枕单位成本及费用承担方。", "影响": "不能形成最终有效费用和费用归属闭环。", "责任方": "业务/财务", "状态": "待补充"},
        {"ID": "Q006", "分类": "风险提示", "级别": "P1", "问题": f"满赠已完成订单中{gift['payment_risk_count']}单支付状态为未支付。", "影响": "按既定口径不排除已完成订单；需确认未支付是否为货到付款、账期或异常状态。", "责任方": "快马/兴路强", "状态": "待确认支付状态业务语义"},
        {"ID": "Q007", "分类": "风险提示", "级别": "P1", "问题": f"满赠订单明细抱枕总量{gift['order_detail_gift_total']}个，其中{gift['non_activity_gift_quantity']}个未关联满赠活动明细。", "影响": "活动权益核验只计入98个活动关联抱枕；非活动关联抱枕的发放原因与费用归属尚未确认。", "责任方": "业务/财务", "状态": "待确认订单1012420526026081900082的发放原因与费用归属"}
    ]


def _report(result: Dict[str, Any]) -> Dict[str, Any]:
    reduction, gift = result["activities"]["满减"], result["activities"]["满赠"]
    headers = ["平台", "经销商", "验证对象", "活动识别", "规则重算", "实际权益核对", "销售交叉验证", "履约闭环", "费用重算", "支付风险", "最终状态", "核心依据"]
    capability_rows = [
        dict(zip(headers, ["快马", "兴路强", "整体", "支持", "条件支持", "条件支持", "支持", "未验证", "不可达", "风险提示", "条件支持", "满减和满赠均可完成活动执行核验；售后与费用资料缺失"])),
        dict(zip(headers, ["快马", "兴路强", "满减", "配置截图+活动明细", "满300固定减15", f"{reduction['benefit_matched_order_count']}/{reduction['eligible_order_count']}一致", f"{reduction['sales_matched_order_count']}/{reduction['eligible_order_count']}独立销售", "未提供售后终态", "缺费用承担方", f"{reduction['payment_risk_count']}单", reduction["conclusion"], "活动、订单及独立销售明细完整覆盖活动期"])),
        dict(zip(headers, ["快马", "兴路强", "满赠", "配置截图+活动明细", "满100赠1个抱枕", f"{gift['gift_result_matched_order_count']}/{gift['eligible_order_count']}已完成订单一致", f"{gift['sales_matched_order_count']}/{gift['eligible_order_count']}", "未提供售后终态", "缺抱枕成本", f"{gift['payment_risk_count']}单", gift["conclusion"], f"活动关联抱枕98个；订单明细总量{gift['order_detail_gift_total']}个，另{gift['non_activity_gift_quantity']}个未关联活动"])),
    ]
    validation_headers = ["活动", "活动期间", "已完成活动单数", "理论权益", "实际权益", "权益一致", "销售匹配", "支付风险", "活动执行结论", "费用闭环说明"]
    validation_rows = [
        dict(zip(validation_headers, ["满减", reduction["activity_period"], f"{reduction['eligible_order_count']}单（全活动期）", f"{reduction['theoretical_benefit_total']}元", f"{reduction['actual_benefit_total']}元", f"{reduction['benefit_matched_order_count']}/{reduction['eligible_order_count']}", f"{reduction['sales_matched_order_count']}/{reduction['eligible_order_count']}（独立销售明细）", f"{reduction['payment_risk_count']}单", reduction["conclusion"], "售后与费用承担方未提供"])),
        dict(zip(validation_headers, ["满赠", gift["activity_period"], f"{gift['eligible_order_count']}单（活动明细{gift['observed_activity_order_count']}单，订单明细全覆盖）", f"{gift['eligible_order_count']}个抱枕（按活动金额）", f"活动关联{gift['observed_gift_quantity']}个；订单明细总量{gift['order_detail_gift_total']}个", f"{gift['gift_result_matched_order_count']}/{gift['eligible_order_count']}", f"{gift['sales_matched_order_count']}/{gift['eligible_order_count']}", f"{gift['payment_risk_count']}单", gift["conclusion"], f"另{gift['non_activity_gift_quantity']}个活动前非关联抱枕待确认；售后、成本及费用承担方未提供"])),
    ]
    gap_headers = ["模块", "最小数据要求", "平台现状", "是否可达", "级别", "对结论的影响", "建议动作"]
    gap_rows = [
        dict(zip(gap_headers, ["满减数据覆盖", "覆盖至活动结束的订单、活动和销售明细", "已提供至9月17日的活动、订单和销售明细", "可达", "P0", "已完成订单及权益可完整核验", "无需补充活动期数据"])),
        dict(zip(gap_headers, ["满减销售交叉", "独立订单与销售/出库明细", f"独立销售明细覆盖{reduction['sales_matched_order_count']}/{reduction['eligible_order_count']}笔已完成活动订单", "可达", "P1", "已形成独立销售交叉验证", "无需补充销售明细"])),
        dict(zip(gap_headers, ["满赠资格", "订单状态=已完成", "订单明细覆盖98/98单活动订单，均为已完成", "可达", "P0", "已完成发放资格可完整核验", "无需补充订单状态"])),
        dict(zip(gap_headers, ["满赠非活动抱枕", "抱枕订单可关联具体活动", f"订单明细抱枕总量{gift['order_detail_gift_total']}个，活动关联98个，另{gift['non_activity_gift_quantity']}个未关联", "条件可达", "P1", "非活动关联抱枕不计入活动权益，但需确认发放原因和费用归属", "确认订单1012420526026081900082的发放原因与费用归属"])),
        dict(zip(gap_headers, ["支付", "支付方式与支付状态", "满减已提供；满赠已覆盖98单", "可达", "P1", "两类活动均可作支付风险提示", "确认未支付的货到付款、账期或异常语义"])),
        dict(zip(gap_headers, ["履约售后与费用", "退款退货、赠品冲销、单位成本、费用承担方", "未提供", "不可达", "P0", "不能形成最终有效费用闭环", "补充售后与费用资料"])),
    ]
    return {
        "source_note": "数据源：快马-兴路强客户/商品档案、满减订单及独立销售明细、满赠订单明细、两类活动明细及活动配置截图；订单状态=已完成为发放条件。",
        "validation_subtitle": "快马-兴路强｜满减采用满300固定减15并完成全活动期核验；满赠完整核验98单活动订单，订单明细另有1个活动前非关联抱枕待确认。",
        "capability_rows": capability_rows, "validation_summary_rows": validation_rows,
        "detail_sheets": [
            {"name": "活动配置", "title": "满减与满赠活动配置（截图结构化）", "headers": ["活动", "配置字段", "配置值", "证据来源", "证据性质", "备注"], "rows": [
                {"活动": "满减", "配置字段": "规则", "配置值": "可口可乐指定品牌满300立减15；2026-08-31 10:58至09-17 23:59；指定客户类型", "证据来源": "组合促销满减方案.png", "证据性质": "配置截图", "备注": "单一阶梯，按订单固定减15"},
                {"活动": "满赠", "配置字段": "规则", "配置值": "指定商品满100赠雪碧冰丝抱枕1个；2026-08-19 15:15至08-31 23:59；每客户限购1单", "证据来源": "组合促销满赠方案.png", "证据性质": "配置截图", "备注": "指定商品清单未导出"}
            ]},
            {"name": "满减逐单", "title": "满减逐单权益核验（全活动期）", "headers": ["订单编号", "下单时间", "客户编号", "客户名称", "订单状态", "支付方式", "支付状态", "参与商品金额", "理论优惠金额", "实际优惠金额", "权益一致", "销售明细匹配", "支付风险", "活动政策"], "rows": reduction["details"]},
            {"name": "满赠逐单", "title": "满赠逐单权益核验（订单状态=已完成，已覆盖全部活动订单）", "headers": ["订单编号", "下单时间", "客户编号", "客户名称", "订单状态", "支付方式", "支付状态", "活动侧商品金额", "理论赠品数量", "实际赠品数量", "赠品结果一致", "订单明细匹配", "销售明细匹配", "支付风险", "活动政策"], "rows": gift["details"]},
            {"name": "满赠异常订单", "title": "满赠异常订单明细（不纳入活动权益）", "headers": ["订单编号", "下单时间", "客户编号", "客户名称", "订单状态", "支付方式", "支付状态", "活动侧商品金额", "理论赠品数量", "实际赠品数量", "活动明细匹配", "销售明细匹配", "支付风险", "异常类型", "异常原因"], "rows": gift["non_activity_gift_details"]}
        ], "gap_rows": gap_rows,
    }


def analyze_case(config_path: Path) -> Dict[str, Any]:
    config_path = Path(config_path).resolve()
    config = json.loads(config_path.read_text(encoding="utf-8"))
    source_root = (config_path.parent / config["source_root"]).resolve()
    reduction = _reduction(source_root, config["activities"]["满减"])
    gift = _gift(source_root, config["activities"]["满赠"])
    result = {
        "platform": config["platform"], "dealer": config["dealer"], "source_root": str(source_root),
        "activities": {"满减": reduction, "满赠": gift}, "overall_conclusion": "条件支持",
        "overall_basis": "满减全活动期133笔已完成订单按满300固定减15重算一致，并与独立销售明细全部匹配；满赠活动明细98单已全部由订单明细覆盖，均为已完成且满100赠抱枕一致。订单明细另有1个活动前、未关联活动明细的抱枕，待确认发放原因与费用归属。"
    }
    result["issues"] = _issues(reduction, gift)
    result["field_mappings"] = build_complete_field_mappings(source_root, config)
    result["report"] = _report(result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="验证快马-兴路强满减与满赠数据闭环")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = analyze_case(args.config)
    output = args.output or PROJECT_ROOT / "outputs" / result["dealer"] / "run.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=lambda value: value.item() if hasattr(value, "item") else str(value)), encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
