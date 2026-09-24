import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.field_mapping import build_complete_field_mappings


def _deduplicate(headers: Iterable[str]) -> List[str]:
    counts: Dict[str, int] = {}
    result: List[str] = []
    for index, raw in enumerate(headers, start=1):
        header = str(raw).strip() or f"未命名列{index}"
        counts[header] = counts.get(header, 0) + 1
        result.append(header if counts[header] == 1 else f"{header}_{counts[header]}")
    return result


def _read_sheet(path: Path, header_rows: List[int], sheet: Any = 0) -> pd.DataFrame:
    raw = pd.read_excel(path, sheet_name=sheet, header=None, engine="openpyxl")
    header_frames = [raw.iloc[row_number - 1] for row_number in header_rows]
    last_group = ""
    headers: List[str] = []
    for column in range(raw.shape[1]):
        values = []
        for header_frame in header_frames:
            value = header_frame.iloc[column]
            values.append("" if pd.isna(value) else str(value).strip())
        if values[0]:
            last_group = values[0]
        if len(values) == 1:
            headers.append(values[0])
        elif values[-1]:
            headers.append(f"{values[0] or last_group}-{values[-1]}")
        else:
            headers.append(values[0])
    data = raw.iloc[max(header_rows):].copy()
    data.columns = _deduplicate(headers)
    return data.dropna(how="all").reset_index(drop=True)


def _source_frame(source_root: Path, spec: Dict[str, Any]) -> pd.DataFrame:
    return _read_sheet(source_root / spec["file"], spec["header_rows"], spec.get("sheet", 0))


def _date_text(value: Any) -> str:
    return pd.Timestamp(value).strftime("%Y-%m-%d")


def _reduction_analysis(source_root: Path, rule: Dict[str, Any]) -> Dict[str, Any]:
    coverage = []
    activity_start = pd.Timestamp(rule["start_at"])
    activity_end = pd.Timestamp(rule["end_at"]) if rule.get("end_at") else None
    all_dates: List[pd.Timestamp] = []
    overlap_count = 0
    for label, spec, date_field in (
        ("销售明细（按单号）", rule["sales_source"], "开单日期"),
        ("订单明细", rule["order_source"], "销售日期"),
    ):
        frame = _source_frame(source_root, spec)
        dates = pd.to_datetime(frame[date_field], errors="coerce").dropna()
        overlap = dates.ge(activity_start) if activity_end is None else dates.between(activity_start, activity_end, inclusive="both")
        overlap_count += int(overlap.sum())
        all_dates.extend(dates.tolist())
        coverage.append({
            "来源文件": spec["file"],
            "数据类型": label,
            "起始日期": _date_text(dates.min()),
            "结束日期": _date_text(dates.max()),
            "记录数": int(len(frame)),
            "活动期重叠记录数": int(overlap.sum()),
            "结论": "无开始日后数据" if not overlap.any() else "覆盖开始日后数据",
        })
    return {
        "activity_name": rule["name"],
        "activity_type": "满减",
        "config_source": rule["config_source"],
        "config_evidence": rule["config_evidence"],
        "activity_period": f'自{pd.Timestamp(rule["start_at"]).strftime("%Y-%m-%d")}起（结束时间未提供）' if activity_end is None else f'{rule["start_at"]} 至 {rule["end_at"]}',
        "source_start_date": _date_text(min(all_dates)),
        "source_end_date": _date_text(max(all_dates)),
        "activity_period_record_count": overlap_count,
        "eligible_order_count": None,
        "theoretical_benefit_total": None,
        "actual_benefit_total": None,
        "benefit_matched_order_count": None,
        "sales_matched_order_count": None,
        "payment_risk_count": None,
        "conclusion": "未验证",
        "details": coverage,
    }


