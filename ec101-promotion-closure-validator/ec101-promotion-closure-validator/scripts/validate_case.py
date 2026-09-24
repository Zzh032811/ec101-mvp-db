import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.source_readers import read_table
from scripts.field_mapping import build_complete_field_mappings
from scripts.validation_rules import eligible_order, full_reduction, payment_risk


def _order_id(value: Any) -> str:
    if pd.isna(value):
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _number(value: Any) -> float:
    converted = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return 0.0 if pd.isna(converted) else float(converted)


def _iso_timestamp(value: Any) -> str:
    return pd.Timestamp(value).strftime("%Y-%m-%d %H:%M:%S")


def _order_summaries(frame: pd.DataFrame) -> Dict[str, Dict[str, Any]]:
    source = frame.copy()
    source["订单编号"] = source["订单编号"].map(_order_id)
    source["下单时间"] = pd.to_datetime(source["下单时间"])
    summaries: Dict[str, Dict[str, Any]] = {}
    for order_id, rows in source.groupby("订单编号", sort=False):
        first = rows.iloc[0]
        summaries[order_id] = {
            "订单编号": order_id,
            "下单时间": first["下单时间"].to_pydatetime(),
            "客户编号": str(first.get("客户编号", "")),
            "客户名称": str(first.get("客户名称", "")),
            "订单状态": str(first.get("订单状态", "")),
            "支付方式": str(first.get("支付方式", "")),
            "支付状态": str(first.get("支付状态", "")),
            "订单优惠前金额": round(pd.to_numeric(rows["优惠前金额"], errors="coerce").fillna(0).sum(), 2),
            "订单优惠金额": round(pd.to_numeric(rows["优惠金额"], errors="coerce").fillna(0).sum(), 2),
        }
    return summaries


def _sales_order_ids(frame: pd.DataFrame) -> set:
    return set(frame["单据编号"].map(_order_id))


def _read_sources(source_root: Path, rule: Dict[str, Any]) -> Dict[str, pd.DataFrame]:
    return {
        "orders": read_table(source_root / rule["order_file"]),
        "sales": read_table(source_root / rule["sales_file"]),
        "activity": read_table(source_root / rule["activity_file"]),
    }


def _activity_groups(frame: pd.DataFrame) -> Iterable:
    source = frame.copy()
    source["订单号"] = source["订单号"].map(_order_id)
    source = source[source["订单号"] != ""]
    source["商品总金额"] = pd.to_numeric(source["商品总金额"], errors="coerce").fillna(0)
    source["促销优惠金额"] = pd.to_numeric(source["促销优惠金额"], errors="coerce").fillna(0)
    return source.groupby("订单号", sort=False)


