import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const outputPath = path.resolve(process.argv[2] ?? "outputs/兴路强/活动任务卡_快马_兴路强.xlsx");
const previewPath = outputPath.replace(/\.xlsx$/i, ".preview.png");
const FONT = "Arial";
const COLORS = {
  navy: "#1F4E78",
  lightBlue: "#EAF3F8",
  amber: "#FFF2CC",
  green: "#E2F0D9",
  gray: "#F2F2F2",
  border: "#B7C9D6",
  text: "#1F2937",
};

const customerTypes = "测试类型、西乡、零售、线下付款客户、闪电仓、可口可乐业务";

const activities = [
  {
    id: "KM-XLQ-20260819-MZ-01",
    sheet: "满赠任务卡",
    name: "满赠优惠",
    type: "组合促销－满赠",
    start: new Date("2026-08-19T15:15:00Z"),
    end: new Date("2026-08-31T23:59:00Z"),
    source: "组合促销满赠方案.png",
    rules: [
      ["优惠方式", "阶梯优惠", "截图"],
      ["促销方式", "满一定金额立赠", "截图"],
      ["活动门槛", "金额满 100 元", "截图"],
      ["权益", "赠雪碧 冰丝抱枕（赠品勿下）1 个", "截图"],
      ["赠品商品编号", "348721357", "截图"],
      ["赠品单位", "个", "截图"],
      ["活动商品范围", "指定商品；具体商品清单未在截图中展示", "待导出商品清单"],
      ["活动客户范围", `指定客户类型：${customerTypes}`, "截图"],
      ["禁用对象", "无", "截图"],
      ["购买限制", "每用户限购 1 单", "截图"],
      ["使用设备", "不限", "截图"],
      ["限制充值赠送客户", "关闭", "截图"],
      ["使用场景", "客户自下单可用；代下单不可用", "截图"],
      ["允许与其他活动同时参与", "是", "截图"],
      ["允许使用优惠券", "是", "截图"],
      ["最少参与 SKU 数", "0（不限制）", "截图"],
      ["必买商品", "截图未完整展示，待确认", "待补充"],
    ],
  },
  {
    id: "KM-XLQ-20260831-MJ-01",
    sheet: "满减任务卡",
    name: "可口可乐满减",
    type: "组合促销－满减",
    start: new Date("2026-08-31T10:58:00Z"),
    end: new Date("2026-09-17T23:59:00Z"),
    source: "组合促销满减方案.png",
    rules: [
      ["优惠方式", "阶梯优惠", "截图"],
      ["促销方式", "满一定金额立减", "截图"],
      ["活动门槛", "金额满 300 元", "截图"],
      ["权益", "立减 15 元", "截图"],
      ["活动商品范围", "指定品牌：可口可乐", "截图"],
      ["活动客户范围", `指定客户类型：${customerTypes}`, "截图"],
      ["禁用对象", "无", "截图"],
      ["购买限制", "每用户限购 0 单（不限制）", "截图"],
      ["使用设备", "不限", "截图"],
      ["限制充值赠送客户", "关闭", "截图"],
      ["使用场景", "客户自下单可用；代下单不可用", "截图"],
      ["允许与其他活动同时参与", "是", "截图"],
      ["允许使用优惠券", "是", "截图"],
      ["最少参与 SKU 数", "0（不限制）", "截图"],
      ["必买商品", "截图未完整展示，待确认", "待补充"],
    ],
  },
];

function applyTitle(sheet, title, subtitle) {
  sheet.showGridLines = false;
  sheet.getRange("A2").values = [[title]];
  sheet.getRange("A2").format = { font: { name: FONT, size: 15, bold: true, color: COLORS.navy } };
  sheet.getRange("A3").values = [[subtitle]];
  sheet.getRange("A3").format = { font: { name: FONT, size: 10, italic: true, color: "#5B6573" } };
  sheet.getRange("A4:H4").format.borders = { bottom: { style: "thin", color: COLORS.navy } };
}

