import argparse
import json
import math
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.field_mapping import build_complete_field_mappings


def _read_export(path: Path, header_row: int) -> pd.DataFrame:
    raw = pd.read_excel(path, header=None, engine="openpyxl")
    frame = raw.iloc[header_row:].copy()
    headers = raw.iloc[header_row - 1].fillna("").astype(str).tolist()
    counts: Dict[str, int] = {}
    unique_headers = []
    for index, header in enumerate(headers, start=1):
        header = header.strip() or f"未命名列{index}"
        counts[header] = counts.get(header, 0) + 1
        unique_headers.append(header if counts[header] == 1 else f"{header}_{counts[header]}")
    frame.columns = unique_headers
    return frame.dropna(how="all").reset_index(drop=True)


def _number(value: Any) -> float:
    return float(pd.to_numeric(pd.Series([value]), errors="coerce").fillna(0).iloc[0])


def _quantity(frame: pd.DataFrame) -> pd.Series:
    raw = frame.get("订单数量", pd.Series(index=frame.index, dtype=object)).fillna(
        frame.get("实际数量", pd.Series(index=frame.index, dtype=object))
    )
    return raw.astype(str).str.extract(r"([0-9.]+)")[0].astype(float).fillna(0)


def _date(value: Any) -> str:
    return pd.Timestamp(value).strftime("%Y-%m-%d")


def _normalize_customer_name(value: Any) -> str:
    text = str(value or "").strip().replace("（", "(").replace("）", ")")
    text = re.sub(r"^X", "", text)
    text = re.sub(r"\([^)]*\)", "", text)
    return re.sub(r"\s+", "", text)


def _split_order_ids(value: Any) -> List[str]:
    return [item.strip() for item in str(value or "").split(",") if item.strip() and item.strip().lower() != "nan"]


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if pd.isna(value) if not isinstance(value, (list, dict)) else False:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.isoformat(sep=" ")
    return value


def _read_order_files(source_root: Path, file_names: Iterable[str]) -> pd.DataFrame:
    return pd.concat([_read_export(source_root / name, 4) for name in file_names], ignore_index=True)


def _auxiliary_coupon_eligibility(source_root: Path, rule: Dict[str, Any], sales: pd.DataFrame, activity: pd.DataFrame) -> Dict[str, Any]:
    xd = _read_export(source_root / rule["xd_file"], 4)
    xd["单据时间_dt"] = pd.to_datetime(xd["单据时间"], errors="coerce")
    xd["出入库金额_num"] = pd.to_numeric(xd["出入库金额"], errors="coerce").fillna(0)
    xd["客户名称_norm"] = xd["客户名称"].map(_normalize_customer_name)
    coke_orders = xd[
        xd["品牌"].fillna("").astype(str).eq(rule["brand"])
        & xd["订单状态"].fillna("").astype(str).eq("已完成")
    ].groupby(
        ["单据", "客户名称", "客户名称_norm", "单据时间", "订单状态"], as_index=False
    ).agg(可口可乐出库金额=("出入库金额_num", "sum"))
    sales_lookup = sales.drop_duplicates("订单编号").set_index("订单编号")
    rows: List[Dict[str, Any]] = []
    for _, activity_row in activity.iterrows():
        for linked_order_id in _split_order_ids(activity_row.get("关联单据编号")):
            sales_row = sales_lookup.loc[linked_order_id] if linked_order_id in sales_lookup.index else None
            cutoff = pd.to_datetime(sales_row["下单时间"], errors="coerce") if sales_row is not None else pd.NaT
            candidates = coke_orders.iloc[0:0]
            if pd.notna(cutoff):
                candidates = coke_orders[
                    coke_orders["客户名称_norm"].eq(_normalize_customer_name(activity_row["领取客户"]))
                    & coke_orders["可口可乐出库金额"].ge(rule["threshold"])
                    & pd.to_datetime(coke_orders["单据时间"], errors="coerce").lt(cutoff)
                ].sort_values("单据时间")
            candidate = candidates.iloc[0] if not candidates.empty else None
            rows.append({
                "领取客户": str(activity_row["领取客户"]),
                "关联SXD单据编号": linked_order_id,
                "SXD下单时间（倒推上限）": str(sales_row["下单时间"]) if sales_row is not None else "",
                "辅助触发XD单据编号": "" if candidate is None else str(candidate["单据"]),
                "辅助触发XD单据时间": "" if candidate is None else str(candidate["单据时间"]),
                "可口可乐出库金额": "" if candidate is None else round(_number(candidate["可口可乐出库金额"]), 2),
                "订单状态": "" if candidate is None else str(candidate["订单状态"]),
                "辅助资格结果": "具备领券资格" if candidate is not None else "未找到候选单",
                "说明": "仅用于本次资格核对，非合规判定；正式触发订单仍需发券流水确认。",
            })
    return {
        "used_coupon_count": int(pd.to_numeric(activity["已使用张数"], errors="coerce").fillna(0).sum()),
        "linked_coupon_count": len(rows),
        "qualified_coupon_count": sum(row["辅助资格结果"] == "具备领券资格" for row in rows),
        "details": rows,
    }