def _analyze_reduction(source_root: Path, rule: Dict[str, Any]) -> Dict[str, Any]:
    sources = _read_sources(source_root, rule)
    orders = _order_summaries(sources["orders"])
    sales_ids = _sales_order_ids(sources["sales"])
    details: List[Dict[str, Any]] = []
    unmatched_activity_order_ids: List[str] = []
    non_completed_activity_order_count = 0
    activity_order_count = 0

    for order_id, rows in _activity_groups(sources["activity"]):
        activity_order_count += 1
        order = orders.get(order_id)
        if not order:
            unmatched_activity_order_ids.append(order_id)
            continue
        if not eligible_order(order, rule):
            if order["订单状态"] != rule["required_order_status"]:
                non_completed_activity_order_count += 1
            continue
        participating_amount = round(rows["商品总金额"].sum(), 2)
        actual_benefit = round(rows["促销优惠金额"].sum(), 2)
        theoretical_benefit = full_reduction(participating_amount, rule["threshold"], rule["benefit"])
        risk = payment_risk(order)
        representative_policy = next(iter(rows["享受促销政策"].dropna().astype(str)), "")
        details.append(
            {
                "订单编号": order_id,
                "下单时间": _iso_timestamp(order["下单时间"]),
                "客户编号": order["客户编号"],
                "客户名称": order["客户名称"],
                "订单状态": order["订单状态"],
                "支付方式": order["支付方式"],
                "支付状态": order["支付状态"],
                "参与商品金额": participating_amount,
                "理论优惠金额": theoretical_benefit,
                "实际优惠金额": actual_benefit,
                "权益一致": abs(theoretical_benefit - actual_benefit) < 0.01,
                "订单明细匹配": True,
                "销售明细匹配": order_id in sales_ids,
                "支付风险": risk,
                "活动政策": representative_policy,
            }
        )

    order_source_end = pd.to_datetime(sources["orders"]["下单时间"], errors="coerce").max()
    coverage_complete = order_source_end >= pd.Timestamp(rule["end_at"])
    return {
        "activity_name": rule["name"],
        "activity_type": rule["type"],
        "activity_period": f'{rule["start_at"]} 至 {rule["end_at"]}',
        "required_order_status": rule["required_order_status"],
        "eligible_order_count": len(details),
        "theoretical_benefit_total": round(sum(row["理论优惠金额"] for row in details), 2),
        "actual_benefit_total": round(sum(row["实际优惠金额"] for row in details), 2),
        "activity_detail_matched_order_count": sum(row["订单明细匹配"] for row in details),
        "sales_matched_order_count": sum(row["销售明细匹配"] for row in details),
        "benefit_matched_order_count": sum(row["权益一致"] for row in details),
        "payment_risk_count": sum(bool(row["支付风险"]) for row in details),
        "activity_order_count": activity_order_count,
        "unmatched_activity_order_ids": unmatched_activity_order_ids,
        "non_completed_activity_order_count": non_completed_activity_order_count,
        "order_source_end_at": _iso_timestamp(order_source_end),
        "conclusion": "支持" if details and coverage_complete and not unmatched_activity_order_ids and all(row["权益一致"] and row["销售明细匹配"] for row in details) else "条件支持",
        "details": details,
    }


