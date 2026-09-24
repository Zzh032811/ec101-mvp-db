import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const outputPath = path.resolve(process.argv[2] ?? "outputs/勤进/活动任务卡_财经云_勤进.xlsx");
const previewPath = outputPath.replace(/\.xlsx$/i, ".preview.png");
const FONT = "Arial";
const COLORS = { navy: "#1F4E78", lightBlue: "#EAF3F8", amber: "#FFF2CC", green: "#E2F0D9", border: "#B7C9D6", text: "#1F2937" };

const cards = [
  {
    id: "CJY-QJ-20260826-MJ-01", sheet: "满减任务卡", name: "可口可乐每满300减15", type: "满减",
    start: "2026-08-26", end: "未提供", source: "业务说明（正式活动配置未提供）",
    rule: "可口可乐商品每满 300 元减 15 元",
    sample: "订单明细：2026-08-25 至 2026-09-01；销售明细：2026-08-26 至 2026-09-08",
    rules: [
      ["活动开始日期", "2026-08-26", "业务说明"], ["活动结束时间", "未提供", "Gap"],
      ["活动门槛", "每满 300 元", "业务说明"], ["权益", "减 15 元", "业务说明"],
      ["活动商品范围", "可口可乐商品；完整 SKU/品牌范围待配置确认", "待补充"],
      ["客户范围/限购/叠加规则", "未提供", "Gap"], ["活动编号/版本", "未提供", "Gap"],
    ],
    inputs: [
      ["活动配置", "未提供", "结束时间、商品范围、客户范围、叠加、活动编号", "Gap", "P0：未补齐不得重算"],
      ["活动执行明细", "未提供", "订单号、活动商品金额、实际优惠金额", "Gap", "P0：无法核对实际优惠"],
      ["订单明细", "销售出库明细26-08-25_26-09-01.xlsx", "订单号、下单时间、订单状态、支付状态、商品、金额", "待质检", "当前无订单状态；覆盖期需待活动结束时间确认"],
      ["销售明细", "销售出库(按单号)20260826-26-09-08.xlsx", "单号、商品、数量、金额", "待质检", "与订单明细按单号交叉核验"],
      ["客户/商品资料", "客户列表26-09-11.xlsx；勤进-产品映射-20260911-1018.xlsx", "客户、品牌、SKU、规格", "待质检", "确认可口可乐范围"],
      ["售后/费用", "退款退货、费用承担方", "最终履约与费用归属", "待补充", "缺失时不能形成费用闭环"],
    ],
  },
  {
    id: "CJY-QJ-20260821-PKG-01", sheet: "套餐任务卡", name: "可口可乐专属套餐", type: "套餐促销",
    start: "2026-08-21", end: "2026-09-16", source: "满赠活动配置.png（页面实际为套餐配置）",
    rule: "2 项雪碧商品加 1 个抱枕；套餐总额 105.60 元",
    sample: "订单明细：2026-08-21 至 2026-08-25；观察到 93 单套餐，其中 92 单组成一致",
    rules: [
      ["套餐有效期", "2026-08-21 至 2026-09-16（截图仅提供日期）", "截图"], ["参与客户", "全部客户", "截图"],
      ["总数量上限", "100", "截图"], ["客户限购数量", "1", "截图"], ["默认价格方案", "批发价", "截图"],
      ["套餐商品 1", "500ml 雪碧（膜装），1*24，1 件，47.50 元", "截图"],
      ["套餐商品 2", "2L 雪碧 6支装，1*6，2 件，单价 29.00 元，合计 58.00 元", "截图"],
      ["套餐商品 3", "可口可乐专属抱枕，1*100，1 个，0.10 元", "截图"], ["套餐总额", "105.60 元", "截图"],
      ["活动编号/版本", "未在截图中展示", "Gap"], ["精确起止时分秒", "未在截图中展示", "Gap"],
    ],
    inputs: [
      ["活动配置", "满赠活动配置.png", "有效期、客户范围、限购、套餐组成、价格", "已提供", "文件名不准确，页面实际为套餐配置"],
      ["订单明细", "满赠销售出库明细26-08-21_26-08-25.xlsx", "销售单号、销售日期、促销活动、备注、商品、金额", "待质检", "当前仅覆盖活动期前段；核验套餐组成"],
      ["销售明细", "满赠销售出库(按单号)26-09-17.xlsx", "单号、商品、数量、金额", "待质检", "与订单明细按单号交叉核验"],
      ["活动执行明细", "未提供", "套餐订单归因、实际执行状态", "Gap", "不能替代订单状态和最终履约证据"],
      ["客户/商品资料", "客户列表26-09-11.xlsx；勤进-产品映射-20260911-1018.xlsx", "客户、商品、规格", "待质检", "确认客户与商品范围"],
      ["订单状态/支付状态", "未提供", "订单状态=已完成；支付风险", "Gap", "P0：不能确认发放/有效履约；支付仅风险提示"],
      ["售后/费用", "退款退货、抱枕成本、费用承担方", "最终履约与费用归属", "待补充", "缺失时不能形成费用闭环"],
    ],
  },
];

function title(sheet, main, sub) {
  sheet.showGridLines = false;
  sheet.getRange("A2").values = [[main]];
  sheet.getRange("A2").format = { font: { name: FONT, size: 15, bold: true, color: COLORS.navy } };
  sheet.getRange("A3").values = [[sub]];
  sheet.getRange("A3").format = { font: { name: FONT, size: 10, italic: true, color: "#5B6573" } };
  sheet.getRange("A4:I4").format.borders = { bottom: { style: "thin", color: COLORS.navy } };
}

