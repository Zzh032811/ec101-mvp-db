from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

import pandas as pd

from scripts.source_readers import read_table


V1_FIELD_SPECS: Dict[str, List[Tuple[str, str, str]]] = {
    "客户资料": [
        ("客户编号", "平台原始", "P0"), ("客户名称", "平台原始", "P0"),
        ("客户类型", "平台原始", "P1"), ("客户等级", "平台原始", "P1"),
        ("客户标签", "平台原始", "P1"), ("客户区域", "平台原始", "P1"),
        ("客户线路", "平台原始", "P1"), ("所属业务员", "平台原始", "P1"),
        ("上级分销商", "平台原始", "P1"), ("建档时间", "平台原始", "P1"),
        ("客户状态", "平台原始", "P1"), ("太古售点编号", "平台/内部映射", "P1"),
        ("客户匹配状态", "Skill计算", "P1"),
    ],
    "商品资料": [
        ("平台商品编号", "平台原始", "P0"), ("商品名称", "平台原始", "P0"),
        ("商品品牌", "平台原始", "P0"), ("商品目录/品类", "平台原始", "P1"),
        ("商品规格", "平台原始", "P1"), ("商品条码", "平台原始", "P1"),
        ("基本单位", "平台原始", "P0"), ("箱规", "平台/太古资料", "P0"),
        ("每箱基本单位数量", "平台/太古资料", "P0"), ("太古产品代码", "太古资料/映射", "P1"),
        ("太古SKU匹配状态", "Skill计算", "P1"),
    ],
    "订单明细": [
        ("订单编号", "平台原始", "P0"), ("订单行编号", "平台原始/Skill生成", "P0"),
        ("下单时间", "平台原始", "P0"), ("客户编号", "平台原始", "P0"),
        ("商品编号", "平台原始", "P0"), ("商品名称", "平台原始", "P1"),
        ("订货数量", "平台原始", "P0"), ("订货单位", "平台原始", "P0"),
        ("基本单位数量", "平台原始/Skill换算", "P0"), ("基本单位", "平台原始", "P0"),
        ("单价", "平台原始", "P1"), ("优惠前金额", "平台原始", "P0"),
        ("总优惠金额", "平台原始", "P0"), ("实付金额", "平台原始", "P0"),
        ("已发货数量", "平台原始", "P1"), ("未发货数量", "平台原始", "P1"),
        ("退货数量", "平台原始", "P0"), ("订单状态", "平台原始", "P0"),
        ("支付方式", "平台原始", "P1"), ("支付状态", "平台原始", "P1"),
        ("订单来源", "平台原始", "P1"), ("订单类型", "平台原始", "P1"),
        ("所属业务员", "平台原始", "P1"), ("优惠券编号", "平台原始", "P1"),
        ("优惠券优惠金额", "平台原始", "P1"),
    ],
    "销售明细": [
        ("销售单据编号", "平台原始", "P1"), ("关联订单编号", "平台原始/映射", "P0"),
        ("销售时间", "平台原始", "P1"), ("客户编号", "平台原始", "P0"),
        ("商品编号", "平台原始", "P0"), ("销售数量", "平台原始", "P0"),
        ("销售单位", "平台原始", "P1"), ("优惠前金额", "平台原始", "P1"),
        ("优惠金额", "平台原始", "P1"), ("销售金额", "平台原始", "P0"),
        ("销售/订单状态", "平台原始", "P0"),
    ],
    "活动配置": [
        ("活动编号", "平台原始", "P0"), ("活动名称", "平台原始", "P0"),
        ("活动类型", "平台原始/Skill识别", "P0"), ("促销方式", "平台原始", "P0"),
        ("优惠方式", "平台原始", "P1"), ("活动开始时间", "平台原始", "P0"),
        ("活动结束时间", "平台原始", "P0"), ("活动状态", "平台原始", "P0"),
        ("活动规则版本", "Skill生成", "P1"), ("门槛类型", "平台原始/Skill结构化", "P0"),
        ("门槛值", "平台原始", "P0"), ("门槛单位", "平台原始/映射", "P0"),
        ("最少参与SKU数", "平台原始", "P1"), ("必买商品编号", "平台原始", "P0*"),
        ("必买商品数量", "平台原始", "P0*"), ("必买商品单位", "平台原始", "P0*"),
        ("权益类型", "平台原始/Skill结构化", "P0"), ("权益金额", "平台原始", "P0*"),
        ("赠品商品编号", "平台原始", "P0*"), ("赠品数量", "平台原始", "P0*"),
        ("赠品单位", "平台原始", "P0*"), ("折扣率", "平台原始", "P0*"),
        ("赠送优惠券编号", "平台原始", "P0*"), ("活动商品范围类型", "平台原始", "P0"),
        ("活动商品范围值", "平台原始", "P0"), ("活动客户范围类型", "平台原始", "P0"),
        ("活动客户范围值", "平台原始", "P0"), ("禁用对象类型", "平台原始", "P1"),
        ("禁用对象值", "平台原始", "P1"), ("是否允许叠加其他活动", "平台原始/人工确认", "P0"),
        ("是否允许使用优惠券", "平台原始/人工确认", "P0"), ("限购类型", "平台原始", "P1"),
        ("限购数量", "平台原始", "P1"), ("使用场景", "平台原始", "P1"),
        ("其他活动限制", "平台原始/人工确认", "P1"),
    ],
    "活动执行": [
        ("活动订单编号", "平台原始", "P0"), ("活动编号", "平台原始", "P0"),
        ("客户编号", "平台原始", "P0"), ("客户名称", "平台原始", "P1"),
        ("订单行编号", "平台原始/Skill生成", "P1"), ("商品编号", "平台原始", "P1"),
        ("活动商品金额", "平台原始", "P0"), ("平台实际权益", "平台原始", "P0"),
        ("理论权益", "Skill计算", "P0"), ("权益一致性", "Skill计算", "P0"),
        ("活动政策原文", "平台原始", "P1"), ("赠品实发数量", "平台原始/Skill汇总", "P0"),
        ("订单状态", "平台原始/关联", "P0"),
    ],
    "履约售后": [
        ("最终有效订单", "Skill计算", "P0"), ("退款状态", "平台原始", "P0"),
        ("退款金额", "平台原始", "P0"), ("退货数量", "平台原始", "P0"),
        ("赠品冲销数量", "平台原始", "P0"), ("售后完成时间", "平台原始", "P1"),
    ],
    "费用结果": [
        ("费用承担方", "平台原始/人工确认", "P0"), ("单位费用", "人工输入", "P0"),
        ("理论活动费用", "Skill计算", "P0"), ("实际活动费用", "Skill计算", "P0"),
        ("最终有效费用", "Skill计算", "P0"), ("费用核算状态", "Skill计算", "P0"),
    ],
}