def _analyze_gift(source_root: Path, rule: Dict[str, Any]) -> Dict[str, Any]:
    sources = _read_sources(source_root, rule)
    order_frame = sources["orders"].copy()
    order_frame["订单编号"] = order_frame["订单编号"].map(_order_id)
    orders = _order_summaries(order_frame)
    sales_ids = _sales_order_ids(sources["sales"])

    gift_mask = (
        order_frame["商品名称"].astype(str).str.contains("抱枕", na=False)
        & order_frame["商品品牌"].astype(str).str.contains("赠品", na=False)
        & order_frame["订单状态"].eq(rule["required_order_status"])
    )
    gift_quantity = (
        order_frame.loc[gift_mask]
        .assign(_qty=lambda data: pd.to_numeric(data["订货数量"], errors="coerce").fillna(0))
        .groupby("订单编号")["_qty"]
        .sum()
        .to_dict()
    )

    sprite_amount = (
        order_frame.loc[
            order_frame["商品名称"].astype(str).str.contains("雪碧", na=False)
            & ~order_frame["商品品牌"].astype(str).str.contains("赠品", na=False)
        ]
        .assign(_amount=lambda data: pd.to_numeric(data["优惠前金额"], errors="coerce").fillna(0))
        .groupby("订单编号")["_amount"]
        .sum()
        .to_dict()
    )

    details: List[Dict[str, Any]] = []
    for order_id, rows in _activity_groups(sources["activity"]):
        order = orders.get(order_id)
        if not order or not eligible_order(order, rule):
            continue
        activity_amount = round(rows["商品总金额"].sum(), 2)
        order_scope_amount = round(_number(sprite_amount.get(order_id, 0)), 2)
        actual_quantity = int(_number(gift_quantity.get(order_id, 0)))
        policies = "；".join(sorted(set(rows["享受促销政策"].dropna().astype(str))))
        marked_out_of_stock = "库存为0" in policies
        expected_quantity = rule["gift_quantity_per_order"] if activity_amount >= rule["threshold"] else 0
        risk = payment_risk(order)
        details.append(
            {
                "订单编号": order_id,
                "下单时间": _iso_timestamp(order["下单时间"]),
                "客户编号": order["客户编号"],
                "客户名称": order["客户名称"],
                "订单状态": order["订单状态"],
                "支付方式": order["支付方式"],
                "支付状态": order["支付状态"],
                "活动侧雪碧金额": activity_amount,
                "订单侧雪碧金额": order_scope_amount,
                "组合金额一致": abs(activity_amount - order_scope_amount) < 0.01,
                "理论赠品数量": expected_quantity,
                "实际赠品数量": actual_quantity,
                "库存不足标记": marked_out_of_stock,
                "赠品结果一致": actual_quantity == expected_quantity or (marked_out_of_stock and actual_quantity == 0),
                "销售明细匹配": order_id in sales_ids,
                "支付风险": risk,
                "活动政策": policies,
            }
        )

    issued = [row for row in details if row["实际赠品数量"] > 0]
    not_issued = [row for row in details if row["实际赠品数量"] == 0]
    return {
        "activity_name": rule["name"],
        "activity_type": rule["type"],
        "activity_period": f'{rule["start_at"]} 至 {rule["end_at"]}',
        "required_order_status": rule["required_order_status"],
        "eligible_order_count": len(details),
        "issued_order_count": len(issued),
        "issued_gift_quantity": sum(row["实际赠品数量"] for row in details),
        "not_issued_order_count": len(not_issued),
        "scope_amount_matched_order_count": sum(row["组合金额一致"] for row in details),
        "sales_matched_order_count": sum(row["销售明细匹配"] for row in details),
        "gift_result_matched_order_count": sum(row["赠品结果一致"] for row in details),
        "payment_risk_count": sum(bool(row["支付风险"]) for row in details),
        "conclusion": "支持" if details and all(row["赠品结果一致"] and row["销售明细匹配"] for row in details) else "条件支持",
        "details": details,
    }


def _issues(result: Dict[str, Any]) -> List[Dict[str, str]]:
    reduction = result["activities"]["满减"]
    payment_count = sum(activity["payment_risk_count"] for activity in result["activities"].values())
    return [
        {
            "ID": "Q001",
            "分类": "风险提示",
            "级别": "P1",
            "问题": f"已完成但未支付订单共 {payment_count} 单，主要为货到付款。",
            "影响": "不影响本次发放统计；当前数据不能证明线下实收。",
            "责任方": "快马/顺英",
            "状态": "待确认支付状态业务语义",
        },
        {
            "ID": "Q002",
            "分类": "Gap",
            "级别": "P0",
            "问题": "满赠赠品采购单价未提供。",
            "影响": "可核验实发 98 个抱枕，但不能换算最终费用金额。",
            "责任方": "业务/财务",
            "状态": "待补充",
        },
        {
            "ID": "Q003",
            "分类": "Gap",
            "级别": "P0",
            "问题": "当前数据未提供已完成后的退款、退货和赠品冲销终态。",
            "影响": "若已完成后仍可售后，最终费用只能条件闭环。",
            "责任方": "快马/业务",
            "状态": "待确认",
        },
        {
            "ID": "Q004",
            "分类": "Gap",
            "级别": "P0",
            "问题": "活动费用承担方未在活动或订单数据中标识。",
            "影响": "无法仅凭当前文件证明 15 元优惠或抱枕成本由太古承担。",
            "责任方": "市场/财务",
            "状态": "待确认",
        },
        {
            "ID": "Q005",
            "分类": "Gap",
            "级别": "P0",
            "问题": f"满减活动配置至2026-09-18 20:13，但订单明细数据最晚下单时间为{reduction['order_source_end_at']}。",
            "影响": "活动结束前最后约5小时的数据未覆盖，满减只能形成截至已提供数据时间的条件支持结论。",
            "责任方": "快马/顺英",
            "状态": "待补充活动结束前订单、销售及活动明细",
        },
        {
            "ID": "Q006",
            "分类": "Gap",
            "级别": "P0",
            "问题": f"满减活动明细有{len(reduction['unmatched_activity_order_ids'])}笔订单未匹配订单明细：{'、'.join(reduction['unmatched_activity_order_ids'])}。",
            "影响": "该活动订单无法判定订单状态、支付状态及是否满足发放条件。",
            "责任方": "快马/顺英",
            "状态": "待补充对应订单及销售明细",
        },
    ]