def _package_analysis(source_root: Path, rule: Dict[str, Any]) -> Dict[str, Any]:
    frame = _source_frame(source_root, rule["order_source"])
    sales_frame = _source_frame(source_root, rule["sales_source"])
    sales_order_ids = set(sales_frame["单号"].astype(str).str.strip())
    source_dates = pd.to_datetime(frame["销售日期"], errors="coerce").dropna()
    frame["销售单号"] = frame["销售单号"].astype(str).str.strip()
    frame["销售-金额"] = pd.to_numeric(frame["销售-金额"], errors="coerce").fillna(0)
    product = frame["货品名称"].fillna("").astype(str).str.strip()
    promotion = frame["促销活动"].fillna("").astype(str).str.strip()
    package_rows = frame[
        promotion.eq(rule["promotion_marker"])
        & frame["单据备注"].fillna("").astype(str).str.contains(rule["package_marker"], na=False, regex=False)
    ].copy()
    expected_amounts = {item["name"]: float(item["amount"]) for item in rule["items"]}
    expected_names = list(expected_amounts)

    details: List[Dict[str, Any]] = []
    for order_id, rows in package_rows.groupby("销售单号", sort=True):
        actual_amounts = {
            name: round(float(rows.loc[rows["货品名称"].fillna("").astype(str).str.strip().eq(name), "销售-金额"].sum()), 2)
            for name in expected_names
        }
        missing_items = [name for name, amount in actual_amounts.items() if amount == 0]
        component_match = all(actual_amounts[name] == expected_amounts[name] for name in expected_names)
        package_amount = round(float(rows["销售-金额"].sum()), 2)
        first = rows.iloc[0]
        notes = "；".join(sorted(set(rows["单据备注"].dropna().astype(str))))
        details.append({
            "销售单号": order_id,
            "销售日期": _date_text(first["销售日期"]),
            "客户名称": str(first["客户名称"]),
            "订单状态": "未提供",
            "套餐商品金额": package_amount,
            "配置套餐金额": rule["package_total"],
            "套餐组成一致": component_match and package_amount == rule["package_total"],
            "实际组成": "；".join(f"{name} {actual_amounts[name]:.2f}元" for name in expected_names if actual_amounts[name]),
            "销售明细匹配": order_id in sales_order_ids,
            "活动标记": rule["promotion_marker"],
            "单据备注": notes,
            "风险提示": "销售明细无订单状态" if component_match else f"套餐缺少或金额不符：{'、'.join(missing_items) or '金额不符'}；销售明细无订单状态",
        })

    ordinary_pillow_sales = frame[
        product.eq(rule["pillow_product_name"])
        & ~promotion.eq(rule["promotion_marker"])
    ]
    matched = [row for row in details if row["套餐组成一致"]]
    unmatched = [row for row in details if not row["套餐组成一致"]]
    return {
        "activity_name": rule["name"],
        "activity_type": "套餐",
        "config_source": rule["config_source"],
        "config_evidence": rule["config_evidence"],
        "activity_period": f"{rule['start_at']} 至 {rule['end_at']}（截图仅提供日期）",
        "required_order_status": "已完成（源数据未提供）",
        "source_period": f"{_date_text(source_dates.min())} 至 {_date_text(source_dates.max())}",
        "observed_package_order_count": len(details),
        "eligible_order_count": len(details),
        "package_matched_order_count": len(matched),
        "package_unmatched_order_count": len(unmatched),
        "ordinary_pillow_sale_count": int(len(ordinary_pillow_sales)),
        "sales_matched_order_count": sum(row["销售明细匹配"] for row in details),
        "payment_risk_count": None,
        "conclusion": "未验证",
        "details": details,
    }


def _issues(reduction: Dict[str, Any], package: Dict[str, Any]) -> List[Dict[str, str]]:
    return [
        {"ID": "Q001", "分类": "Gap", "级别": "P0", "问题": "满减业务说明活动从2026-08-26开始，当前销售数据已覆盖开始日后，但活动结束时间和正式活动配置未提供。", "影响": "无法确定完整活动期间、商品范围、资格门槛、理论优惠和实际优惠归因。", "责任方": "财经云/业务", "状态": "待补充结束时间、活动配置和执行明细"},
        {"ID": "Q002", "分类": "Gap", "级别": "P0", "问题": "订单明细未提供订单状态。", "影响": "无法按订单状态=已完成独立执行发放资格过滤。", "责任方": "财经云/勤进", "状态": "待补充订单状态或状态映射"},
        {"ID": "Q003", "分类": "风险提示", "级别": "P0", "问题": f"套餐订单明细观察到{package['observed_package_order_count']}单可口可乐专属套餐，其中{package['package_matched_order_count']}单组成与配置一致、{package['package_unmatched_order_count']}单缺少或金额不符；已与按单号销售明细{package['sales_matched_order_count']}/{package['observed_package_order_count']}匹配。", "影响": "套餐配置已提供，但订单状态、完整活动期数据和缺件原因未提供，不能确认最终有效履约或费用。", "责任方": "财经云/勤进", "状态": "待补充订单状态、全周期订单及缺件原因"},
        {"ID": "Q005", "分类": "风险提示", "级别": "P1", "问题": f"另有{package['ordinary_pillow_sale_count']}条抱枕按99元普通销售，未标记套装活动。", "影响": "已从套餐组成核验中排除；需确认是否为正常销售或活动录入异常。", "责任方": "勤进", "状态": "待复核"},
        {"ID": "Q006", "分类": "Gap", "级别": "P0", "问题": "满减活动配置、活动编号/版本和独立活动执行明细未提供；套餐配置已提供，但独立活动执行明细未提供。", "影响": "满减无法确认理论优惠或活动归因；套餐无法按订单状态确认最终有效履约。", "责任方": "财经云/业务", "状态": "待补充满减配置及两类活动执行明细"},
        {"ID": "Q007", "分类": "Gap", "级别": "P1", "问题": "未提供支付方式和支付状态。", "影响": "无法输出支付状态风险维度。", "责任方": "财经云/勤进", "状态": "待补充"},
        {"ID": "Q008", "分类": "Gap", "级别": "P0", "问题": "未提供退款退货终态、抱枕单位费用和费用承担方。", "影响": "无法形成最终费用闭环。", "责任方": "业务/财务", "状态": "待补充"},
    ]


