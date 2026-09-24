# -*- coding: utf-8 -*-
"""配置驱动的通用字段映射工具 (平台无关, 可复用给第三平台).

三层职责:
  std_field_mapping 表  = 映射真源 (raw_field -> ec101_field), 由 seed_*.py 灌入
  load_mapping()        = 读表, 得到某平台某模块的 {原始列名: EC101标准字段}
  map_rows()            = 按"列名"(非列序)把原始行翻译成 {EC101标准字段: 值}
  EC101_TO_CORE / project() = 把 EC101标准字段绑定到 CORE 表列名 (1:1 机械映射)

舟谱特有的非 1:1 语义(复合主键/双过桥/XD权威状态/计算列)不在这里, 放 ingest_zhoupu.py 薄适配层.
"""
from typing import Any, Dict, List


# EC101标准字段 -> CORE 表列 (平台无关的固定绑定, 按目标表分组).
# 故意省略的字段由薄适配层特殊处理:
#   order_header.订单状态   -> 决策5: 取 XD 权威状态, 无 XD 才回退 SXD, 故不走 1:1 绑定
#   order_line.discount_amount -> 舟谱无独立优惠列, 由 优惠前金额 - 实付金额 计算
#   order_line.base_qty        -> SXD 无"基本单位数量"列, 由 order_qty × 每箱换算 推导
EC101_TO_CORE: Dict[str, Dict[str, str]] = {
    "customer": {
        "客户名称": "customer_name",
        "客户类型": "customer_type",
        "客户等级": "customer_level",
        "客户标签": "customer_tag",
        "客户区域": "customer_region",
        "所属业务员": "salesperson_name",
        "建档时间": "created_at",
        "客户状态": "status",
    },
    "product": {
        "平台商品编号": "platform_product_no",
        "商品名称": "product_name",
        "商品品牌": "brand",
        "商品目录/品类": "category",
        "商品规格": "spec",
        "商品条码": "barcode",
        "基本单位": "base_unit",
        "箱规": "box_conversion",
        "太古产品代码": "swire_product_code",
    },
    "order_header": {
        "订单编号": "order_no",
        "下单时间": "order_time",
        "支付方式": "pay_method",
        "支付状态": "pay_status",
        "下游订单编号": "downstream_order_no",
        "订单来源": "order_source",
        "订单类型": "order_type",
        # 订单状态: 见上, 由适配层取 XD
    },
    "order_line": {
        "订货数量": "order_qty",
        "订货单位": "order_unit",
        "基本单位数量": "base_qty",
        "基本单位": "base_unit",
        "优惠前金额": "pre_discount_amount",
        "单价": "unit_price",
        "退货数量": "return_qty",
        # discount_amount: 由适配层计算
    },
    "fulfillment": {
        "履约订单状态": "order_status",
        "完成时间": "completed_at",
        "退货数量": "return_qty",
    },
}


def load_mapping(conn, platform: str, module: str) -> Dict[str, str]:
    """读 std_field_mapping, 返回 {原始列名: EC101标准字段}.
    只取 V1 映射行 (is_non_v1=0 且 ec101_field 非空); 非V1(—)/Gap 行不参与落库.
    """
    sql = (
        "SELECT raw_field, ec101_field FROM std_field_mapping "
        "WHERE platform=? AND module=? AND is_non_v1=0 "
        "AND ec101_field IS NOT NULL AND ec101_field<>''"
    )
    return {raw: ec for raw, ec in conn.execute(sql, (platform, module))}


def _first_index(header: List[str]) -> Dict[str, int]:
    """列名 -> 首个出现的下标 (重名列如 XD 的多个"单位名称"取第一个)."""
    idx: Dict[str, int] = {}
    for i, name in enumerate(header):
        key = str(name).strip()
        if key and key not in idx:
            idx[key] = i
    return idx


def ec_col_index(header: List[str], mapping: Dict[str, str]) -> Dict[str, int]:
    """{EC101标准字段: 列下标} — 仅含 header 中实际存在的列.
    供大文件(XD 4.6万/2.8万行)按行流式取值, 避免 map_rows 一次性物化上万个 dict.
    """
    idx = _first_index(header)
    return {ec: idx[raw] for raw, ec in mapping.items() if raw in idx}


def map_rows(header: List[str], rows: List[List[Any]], mapping: Dict[str, str]) -> List[Dict[str, Any]]:
    """按列名把原始行翻译成 [{EC101标准字段: 值}].
    天然容忍满减/满赠同类文件的列序与列名差异; mapping 未命中或文件缺失的列不产出.
    """
    idx = _first_index(header)
    # ec101_field -> 列下标 (同一 ec101_field 可能被多个原始别名指向, 取文件中实际存在的那个)
    col_of: Dict[str, int] = {}
    for raw_field, ec_field in mapping.items():
        if raw_field in idx:
            col_of[ec_field] = idx[raw_field]
    out: List[Dict[str, Any]] = []
    for row in rows:
        rec: Dict[str, Any] = {}
        for ec_field, ci in col_of.items():
            rec[ec_field] = row[ci] if ci < len(row) else ""
        out.append(rec)
    return out


def project(mapped_row: Dict[str, Any], table: str) -> Dict[str, Any]:
    """把 {EC101标准字段: 值} 按 EC101_TO_CORE[table] 投影成 {CORE列: 值}.
    只产出该行实际拥有的字段; 缺失字段不写键 (交由适配层/DB 默认值处理).
    """
    bind = EC101_TO_CORE.get(table, {})
    out: Dict[str, Any] = {}
    for ec_field, col in bind.items():
        if ec_field in mapped_row:
            out[col] = mapped_row[ec_field]
    return out


def unmapped_columns(conn, platform: str, module: str, header: List[str]) -> List[str]:
    """返回 header 中在 std_field_mapping(该平台该模块)里"完全无行"的列 (供 dry-run 未映射报告).
    注意: 有行但标记为非V1(—)的列不算未映射 (已确认无需入库), 故此处不筛 is_non_v1.
    """
    rows = conn.execute(
        "SELECT raw_field FROM std_field_mapping WHERE platform=? AND module=?",
        (platform, module),
    )
    known = {r[0] for r in rows}
    seen = set()
    result = []
    for name in header:
        key = str(name).strip()
        if key and key not in known and key not in seen:
            seen.add(key)
            result.append(key)
    return result