def _report(result: Dict[str, Any]) -> Dict[str, Any]:
    reduction, gift = result["activities"]["满减"], result["activities"]["满赠"]
    matrix_headers = ["平台", "经销商", "验证对象", "活动识别", "规则重算", "实际权益核对", "销售交叉验证", "履约闭环", "费用重算", "支付风险", "最终状态", "核心依据"]
    validation_headers = ["活动", "活动期间", "已完成活动单数", "理论权益", "实际权益", "权益一致", "销售匹配", "支付风险", "活动执行结论", "费用闭环说明"]
    gap_headers = ["模块", "最小数据要求", "平台现状", "是否可达", "级别", "对结论的影响", "建议动作"]
    return {
        "source_note": "数据源：快马-顺英满减订单、独立销售与活动明细，满赠订单、销售与活动明细；订单状态=已完成为发放条件。",
        "validation_subtitle": "快马-顺英｜满减按每满300减15核验已提供窗口；活动结束前最后约5小时及1笔活动订单的订单明细仍待补充。",
        "capability_rows": [
            dict(zip(matrix_headers, ["快马", "顺英", "整体", "支持", "条件支持", "条件支持", "条件支持", "未验证", "不可达", "风险提示", "条件支持", "满减与满赠可逐单核验；满减末段数据、售后与费用资料缺失"])),
            dict(zip(matrix_headers, ["快马", "顺英", "满减", "配置截图+活动明细", "每满300减15", f"{reduction['benefit_matched_order_count']}/{reduction['eligible_order_count']}一致", f"{reduction['sales_matched_order_count']}/{reduction['eligible_order_count']}", "未提供售后终态", "缺费用承担方", f"{reduction['payment_risk_count']}单", reduction["conclusion"], f"已完成47/54笔活动订单；末段数据及1笔订单明细待补"])),
            dict(zip(matrix_headers, ["快马", "顺英", "满赠", "配置截图+活动明细", "满100赠1个抱枕", f"{gift['gift_result_matched_order_count']}/{gift['eligible_order_count']}一致", f"{gift['sales_matched_order_count']}/{gift['eligible_order_count']}", "未提供售后终态", "缺抱枕成本", f"{gift['payment_risk_count']}单", gift["conclusion"], f"实发{gift['issued_gift_quantity']}个抱枕；库存不足未发{gift['not_issued_order_count']}单"])),
        ],
        "validation_summary_rows": [
            dict(zip(validation_headers, ["满减", reduction["activity_period"], f"{reduction['eligible_order_count']}单（活动明细54单）", f"{reduction['theoretical_benefit_total']}元", f"{reduction['actual_benefit_total']}元", f"{reduction['benefit_matched_order_count']}/{reduction['eligible_order_count']}", f"{reduction['sales_matched_order_count']}/{reduction['eligible_order_count']}", f"{reduction['payment_risk_count']}单", reduction["conclusion"], "末段数据、售后及费用承担方未提供"])),
            dict(zip(validation_headers, ["满赠", gift["activity_period"], f"{gift['eligible_order_count']}单", f"{gift['eligible_order_count']}个抱枕", f"{gift['issued_gift_quantity']}个", f"{gift['gift_result_matched_order_count']}/{gift['eligible_order_count']}", f"{gift['sales_matched_order_count']}/{gift['eligible_order_count']}", f"{gift['payment_risk_count']}单", gift["conclusion"], "库存不足2单；售后、成本及费用承担方未提供"])),
        ],
        "gap_rows": [
            dict(zip(gap_headers, ["满减数据覆盖", "覆盖至活动结束的订单、活动和销售明细", f"数据最晚下单时间{reduction['order_source_end_at']}，活动至2026-09-18 20:13", "条件可达", "P0", "活动结束前最后约5小时未覆盖", "补充活动结束前数据"])),
            dict(zip(gap_headers, ["满减订单关联", "活动订单可关联订单状态和支付状态", f"活动明细54单，订单明细缺{len(reduction['unmatched_activity_order_ids'])}单", "条件可达", "P0", "缺失订单不能判断发放资格", "补充订单及销售明细"])),
            dict(zip(gap_headers, ["支付", "支付方式与支付状态", f"满减已完成订单中{reduction['payment_risk_count']}单未支付", "可达", "P1", "不排除已完成订单，但需确认线下实收语义", "确认支付状态业务语义"])),
            dict(zip(gap_headers, ["履约售后与费用", "退款退货、赠品冲销、单位成本、费用承担方", "未提供", "不可达", "P0", "不能形成最终有效费用闭环", "补充售后及费用资料"])),
        ],
        "detail_sheets": [
            {"name": "满减逐单", "title": "满减逐单权益核验（已提供窗口）", "headers": ["订单编号", "下单时间", "客户编号", "客户名称", "订单状态", "支付方式", "支付状态", "参与商品金额", "理论优惠金额", "实际优惠金额", "权益一致", "订单明细匹配", "销售明细匹配", "支付风险", "活动政策"], "rows": reduction["details"]},
            {"name": "满赠逐单", "title": "满赠逐单权益核验", "headers": ["订单编号", "下单时间", "客户编号", "客户名称", "订单状态", "支付方式", "支付状态", "活动侧雪碧金额", "订单侧雪碧金额", "组合金额一致", "理论赠品数量", "实际赠品数量", "库存不足标记", "赠品结果一致", "销售明细匹配", "支付风险", "活动政策"], "rows": gift["details"]},
        ],
    }