function writeTable(sheet, startRow, headers, rows, widths) {
  const start = startRow - 1;
  const headerRange = sheet.getRangeByIndexes(start, 0, 1, headers.length);
  headerRange.values = [headers];
  headerRange.format = {
    fill: COLORS.navy,
    font: { name: FONT, size: 10, bold: true, color: "#FFFFFF" },
    horizontalAlignment: "center",
    verticalAlignment: "center",
    wrapText: true,
    borders: { preset: "all", style: "thin", color: "#FFFFFF" },
  };
  headerRange.format.rowHeight = 26;
  const dataRange = sheet.getRangeByIndexes(start + 1, 0, rows.length, headers.length);
  dataRange.values = rows;
  dataRange.format = {
    font: { name: FONT, size: 10, color: COLORS.text },
    verticalAlignment: "center",
    wrapText: true,
    borders: { preset: "inside", style: "thin", color: COLORS.border },
  };
  dataRange.format.autofitRows();
  widths.forEach((width, index) => {
    sheet.getRangeByIndexes(start, index, rows.length + 1, 1).format.columnWidth = width;
  });
}

function sectionLabel(sheet, row, text) {
  const range = sheet.getRange(`A${row}:D${row}`);
  range.values = [[text, "", "", ""]];
  range.format = {
    fill: COLORS.lightBlue,
    font: { name: FONT, size: 10, bold: true, color: COLORS.navy },
    verticalAlignment: "center",
    borders: { preset: "outside", style: "thin", color: COLORS.border },
  };
}

function buildOverview(workbook) {
  const sheet = workbook.worksheets.add("任务卡总览");
  applyTitle(sheet, "EC101 活动任务卡", "快马－兴路强｜活动配置已结构化，数据质检通过后才进入活动验证。");
  const headers = ["验证编号", "经销商", "平台", "活动名称", "活动类型", "活动期间", "核心规则", "订单应导期间", "当前状态"];
  const rows = activities.map((activity) => [
    activity.id,
    "兴路强",
    "快马",
    activity.name,
    activity.type,
    activity.start,
    activity.name === "满赠优惠" ? "满100赠抱枕1个" : "满300固定减15元",
    `${activity.start.toISOString().slice(0, 10)} 至 ${activity.end.toISOString().slice(0, 10)}`,
    "待收数质检",
  ]);
  writeTable(sheet, 6, headers, rows, [28, 14, 12, 18, 18, 28, 28, 30, 16]);
  sheet.getRange("F7:F8").format.numberFormat = "yyyy-mm-dd hh:mm";
  sheet.getRange("I7:I8").format = { fill: COLORS.amber, font: { name: FONT, size: 10, bold: true, color: COLORS.text }, horizontalAlignment: "center" };
  sheet.getRange("A11").values = [["发放条件：订单状态=已完成。支付状态用于风险提示，不作为发放排除条件。"]];
  sheet.getRange("A11").format = { font: { name: FONT, size: 10, italic: true, color: "#5B6573" } };
  sheet.freezePanes.freezeRows(6);
}

