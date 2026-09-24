from datetime import datetime
from decimal import Decimal, ROUND_FLOOR
from typing import Any, Mapping


def _as_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("/", "-"))


def eligible_order(order: Mapping[str, Any], rule: Mapping[str, Any]) -> bool:
    order_time = _as_datetime(order["下单时间"])
    start_at = _as_datetime(rule["start_at"])
    end_at = _as_datetime(rule["end_at"])
    required_status = rule.get("required_order_status", "已完成")
    return start_at <= order_time <= end_at and order.get("订单状态") == required_status


def full_reduction(amount: Any, threshold: Any, benefit: Any) -> float:
    amount_decimal = Decimal(str(amount))
    threshold_decimal = Decimal(str(threshold))
    benefit_decimal = Decimal(str(benefit))
    tiers = (amount_decimal / threshold_decimal).to_integral_value(rounding=ROUND_FLOOR)
    return float(tiers * benefit_decimal)


def payment_risk(order: Mapping[str, Any]) -> str:
    if order.get("订单状态") == "已完成" and order.get("支付状态") == "未支付":
        return "已完成但未支付：线下实收无法确认"
    return ""