def analyze_case(config_path: Path) -> Dict[str, Any]:
    config_path = Path(config_path).resolve()
    config = json.loads(config_path.read_text(encoding="utf-8"))
    source_root = (config_path.parent / config["source_root"]).resolve()
    result: Dict[str, Any] = {
        "platform": config["platform"],
        "dealer": config["dealer"],
        "source_root": str(source_root),
        "activities": {
            "满减": _analyze_reduction(source_root, config["activities"]["满减"]),
            "满赠": _analyze_gift(source_root, config["activities"]["满赠"]),
        },
        "overall_conclusion": "条件支持",
        "overall_basis": "满减与满赠执行结果可逐单核验；支付状态仅作风险提示。售后终态、赠品成本和费用承担方仍需补充。",
    }
    result["issues"] = _issues(result)
    result["field_mappings"] = build_complete_field_mappings(source_root, config)
    result["report"] = _report(result)
    return result


def _json_default(value: Any) -> Any:
    if hasattr(value, "item"):
        return value.item()
    raise TypeError(f"Object of type {value.__class__.__name__} is not JSON serializable")


def default_output_path(config_path: Path, dealer: str) -> Path:
    return PROJECT_ROOT / "outputs" / dealer / "run.json"


def main() -> None:
    parser = argparse.ArgumentParser(description="验证快马-顺英促销活动数据闭环")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = analyze_case(args.config)
    output_path = args.output or default_output_path(args.config, result["dealer"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8",
    )
    print(output_path)


if __name__ == "__main__":
    main()