function table(sheet, row, headers, rows, widths) {
  const start = row - 1;
  const head = sheet.getRangeByIndexes(start, 0, 1, headers.length);
  head.values = [headers];
  head.format = { fill: COLORS.navy, font: { name: FONT, size: 10, bold: true, color: "#FFFFFF" }, horizontalAlignment: "center", verticalAlignment: "center", wrapText: true, borders: { preset: "all", style: "thin", color: "#FFFFFF" } };
  head.format.rowHeight = 26;
  const data = sheet.getRangeByIndexes(start + 1, 0, rows.length, headers.length);
  data.values = rows;
  data.format = { font: { name: FONT, size: 10, color: COLORS.text }, verticalAlignment: "center", wrapText: true, borders: { preset: "inside", style: "thin", color: COLORS.border } };
  data.format.autofitRows();
  widths.forEach((width, index) => sheet.getRangeByIndexes(start, index, rows.length + 1, 1).format.columnWidth = width);
}

function section(sheet, row, label) {
  const range = sheet.getRange(`A${row}:D${row}`);
  range.values = [[label, "", "", ""]];
  range.format = { fill: COLORS.lightBlue, font: { name: FONT, size: 10, bold: true, color: COLORS.navy }, borders: { preset: "outside", style: "thin", color: COLORS.border } };
}

const workbook = Workbook.create();
const overview = workbook.worksheets.add("任务卡总览");
title(overview, "EC101 活动任务卡", "财经云－勤进｜满减配置未提供；“满赠活动配置.png”页面实际为可口可乐专属套餐配置。");
table(overview, 6, ["验证编号", "经销商", "平台", "活动名称", "活动类型", "活动期间", "核心规则", "订单应导期间", "当前状态"], cards.map((card) => [card.id, "勤进", "财经云", card.name, card.type, `${card.start} 至 ${card.end}`, card.rule, `${card.start} 至 ${card.end}`, "待收数质检"]), [28, 14, 12, 24, 16, 28, 40, 28, 16]);
overview.getRange("I7:I8").format = { fill: COLORS.amber, font: { name: FONT, size: 10, bold: true, color: COLORS.text }, horizontalAlignment: "center" };
overview.getRange("A11").values = [["发放条件：订单状态=已完成；支付状态仅作风险提示。满减未提供配置，套餐仅可先验证组成与金额。"]];
overview.getRange("A11").format = { font: { name: FONT, size: 10, italic: true, color: "#5B6573" } };
overview.freezePanes.freezeRows(6);

for (const card of cards) {
  const sheet = workbook.worksheets.add(card.sheet);
  title(sheet, `${card.name}活动任务卡`, `验证编号：${card.id}｜活动配置来源：${card.source}`);
  section(sheet, 6, "任务基本信息");
  table(sheet, 7, ["字段", "内容", "字段", "内容"], [
    ["验证编号", card.id, "来源", "EC101 生成"], ["经销商", "勤进", "平台", "财经云"],
    ["活动名称", card.name, "活动类型", card.type], ["活动编号", "未在现有证据中展示", "活动状态", "未在现有证据中展示"],
    ["活动开始时间", card.start, "活动结束时间", card.end], ["订单应导范围", card.start, "至", card.end],
    ["发放条件", "订单状态=已完成", "支付状态", "仅作风险提示"], ["当前样本范围", card.sample, "当前任务状态", "待收数质检"],
  ], [24, 48, 24, 48]);
  sheet.getRange("D15").format = { fill: COLORS.amber, font: { name: FONT, size: 10, bold: true, color: COLORS.text }, horizontalAlignment: "center" };
  section(sheet, 17, "活动配置与规则");
  const ruleRows = card.rules.map(([field, value, evidence]) => [field, value, evidence, evidence === "截图" || evidence === "业务说明" ? "已记录" : "待确认"]);
  table(sheet, 18, ["配置字段", "已记录值", "证据", "状态"], ruleRows, [24, 68, 24, 16]);
  sheet.getRange(`D19:D${18 + ruleRows.length}`).conditionalFormats.add("containsText", { text: "待确认", format: { fill: COLORS.amber } });
  const collectionStart = 21 + ruleRows.length;
  section(sheet, collectionStart, "收数与输入数据质检");
  table(sheet, collectionStart + 1, ["资料类型", "取数路径/证据", "关键检查字段", "状态", "质检要求"], card.inputs, [18, 44, 44, 16, 46]);
  const statusStart = collectionStart + 2;
  sheet.getRange(`D${statusStart}:D${statusStart + card.inputs.length - 1}`).conditionalFormats.add("containsText", { text: "待", format: { fill: COLORS.amber } });
  sheet.getRange(`D${statusStart}:D${statusStart + card.inputs.length - 1}`).conditionalFormats.add("containsText", { text: "已提供", format: { fill: COLORS.green } });
  sheet.freezePanes.freezeRows(6);
}

workbook.recalculate();
console.log((await workbook.inspect({ kind: "table", range: "任务卡总览!A2:I11", include: "values,formulas", tableMaxRows: 12, tableMaxCols: 10 })).ndjson);
console.log((await workbook.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!", options: { useRegex: true, maxResults: 100 }, summary: "formula error scan" })).ndjson);
await fs.mkdir(path.dirname(outputPath), { recursive: true });
const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
const preview = await workbook.render({ sheetName: "任务卡总览", autoCrop: "all", scale: 1.25, format: "png" });
await fs.writeFile(previewPath, new Uint8Array(await preview.arrayBuffer()));
console.log(JSON.stringify({ outputPath, previewPath }));