RAW_TO_STANDARD = {
    "客户资料": {"客户编号": "客户编号", "客户唯一序号": "客户编号", "客户名称": "客户名称", "客户类型": "客户类型", "客户类别": "客户类型", "客户等级": "客户等级", "客户标签": "客户标签", "客户区域": "客户区域", "片区": "客户区域", "客户线路": "客户线路", "所属业务员": "所属业务员", "业务员": "所属业务员", "专属员工": "所属业务员", "上级分销商": "上级分销商", "添加时间": "建档时间", "状态": "客户状态", "门店状态": "客户状态"},
    "商品资料": {"商品编号": "平台商品编号", "商品主键": "平台商品编号", "商品唯一序号": "平台商品编号", "商品名称": "商品名称", "合作产品-商品名称": "商品名称", "品牌": "商品品牌", "一级目录": "商品目录/品类", "类别": "商品目录/品类", "规格值1": "商品规格", "规格": "商品规格", "合作产品-产品规格": "商品规格", "条形码": "商品条码", "商品条码": "商品条码", "合作产品-单位条码": "商品条码", "单位": "基本单位", "单位名称": "基本单位", "包装规格": "箱规", "单位换算": "箱规", "太古产品-箱规则": "箱规", "换算关系1": "每箱基本单位数量", "大单位换算": "每箱基本单位数量", "合作产品-数量/箱": "每箱基本单位数量", "太古产品代码": "太古产品代码", "匹配状态": "太古SKU匹配状态"},
    "订单明细": {"订单编号": "订单编号", "下单时间": "下单时间", "客户编号": "客户编号", "商品编号": "商品编号", "商品名称": "商品名称", "订货数量": "订货数量", "订单数量": "订货数量", "实际数量": "订货数量", "订货数量单位": "订货单位", "单位名称": "订货单位", "基本单位数量": "基本单位数量", "基本单位": "基本单位", "订货单价": "单价", "实际单价": "单价", "优惠前金额": "优惠前金额", "优惠金额": "总优惠金额", "订货金额": "实付金额", "实际金额": "实付金额", "已发货数量": "已发货数量", "未发货数量": "未发货数量", "退货数量": "退货数量", "订单状态": "订单状态", "支付方式": "支付方式", "支付时间": "支付方式", "支付状态": "支付状态", "订单来源": "订单来源", "订单类型": "订单类型", "所属业务员": "所属业务员", "优惠券优惠金额": "优惠券优惠金额"},
    "销售明细": {"单据编号": "关联订单编号", "订单编号": "关联订单编号", "销售单号": "销售单据编号", "单号": "销售单据编号", "下单时间": "销售时间", "销售日期": "销售时间", "开单日期": "销售时间", "商品编号": "商品编号", "数量": "销售数量", "单位": "销售单位", "优惠前金额": "优惠前金额", "销售-金额": "优惠前金额", "优惠金额": "优惠金额", "销售-差价金额": "优惠金额", "销售金额": "销售金额", "实际金额": "销售金额", "销售-折后金额": "销售金额", "订单状态": "销售/订单状态"},
    "活动执行": {"订单号": "活动订单编号", "客户": "客户名称", "商品总金额": "活动商品金额", "促销优惠金额": "平台实际权益", "享受促销政策": "活动政策原文", "订单状态": "订单状态"},
}