function buildActivityCard(workbook, activity) {
  const sheet = workbook.worksheets.add(activity.sheet);
  applyTitle(sheet, `${activity.name}活动任务卡`, `验证编号：${activity.id}｜活动配置来源：${activity.source}`);

  sectionLabel(sheet, 6, "任务基本信息");
  const basicRows = [
    ["验证编号", activity.id, "来源", "EC101 生成"],
    ["经销商", "兴路强", "平台", "快马"],
    ["活动名称", activity.name, "活动类型", activity.type],
    ["活动编号", "未在截图中展示", "活动状态", "未在截图中展示"],
    ["活动开始时间", activity.start, "活动结束时间", activity.end],
    ["订单应导范围", activity.start, "至", activity.end],
    ["发放条件", "订单状态=已完成", "支付状态", "仅作风险提示"],
    ["售后观察期", "待业务确认", "当前任务状态", "待收数质检"],
  ];
  writeTable(sheet, 7, ["字段", "内容", "字段", "内容"], basicRows, [22, 36, 22, 36]);
  sheet.getRange("B12:B13").format.numberFormat = "yyyy-mm-dd hh:mm";
  sheet.getRange("D12:D13").format.numberFormat = "yyyy-mm-dd hh:mm";
  sheet.getRange("D15").format = { fill: COLORS.amber, font: { name: FONT, size: 10, bold: true, color: COLORS.text }, horizontalAlignment: "center" };

  sectionLabel(sheet, 17, "活动配置与规则");
  const ruleRows = activity.rules.map(([field, value, evidence]) => [field, value, evidence, evidence === "待补充" ? "待确认" : "已记录"]);
  writeTable(sheet, 18, ["配置字段", "已记录值", "证据", "状态"], ruleRows, [24, 62, 22, 16]);
  const lastRuleRow = 18 + ruleRows.length;
  sheet.getRange(`D${lastRuleRow}:D${lastRuleRow}`).format = { fill: COLORS.amber, font: { name: FONT, size: 10, bold: true, color: COLORS.text }, horizontalAlignment: "center" };

  const collectionStart = lastRuleRow + 3;
  sectionLabel(sheet, collectionStart, "收数与输入数据质检");
  const collectionRows = [
    ["活动配置", activity.source, "活动名称、规则、时间、商品/客户范围", "已提供", "核对截图与任务卡一致"],
    ["活动执行明细", "活动统计导出", "订单号、活动商品金额、实际权益/优惠", "待收集", "必须完整覆盖活动期"],
    ["订单明细", "销售－报表－订货明细", "订单编号、下单时间、订单状态、支付状态、商品、金额", "待质检", "日期最小/最大值覆盖活动期"],
    ["销售明细", "销售－报表－销售明细", "订单编号、销售商品、数量、金额", "待质检", "与订单明细按订单号交叉核验"],
    ["客户资料", "客户－客户列表", "客户编号、客户类型", "待收集", "验证客户范围"],
    ["商品资料", "商品－商品列表", "商品编号、品牌、规格", "待收集", "验证商品范围与赠品 SKU"],
    ["售后/费用", "退款退货、赠品冲销、成本、费用承担方", "最终履约与费用归属", "待补充", "缺失时只能给条件支持"],
  ];
  writeTable(sheet, collectionStart + 1, ["资料类型", "取数路径/证据", "关键检查字段", "状态", "质检要求"], collectionRows, [18, 34, 42, 16, 42]);
  const firstStatusRow = collectionStart + 2;
  sheet.getRange(`D${firstStatusRow}:D${firstStatusRow + collectionRows.length - 1}`).conditionalFormats.add("containsText", { text: "待", format: { fill: COLORS.amber } });
  sheet.getRange(`D${firstStatusRow}:D${firstStatusRow + collectionRows.length - 1}`).conditionalFormats.add("containsText", { text: "已提供", format: { fill: COLORS.green } });
  sheet.freezePanes.freezeRows(6);
}

const workbook = Workbook.create();
buildOverview(workbook);
activities.forEach((activity) => buildActivityCard(workbook, activity));
workbook.recalculate();

const check = await workbook.inspect({ kind: "table", range: "任务卡总览!A2:I11", include: "values,formulas", tableMaxRows: 12, tableMaxCols: 10 });
console.log(check.ndjson);
const errors = await workbook.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!", options: { useRegex: true, maxResults: 100 }, summary: "formula error scan" });
console.log(errors.ndjson);

await fs.mkdir(path.dirname(outputPath), { recursive: true });
const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
const preview = await workbook.render({ sheetName: "任务卡总览", autoCrop: "all", scale: 1.5, format: "png" });
await fs.writeFile(previewPath, new Uint8Array(await preview.arrayBuffer()));
console.log(JSON.stringify({ outputPath, previewPath }));