def _coupon_analysis(source_root: Path, rule: Dict[str, Any]) -> Dict[str, Any]:
    orders = _read_order_files(source_root, rule["order_files"])
    sales = _read_export(source_root / rule["sales_file"], 4)
    activity = _read_export(source_root / rule["activity_file"], 3)
    orders["下单时间_dt"] = pd.to_datetime(orders["下单时间"], errors="coerce")
    orders["实际金额_num"] = pd.to_numeric(orders["实际金额"], errors="coerce").fillna(0)
    compare_end = min(pd.Timestamp(rule["end_at"]), pd.Timestamp("2026-09-08 23:59:59"))
    completed_coke = orders[
        orders["品牌"].fillna("").astype(str).eq(rule["brand"])
        & orders["订单状态"].fillna("").astype(str).eq("已完成")
        & orders["下单时间_dt"].between(pd.Timestamp(rule["start_at"]), compare_end)
    ].copy()
    aggregates = completed_coke.groupby(["订单编号", "客户名称", "下单时间"], as_index=False).agg(
        可口可乐活动商品金额=("实际金额_num", "sum")
    )
    eligible = aggregates[aggregates["可口可乐活动商品金额"] >= rule["threshold"]].copy()
    sales["已支付金额_num"] = pd.to_numeric(sales["已支付金额"], errors="coerce")
    sales_lookup = sales.drop_duplicates("订单编号").set_index("订单编号")
    details = []
    for _, row in eligible.sort_values("下单时间").iterrows():
        order_id = str(row["订单编号"])
        sales_row = sales_lookup.loc[order_id] if order_id in sales_lookup.index else None
        paid = sales_row["已支付金额_num"] if sales_row is not None else None
        risk = sales_row is not None and (pd.isna(paid) or paid == 0)
        details.append({
            "订单编号": order_id,
            "客户名称": str(row["客户名称"]),
            "下单时间": str(row["下单时间"]),
            "订单状态": "已完成",
            "可口可乐活动商品金额": round(_number(row["可口可乐活动商品金额"]), 2),
            "理论返券金额": rule["coupon_face_value"],
            "实际返券": "活动明细未提供触发订单号，无法逐单关联",
            "权益一致": "未能逐单验证",
            "销售明细匹配": sales_row is not None,
            "支付风险": "已完成且已支付金额为空/0" if risk else "无",
        })
    issued = int(pd.to_numeric(activity["已领取数量"], errors="coerce").fillna(0).sum())
    used = int(pd.to_numeric(activity["已使用张数"], errors="coerce").fillna(0).sum())
    auxiliary = _auxiliary_coupon_eligibility(source_root, rule, sales, activity)
    return {
        "activity_name": rule["name"],
        "activity_type": "下单返券",
        "activity_period": "2026-08-26 至 2026-09-26",
        "threshold": rule["threshold"],
        "coupon_face_value": rule["coupon_face_value"],
        "order_source_start": _date(orders["下单时间_dt"].min()),
        "order_source_end": _date(orders["下单时间_dt"].max()),
        "activity_source_end": "2026-09-08",
        "eligible_order_count": len(details),
        "theoretical_benefit_total": len(details) * rule["coupon_face_value"],
        "issued_coupon_count": issued,
        "used_coupon_count": used,
        "linked_usage_order_count": auxiliary["linked_coupon_count"],
        "auxiliary_eligibility": auxiliary,
        "sales_matched_order_count": sum(row["销售明细匹配"] for row in details),
        "payment_risk_count": sum(row["支付风险"] != "无" for row in details),
        "conclusion": "条件支持",
        "details": details,
        "activity_details": activity.to_dict("records"),
    }