SCREENSHOT_CONFIG_FIELDS = {
    "活动名称", "促销方式", "优惠方式", "活动开始时间", "活动结束时间", "活动状态",
    "门槛类型", "门槛值", "门槛单位", "最少参与SKU数", "必买商品编号", "必买商品数量",
    "必买商品单位", "权益类型", "权益金额", "赠品商品编号", "赠品数量", "赠品单位",
    "活动商品范围类型", "活动商品范围值", "活动客户范围类型", "活动客户范围值",
    "禁用对象类型", "禁用对象值", "是否允许叠加其他活动", "是否允许使用优惠券",
    "限购类型", "限购数量", "使用场景", "其他活动限制",
}


def _source_files(config: Dict[str, Any]) -> Dict[str, List[Any]]:
    if "source_files" in config:
        return config["source_files"]
    return {
        "客户资料": ["User2026091613203383772.xls"],
        "商品资料": ["Product2026091613223281646.xls"],
        "订单明细": [config["activities"]["满减"]["order_file"], config["activities"]["满赠"]["order_file"]],
        "销售明细": [config["activities"]["满减"]["sales_file"], config["activities"]["满赠"]["sales_file"]],
        "活动执行": [config["activities"]["满减"]["activity_file"], config["activities"]["满赠"]["activity_file"]],
    }


def _deduplicate_headers(headers: Iterable[str]) -> List[str]:
    counts: Dict[str, int] = {}
    result: List[str] = []
    for index, raw_header in enumerate(headers, start=1):
        header = str(raw_header).strip() or f"未命名列{index}"
        counts[header] = counts.get(header, 0) + 1
        result.append(header if counts[header] == 1 else f"{header}_{counts[header]}")
    return result