def _report_contract(result: Dict[str, Any]) -> Dict[str, Any]:
    reduction = result["activities"]["满减"]
    package = result["activities"]["可口可乐专属套餐"]
    capability_headers = ["平台", "经销商", "验证对象", "活动识别", "规则重算", "实际权益核对", "销售交叉验证", "履约闭环", "费用重算", "支付风险", "最终状态", "核心依据"]
    capability_rows = [
        dict(zip(capability_headers, [result["platform"], result["dealer"], "整体", "部分支持", "未验证", "未验证", "仅有财经云销售事实", "未验证", "暂不支持", "未提供", result["overall_conclusion"], result["overall_basis"]])),
        dict(zip(capability_headers, [result["platform"], result["dealer"], "满减", "未提供活动配置", "未验证", "未验证", "已覆盖开始日后销售数据", "未验证", "未验证", "未提供", reduction["conclusion"], f"业务说明活动从2026-08-26开始；销售数据覆盖至{reduction['source_end_date']}，但结束时间与配置未提供"])),
        dict(zip(capability_headers, [result["platform"], result["dealer"], "可口可乐专属套餐", "支持", "条件支持", f"{package['package_matched_order_count']}/{package['observed_package_order_count']}套餐组成一致", f"{package['sales_matched_order_count']}/{package['observed_package_order_count']}销售明细匹配", "未验证", "未验证", "未提供", package["conclusion"], "配置已明确套餐期、客户限购、商品组成和金额；当前订单数据仅覆盖活动期前段，且缺订单状态、支付状态、售后及独立执行明细"])),
    ]
    validation_headers = ["活动", "活动期间", "已完成活动单数", "理论权益", "实际权益", "权益一致", "销售匹配", "支付风险", "活动执行结论", "费用闭环说明"]
    validation_rows = [
        dict(zip(validation_headers, ["满减", reduction["activity_period"], "订单状态未提供", "未验证", "未验证", "未验证", "已覆盖开始日后销售数据", "未提供", reduction["conclusion"], "需补充结束时间、活动配置、订单状态和活动执行明细"])),
        dict(zip(validation_headers, ["可口可乐专属套餐", package["activity_period"], "订单状态未提供；观察窗口内93单套餐", "配置套餐105.60元/单", f"{package['package_matched_order_count']}单105.60元；{package['package_unmatched_order_count']}单缺件或金额不符", f"{package['package_matched_order_count']}/{package['observed_package_order_count']}", f"{package['sales_matched_order_count']}/{package['observed_package_order_count']}销售明细匹配", "未提供", package["conclusion"], "套餐组成可核验；活动期仅覆盖前段，订单状态、售后终态和费用承担方待确认"])),
    ]
    gap_headers = ["模块", "最小数据要求", "平台现状", "是否可达", "级别", "对结论的影响", "建议动作"]
    gap_rows = [
        dict(zip(gap_headers, ["满减数据期间", "覆盖2026-08-26开始至活动结束的订单", f"销售数据覆盖2026-08-26起，最晚至{reduction['source_end_date']}；结束时间未提供", "条件可达", "P0", "开始日后有销售数据，但完整活动期间无法确认", "补充活动结束时间、订单状态和活动执行明细"])),
        dict(zip(gap_headers, ["订单资格", "订单状态=已完成", "订单明细未提供订单状态", "不可达", "P0", "不能执行资格过滤", "补充订单状态或状态映射"])),
        dict(zip(gap_headers, ["满减活动配置", "满减规则、范围、起止时间、活动编号和版本", "未提供", "不可达", "P0", "不能确认资格、理论优惠或活动归因", "补充满减活动配置及活动执行明细"])),
        dict(zip(gap_headers, ["套餐活动配置", "套餐期、客户范围、限购、商品组成与价格", "已提供截图；缺活动编号/版本及精确起止时分秒", "条件可达", "P1", "支持套餐组成核验，不足以确认最终有效履约", "补充活动编号、版本及独立活动执行明细"])),
        dict(zip(gap_headers, ["套餐执行", "套餐完整活动期订单及每单组成核验", f"仅覆盖2026-08-21至2026-08-25；观察到{package['observed_package_order_count']}单，{package['package_matched_order_count']}单组成一致", "条件可达", "P0", "不能覆盖套餐完整有效期或解释缺件订单", "补充至2026-09-16的订单、销售、状态及缺件原因"])),
        dict(zip(gap_headers, ["支付", "支付方式与支付状态", "未提供", "不可达", "P1", "不能输出支付风险", "补充支付字段"])),
        dict(zip(gap_headers, ["履约售后", "退款退货与赠品冲销终态", "未提供", "不可达", "P0", "最终有效费用不可确认", "补充售后终态"])),
        dict(zip(gap_headers, ["费用", "赠品单位费用与费用承担方", "未提供", "不可达", "P0", "不能形成金额闭环", "补充成本及承担主体"])),
    ]
    return {
        "source_note": "数据源：财经云-勤进文件夹中的客户、产品映射、销售明细（按单号）和订单明细（销售出库明细）；满减配置未提供，可口可乐专属套餐配置来自满赠活动配置.png。",
        "validation_subtitle": "财经云-勤进｜套餐配置可支持商品组成和金额核验；订单状态、支付数据、售后终态和独立活动执行明细仍未提供。",
        "capability_rows": capability_rows,
        "validation_summary_rows": validation_rows,
        "detail_sheets": [
            {"name": "活动配置", "title": "满减与套餐活动配置可达性", "headers": ["活动", "配置字段", "配置值", "证据来源", "证据性质", "备注"], "rows": [
                {"活动": "满减", "配置字段": "活动配置", "配置值": "未提供", "证据来源": "业务说明", "证据性质": "人工补充", "备注": "已补充开始日期2026-08-26；结束时间、配置截图或导出未提供"},
                {"活动": "可口可乐专属套餐", "配置字段": "有效期/范围/组成", "配置值": "2026-08-21至2026-09-16；全部客户；总量100、每客户1；两项雪碧商品+抱枕，套餐105.60元", "证据来源": "满赠活动配置.png", "证据性质": "页面截图", "备注": "文件名不准确，页面实际为套餐配置；未提供活动编号、版本和独立活动执行明细"},
            ]},
            {"name": "满减数据覆盖", "title": "满减订单/销售数据期间覆盖检查", "headers": ["来源文件", "数据类型", "起始日期", "结束日期", "记录数", "活动期重叠记录数", "结论"], "rows": reduction["details"]},
            {"name": "套餐逐单", "title": "可口可乐专属套餐订单与销售明细交叉核验", "headers": ["销售单号", "销售日期", "客户名称", "订单状态", "套餐商品金额", "配置套餐金额", "套餐组成一致", "实际组成", "销售明细匹配", "活动标记", "单据备注", "风险提示"], "rows": package["details"]},
        ],
        "gap_rows": gap_rows,
    }