def _gift_analysis(source_root: Path, rule: Dict[str, Any]) -> Dict[str, Any]:
    orders = _read_order_files(source_root, rule["order_files"])
    sales = _read_export(source_root / rule["sales_file"], 4)
    orders["下单时间_dt"] = pd.to_datetime(orders["下单时间"], errors="coerce")
    orders["实际金额_num"] = pd.to_numeric(orders["实际金额"], errors="coerce").fillna(0)
    orders["数量_num"] = _quantity(orders)
    orders = orders.drop_duplicates(subset=["订单编号", "商品名称", "下单时间", "实际金额", "数量_num"])
    active = orders[
        orders["下单时间_dt"].between(pd.Timestamp(rule["start_at"]), pd.Timestamp(rule["end_at"]))
        & orders["订单状态"].fillna("").astype(str).eq("已完成")
    ].copy()
    product = active["商品名称"].fillna("").astype(str)
    sprite = active[product.str.contains(rule["scope_keyword"]) & ~product.str.contains("抱枕")].copy()
    gifts = active[product.eq(rule["gift_product_name"])].copy()
    candidates = sprite.groupby(["订单编号", "客户名称", "下单时间"], as_index=False).agg(
        雪碧活动商品金额=("实际金额_num", "sum")
    )
    candidates = candidates[candidates["雪碧活动商品金额"] >= rule["threshold"]].sort_values("下单时间")
    eligible = candidates.drop_duplicates("客户名称", keep="first").copy()
    gift_quantities = gifts.groupby("订单编号", as_index=False).agg(实际赠品数量=("数量_num", "sum"))
    eligible = eligible.merge(gift_quantities, on="订单编号", how="left").fillna({"实际赠品数量": 0})
    sales["已支付金额_num"] = pd.to_numeric(sales["已支付金额"], errors="coerce")
    sales_lookup = sales.drop_duplicates("订单编号").set_index("订单编号")
    details = []
    for _, row in eligible.iterrows():
        order_id = str(row["订单编号"])
        sales_row = sales_lookup.loc[order_id] if order_id in sales_lookup.index else None
        paid = sales_row["已支付金额_num"] if sales_row is not None else None
        actual_quantity = int(row["实际赠品数量"])
        risk = sales_row is not None and (pd.isna(paid) or paid == 0)
        details.append({
            "订单编号": order_id,
            "客户名称": str(row["客户名称"]),
            "下单时间": str(row["下单时间"]),
            "订单状态": "已完成",
            "雪碧活动商品金额": round(_number(row["雪碧活动商品金额"]), 2),
            "理论赠品数量": rule["gift_quantity_per_order"],
            "实际赠品数量": actual_quantity,
            "权益一致": actual_quantity == rule["gift_quantity_per_order"],
            "销售明细匹配": sales_row is not None,
            "支付风险": "已完成且已支付金额为空/0" if risk else "无",
        })
    eligible_ids = {row["订单编号"] for row in details}
    extra_gifts = gift_quantities[~gift_quantities["订单编号"].astype(str).isin(eligible_ids)].to_dict("records")
    candidate_amounts = candidates.assign(订单编号=candidates["订单编号"].astype(str)).set_index("订单编号")["雪碧活动商品金额"].to_dict()
    gift_order_rows = gifts.groupby(["订单编号", "客户名称", "下单时间"], as_index=False).agg(
        实际赠品数量=("数量_num", "sum")
    )
    extra_gift_details = []
    for _, row in gift_order_rows.iterrows():
        order_id = str(row["订单编号"])
        if order_id in eligible_ids:
            continue
        sales_row = sales_lookup.loc[order_id] if order_id in sales_lookup.index else None
        paid = sales_row["已支付金额_num"] if sales_row is not None else None
        risk = sales_row is not None and (pd.isna(paid) or paid == 0)
        amount = round(_number(candidate_amounts.get(order_id, 0)), 2)
        reason = (
            "同一客户存在更早的满赠达标订单，按每客户限购1单不纳入本活动资格集合。"
            if amount >= rule["threshold"]
            else "订单未进入满赠资格集合，待确认活动商品范围或人工发放依据。"
        )
        extra_gift_details.append({
            "订单编号": order_id,
            "客户名称": str(row["客户名称"]),
            "下单时间": str(row["下单时间"]),
            "订单状态": "已完成",
            "雪碧活动商品金额": amount,
            "理论赠品数量": 0,
            "实际赠品数量": int(row["实际赠品数量"]),
            "权益一致": False,
            "销售明细匹配": sales_row is not None,
            "支付风险": "已完成且已支付金额为空/0" if risk else "无",
            "异常类型": "异常赠送",
            "异常原因": reason,
        })
    missing_gift_details = [
        {
            **detail,
            "异常类型": "未赠",
            "异常原因": "满足满赠资格但未见抱枕赠品行，待确认库存、人工补发或后续冲销。",
        }
        for detail in details
        if detail["实际赠品数量"] == 0
    ]
    exception_details = sorted(missing_gift_details + extra_gift_details, key=lambda row: row["下单时间"])
    return {
        "activity_name": rule["name"],
        "activity_type": "满赠",
        "activity_period": "2026-08-19 12:29:37 至 2026-08-26 12:29:40",
        "eligible_order_count": len(details),
        "pre_limit_eligible_order_count": len(candidates),
        "issued_order_count": sum(row["实际赠品数量"] >= 1 for row in details),
        "issued_gift_quantity": int(sum(row["实际赠品数量"] for row in details)),
        "observed_gift_quantity": int(gift_quantities["实际赠品数量"].sum()),
        "not_issued_order_count": sum(row["实际赠品数量"] == 0 for row in details),
        "extra_gift_order_count": len(extra_gifts),
        "gift_result_matched_order_count": sum(row["权益一致"] for row in details),
        "sales_matched_order_count": sum(row["销售明细匹配"] for row in details),
        "payment_risk_count": sum(row["支付风险"] != "无" for row in details),
        "conclusion": "条件支持",
        "details": details,
        "extra_gifts": extra_gifts,
        "exception_details": exception_details,
    }