def _configured_columns(source_root: Path, source: Any) -> Tuple[str, List[str]]:
    if isinstance(source, str):
        return source, list(map(str, read_table(source_root / source).columns))

    file_name = source["file"]
    header_rows = source.get("header_rows")
    if not header_rows:
        frame = pd.read_excel(source_root / file_name, sheet_name=source.get("sheet", 0), engine="openpyxl")
        return file_name, list(map(str, frame.columns))

    raw = pd.read_excel(
        source_root / file_name,
        sheet_name=source.get("sheet", 0),
        header=None,
        nrows=max(header_rows),
        engine="openpyxl",
    )
    header_frames = [raw.iloc[row_number - 1] for row_number in header_rows]
    last_group = ""
    combined: List[str] = []
    for column in range(raw.shape[1]):
        values = []
        for header_frame in header_frames:
            value = header_frame.iloc[column]
            values.append("" if pd.isna(value) else str(value).strip())
        if values[0]:
            last_group = values[0]
        if len(values) == 1:
            combined.append(values[0])
        elif values[-1]:
            combined.append(f"{values[0] or last_group}-{values[-1]}")
        else:
            combined.append(values[0])
    return file_name, _deduplicate_headers(combined)


def _spec_index(module: str) -> Dict[str, Tuple[str, str]]:
    return {field: (source_type, importance) for field, source_type, importance in V1_FIELD_SPECS[module]}


def build_complete_field_mappings(source_root: Path, config: Dict[str, Any]) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    mapped_standard_fields = defaultdict(set)

    for module, file_names in _source_files(config).items():
        occurrences = defaultdict(set)
        for source in file_names:
            file_name, columns = _configured_columns(source_root, source)
            for column in columns:
                occurrences[column].add(file_name)
        specs = _spec_index(module)
        aliases = RAW_TO_STANDARD.get(module, {})
        for raw_field in sorted(occurrences):
            standard_field = aliases.get(raw_field, "—")
            is_v1 = standard_field != "—"
            if is_v1:
                mapped_standard_fields[module].add(standard_field)
            source_type, importance = specs.get(standard_field, ("平台原始", "P2"))
            rows.append({
                "模块": module,
                "来源文件": "；".join(sorted(occurrences[raw_field])),
                "经销商原始字段": raw_field,
                "EC101标准字段": standard_field,
                "字段关系": "V1字段" if is_v1 else "非V1字段",
                "来源类型": source_type,
                "重要度": importance,
                "证据等级": "高" if is_v1 else "—",
                "状态": "已映射" if is_v1 else "保留原字段",
                "说明": "原始字段不删除" if not is_v1 else "",
            })

    for module, specs in V1_FIELD_SPECS.items():
        for standard_field, source_type, importance in specs:
            if standard_field in mapped_standard_fields[module]:
                continue
            screenshot_fields = set(config.get("activity_config_fields", []))
            partial_screenshot_fields = set(config.get("activity_config_partial_fields", []))
            screenshot_notes = config.get("activity_config_notes", {})
            if not screenshot_fields and config.get("platform") == "快马":
                screenshot_fields = SCREENSHOT_CONFIG_FIELDS
            if module == "活动配置" and standard_field in screenshot_fields:
                raw_field = standard_field
                source_file = "；".join(config.get("activity_config_sources", ["image.png", "image (1).png", "image (2).png"]))
                status = "部分截图可达" if standard_field in partial_screenshot_fields else "截图可达"
                evidence = "中"
                note = screenshot_notes.get(standard_field, "活动配置截图人工结构化；非平台结构化导出")
            elif "Skill" in source_type:
                raw_field = "Skill计算"
                source_file = "—"
                status = "可计算"
                evidence = "高"
                note = "由原始字段和规则计算"
            else:
                raw_field = "—"
                source_file = "—"
                status = "Gap"
                evidence = "低"
                note = "V1要求但当前经销商数据未提供"
            rows.append({
                "模块": module,
                "来源文件": source_file,
                "经销商原始字段": raw_field,
                "EC101标准字段": standard_field,
                "字段关系": "V1字段",
                "来源类型": source_type,
                "重要度": importance,
                "证据等级": evidence,
                "状态": status,
                "说明": note,
            })

    module_order = {module: index for index, module in enumerate(V1_FIELD_SPECS)}
    return sorted(
        rows,
        key=lambda row: (
            module_order.get(row["模块"], 99),
            0 if row["字段关系"] == "V1字段" else 1,
            row["EC101标准字段"],
            row["经销商原始字段"],
        ),
    )