def analyze_case(config_path: Path) -> Dict[str, Any]:
    config_path = Path(config_path).resolve()
    config = json.loads(config_path.read_text(encoding="utf-8"))
    source_root = (config_path.parent / config["source_root"]).resolve()
    reduction = _reduction_analysis(source_root, config["activities"]["满减"])
    package = _package_analysis(source_root, config["activities"]["可口可乐专属套餐"])
    result: Dict[str, Any] = {
        "platform": config["platform"],
        "dealer": config["dealer"],
        "source_root": str(source_root),
        "activities": {"满减": reduction, "可口可乐专属套餐": package},
        "overall_conclusion": "未验证",
        "overall_basis": "满减配置仍未提供。可口可乐专属套餐配置已提供，订单明细观察到93单套餐、92单组成及金额一致、1单缺抱枕行，且93/93可与按单号销售明细匹配；但套餐期仅覆盖前段，订单状态、支付状态、售后终态及独立活动执行明细缺失，不能形成最终费用闭环。",
    }
    result["issues"] = _issues(reduction, package)
    result["field_mappings"] = build_complete_field_mappings(source_root, config)
    result["report"] = _report_contract(result)
    return result


def default_output_path(dealer: str) -> Path:
    return PROJECT_ROOT / "outputs" / dealer / "run.json"


def main() -> None:
    parser = argparse.ArgumentParser(description="验证财经云-勤进促销活动数据闭环")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = analyze_case(args.config)
    output_path = args.output or default_output_path(result["dealer"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output_path)


if __name__ == "__main__":
    main()