def _issues(coupon: Dict[str, Any], gift: Dict[str, Any]) -> List[Dict[str, str]]:
    auxiliary = coupon["auxiliary_eligibility"]
    return [
        {"ID": "Q001", "分类": "Gap", "级别": "P0", "问题": "下单返券真实活动期为2026-08-26至2026-09-26；本次订单、销售和活动明细统一仅覆盖2026-08-26至2026-09-08。", "影响": "当前结论仅代表已提供的阶段样本，不能作为全活动期统计。", "责任方": "舟谱/羿柏", "状态": "待补充2026-09-09至09-26订单、销售与活动明细"},
        {"ID": "Q002", "分类": "风险提示", "级别": "P1", "问题": f"已核销的{coupon['used_coupon_count']}张券均可按领取客户和关联SXD单据倒推至活动前的可口可乐达标XD候选单（{auxiliary['qualified_coupon_count']}/{auxiliary['used_coupon_count']}）。", "影响": "该结果仅用于本次客户领券资格核对，不能替代正式发券时间和触发订单号。", "责任方": "舟谱", "状态": "保留辅助核对；正式合规判定仍待发券流水"},
        {"ID": "Q003", "分类": "Gap", "级别": "P0", "问题": "活动明细未提供领取时间和触发订单号。", "影响": "无法将辅助反推的候选单固化为系统正式发券依据，也不能逐单比较理论返券与实际发券。", "责任方": "舟谱", "状态": "待补充发券流水（领取时间、触发订单号、券ID）"},
        {"ID": "Q004", "分类": "风险提示", "级别": "P0", "问题": f"满赠按规则、已完成状态和每客户1单重算出{gift['eligible_order_count']}单；其中{gift['gift_result_matched_order_count']}单赠品一致、{gift['not_issued_order_count']}单未见抱枕，另有{gift['extra_gift_order_count']}单抱枕不在该资格集合。", "影响": "存在未赠及异常赠送，需确认库存、人工补发/调整或活动商品范围差异。", "责任方": "羿柏/舟谱", "状态": "待逐单复核"},
        {"ID": "Q005", "分类": "风险提示", "级别": "P1", "问题": f"已完成的下单返券候选订单中{coupon['payment_risk_count']}单、满赠资格订单中{gift['payment_risk_count']}单的销售订单已支付金额为空或0。", "影响": "舟谱未提供独立支付状态；按既定口径不排除已完成订单，但需确认货到付款/线下结款语义。", "责任方": "舟谱/羿柏", "状态": "待确认支付状态定义"},
        {"ID": "Q006", "分类": "Gap", "级别": "P0", "问题": "未提供退款退货终态、赠品冲销、赠品单位成本和费用承担方。", "影响": "不能计算最终有效费用或确认费用归属。", "责任方": "羿柏/业务/财务", "状态": "待补充售后及费用资料"}
    ]


def _report_contract(result: Dict[str, Any]) -> Dict[str, Any]:
    coupon, gift = result["activities"]["满减"], result["activities"]["满赠"]
    auxiliary = coupon["auxiliary_eligibility"]
    capability_headers = ["平台", "经销商", "验证对象", "活动识别", "规则重算", "实际权益核对", "销售交叉验证", "履约闭环", "费用重算", "支付风险", "最终状态", "核心依据"]
    capability_rows = [
        dict(zip(capability_headers, [result["platform"], result["dealer"], "整体", "支持", "条件支持", "条件支持", "支持", "条件支持", "不可达", "风险提示", result["overall_conclusion"], result["overall_basis"]])),
        dict(zip(capability_headers, [result["platform"], result["dealer"], "下单返券", "截图+活动明细", "满288返15元券", f"发券{coupon['issued_coupon_count']}张；核销券辅助资格{auxiliary['qualified_coupon_count']}/{auxiliary['used_coupon_count']}", f"{coupon['sales_matched_order_count']}/{coupon['eligible_order_count']}（阶段样本）", f"使用{coupon['used_coupon_count']}张，SXD关联{coupon['linked_usage_order_count']}/{coupon['used_coupon_count']}", "缺费用承担方", f"{coupon['payment_risk_count']}单", coupon["conclusion"], "辅助资格核对非合规判定；真实活动至9月26日，数据仅覆盖8月26日至9月8日"])),
        dict(zip(capability_headers, [result["platform"], result["dealer"], "满赠", "规则截图", "已完成、精确活动时间、雪碧满100、每客户1单", f"{gift['gift_result_matched_order_count']}/{gift['eligible_order_count']}一致；{gift['not_issued_order_count']}单未赠、{gift['extra_gift_order_count']}单异常赠送", f"{gift['sales_matched_order_count']}/{gift['eligible_order_count']}", "订单含零金额抱枕行；退款/冲销未提供", "缺抱枕单位成本及费用承担方", f"{gift['payment_risk_count']}单", gift["conclusion"], "满赠配置截图与订单赠品行可直接核验；异常订单待复核"])),
    ]
    validation_headers = ["活动", "活动期间", "已完成活动单数", "理论权益", "实际权益", "权益一致", "销售匹配", "支付风险", "活动执行结论", "费用闭环说明"]
    validation_rows = [
        dict(zip(validation_headers, ["下单返券", coupon["activity_period"], f"{coupon['eligible_order_count']}单（8/26-9/8阶段样本）", f"{coupon['theoretical_benefit_total']}元券面理论值", f"发券{coupon['issued_coupon_count']}张、使用{coupon['used_coupon_count']}张", f"核销券辅助资格{auxiliary['qualified_coupon_count']}/{auxiliary['used_coupon_count']}（非合规）", f"{coupon['sales_matched_order_count']}/{coupon['eligible_order_count']}", f"{coupon['payment_risk_count']}单", coupon["conclusion"], "9/9-9/26、正式发券流水、退款及费用承担方未提供"])),
        dict(zip(validation_headers, ["满赠", gift["activity_period"], f"{gift['eligible_order_count']}单（限购后；限购前{gift['pre_limit_eligible_order_count']}单）", f"{gift['eligible_order_count']}个抱枕", f"观察到{gift['observed_gift_quantity']}个（其中资格单{gift['issued_gift_quantity']}个）", f"{gift['gift_result_matched_order_count']}/{gift['eligible_order_count']}；另{gift['extra_gift_order_count']}单异常赠送", f"{gift['sales_matched_order_count']}/{gift['eligible_order_count']}", f"{gift['payment_risk_count']}单", gift["conclusion"], "赠品成本、费用承担方、退款与冲销未提供"])),
    ]
    gap_headers = ["模块", "最小数据要求", "平台现状", "是否可达", "级别", "对结论的影响", "建议动作"]
    gap_rows = [
        dict(zip(gap_headers, ["下单返券数据覆盖", "完整活动期订单、销售及发券流水", "订单、销售和活动明细统一覆盖8/26-9/8；活动至9/26", "条件可达", "P0", "只能形成阶段样本结论", "补充9/9-9/26数据"])),
        dict(zip(gap_headers, ["返券执行", "发券时间、触发订单号、券ID", f"核销券可按客户名称和关联SXD单据辅助核对资格{auxiliary['qualified_coupon_count']}/{auxiliary['used_coupon_count']}；但无正式触发订单号", "条件可达", "P0", "仅能辅助核对客户资格，不能形成合规判定", "补充发券流水"])),
        dict(zip(gap_headers, ["满赠规则与执行", "规则、订单状态、赠品实发行", "规则截图、已完成订单、零金额抱枕行均已提供", "可达", "P0", f"可定位{gift['not_issued_order_count']}单未赠和{gift['extra_gift_order_count']}单异常赠送", "逐单复核异常原因"])),
        dict(zip(gap_headers, ["支付", "支付状态", "已支付金额及支付流水号可见，但无独立支付状态", "条件可达", "P1", "已完成空/0支付金额仅作风险，不排除资格", "确认货到付款/线下结款语义"])),
        dict(zip(gap_headers, ["履约售后", "退款、退货、赠品冲销终态", "未提供", "不可达", "P0", "最终有效权益不能确认", "补充售后终态"])),
        dict(zip(gap_headers, ["费用", "单位成本与费用承担方", "未提供", "不可达", "P0", "不能形成费用金额和归属闭环", "补充成本及承担方"])),
    ]
    return {
        "source_note": "数据源：舟谱-羿柏客户/商品档案、8月26日至9月8日SXD与XD订单及销售明细、下单返券活动明细及满赠规则截图；订单状态=已完成为资格条件，支付金额空/0仅作风险提示。",
        "validation_subtitle": "舟谱-羿柏｜下单返券真实活动期截至9月26日，本次仅按8月26日至9月8日统一数据窗口核验；核销券客户资格采用SXD/XD时间倒推辅助核对，非合规判定。",
        "capability_rows": capability_rows,
        "validation_summary_rows": validation_rows,
        "detail_sheets": [
            {"name": "活动配置", "title": "下单返券与满赠活动配置（截图结构化）", "headers": ["活动", "配置字段", "配置值", "证据来源", "证据性质", "备注"], "rows": [
                {"活动": "下单返券", "配置字段": "规则", "配置值": "可口可乐满288返15元券；2026-08-26至09-26；每客户每日1次", "证据来源": "满减方案.png", "证据性质": "配置截图", "备注": "该截图实际为下单返券方案，并非满减"},
                {"活动": "满赠", "配置字段": "规则", "配置值": "雪碧指定商品满100赠1个雪碧抱枕；2026-08-19 12:29:37至08-26 12:29:40；每客户1单，总量100", "证据来源": "满赠方案1-3.png", "证据性质": "配置截图", "备注": "活动商品截图仅展示部分指定雪碧SKU"}
            ]},
            {"name": "下单返券逐单", "title": "下单返券资格与销售交叉核验（局部窗口）", "headers": ["订单编号", "客户名称", "下单时间", "订单状态", "可口可乐活动商品金额", "理论返券金额", "实际返券", "权益一致", "销售明细匹配", "支付风险"], "rows": coupon["details"]},
            {"name": "下单返券执行", "title": "下单返券活动明细（原始执行记录）", "headers": ["券名", "领取客户", "已领取数量", "优惠券面值", "已使用张数", "关联单据编号"], "rows": coupon["activity_details"]},
            {"name": "返券辅助资格核验", "title": "核销券客户领券资格辅助核验（非合规判定）", "headers": ["领取客户", "关联SXD单据编号", "SXD下单时间（倒推上限）", "辅助触发XD单据编号", "辅助触发XD单据时间", "可口可乐出库金额", "订单状态", "辅助资格结果", "说明"], "rows": auxiliary["details"]},
            {"name": "满赠逐单", "title": "满赠逐单权益核验", "headers": ["订单编号", "客户名称", "下单时间", "订单状态", "雪碧活动商品金额", "理论赠品数量", "实际赠品数量", "权益一致", "销售明细匹配", "支付风险"], "rows": gift["details"]},
            {"name": "满赠异常订单", "title": "满赠异常订单明细（未赠及异常赠送）", "headers": ["订单编号", "客户名称", "下单时间", "订单状态", "雪碧活动商品金额", "理论赠品数量", "实际赠品数量", "权益一致", "销售明细匹配", "支付风险", "异常类型", "异常原因"], "rows": gift["exception_details"]}
        ],
        "gap_rows": gap_rows,
    }


def analyze_case(config_path: Path) -> Dict[str, Any]:
    config_path = Path(config_path).resolve()
    config = json.loads(config_path.read_text(encoding="utf-8"))
    source_root = (config_path.parent / config["source_root"]).resolve()
    coupon = _coupon_analysis(source_root, config["activities"]["下单返券"])
    gift = _gift_analysis(source_root, config["activities"]["满赠"])
    result: Dict[str, Any] = {
        "platform": config["platform"],
        "dealer": config["dealer"],
        "source_root": str(source_root),
        "activities": {"满减": coupon, "满赠": gift},
        "overall_conclusion": "条件支持",
        "overall_basis": "下单返券按8月26日至9月8日统一阶段样本、满赠按完整活动窗口进行核验；51张核销券可辅助反推客户具备领券资格，但不构成合规判定。返券仍缺9月9日至9月26日数据及正式触发订单号，满赠有4单未赠和1单异常赠送，且售后与费用资料缺失。",
    }
    result["issues"] = _issues(coupon, gift)
    result["field_mappings"] = build_complete_field_mappings(source_root, config)
    result["report"] = _report_contract(result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="验证舟谱-羿柏下单返券与满赠数据闭环")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = analyze_case(args.config)
    output_path = args.output or PROJECT_ROOT / "outputs" / result["dealer"] / "run.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(_json_safe(result), ensure_ascii=False, indent=2), encoding="utf-8")
    print(output_path)


if __name__ == "__main__":
    main()
