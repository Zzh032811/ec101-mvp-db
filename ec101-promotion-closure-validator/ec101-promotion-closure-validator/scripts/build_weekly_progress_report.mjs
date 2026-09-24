import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const [outputPathArg] = process.argv.slice(2);
if (!outputPathArg) {
  throw new Error("Usage: node scripts/build_weekly_progress_report.mjs <output.xlsx>");
}

const projectRoot = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
const outputPath = path.resolve(outputPathArg);
const outputDir = path.dirname(outputPath);
const FONT = "Arial";
const COLORS = {
  navy: "#1F4E78",
  blue: "#D9EAF7",
  lightBlue: "#EEF5FA",
  amber: "#FFF2CC",
  red: "#FCE4D6",
  green: "#E2F0D9",
  border: "#B7C9D6",
  text: "#1F2937",
  gray: "#5B6573",
};

async function loadRun(dealer) {
  return JSON.parse(await fs.readFile(path.join(projectRoot, "outputs", dealer, "run.json"), "utf8"));
}

const [xingluqiang, qinjing, yibai, shunying] = await Promise.all([
  loadRun("兴路强"),
  loadRun("勤进"),
  loadRun("羿柏"),
  loadRun("顺英"),
]);

function createSheet(workbook, name, title, subtitle) {
  const sheet = workbook.worksheets.add(name);
  sheet.showGridLines = false;
  sheet.getRange("A2").values = [[title]];
  sheet.getRange("A2").format.font = { name: FONT, size: 15, bold: true, color: COLORS.navy };
  sheet.getRange("A3").values = [[subtitle]];
  sheet.getRange("A3").format.font = { name: FONT, size: 10, italic: true, color: COLORS.gray };
  sheet.getRange("A4:L4").format.borders = { bottom: { style: "thin", color: COLORS.navy } };
  return sheet;
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
  headerRange.format.rowHeight = 28;
  if (rows.length) {
    const body = sheet.getRangeByIndexes(start + 1, 0, rows.length, headers.length);
    body.values = rows;
    body.format = {
      font: { name: FONT, size: 10, color: COLORS.text },
      verticalAlignment: "center",
      wrapText: true,
      borders: { preset: "inside", style: "thin", color: COLORS.border },
    };
    body.format.autofitRows();
  }
  widths.forEach((width, index) => {
    sheet.getRangeByIndexes(start, index, Math.max(rows.length + 1, 1), 1).format.columnWidth = width;
  });
}

function addSection(sheet, row, text, width = 11) {
  const band = sheet.getRangeByIndexes(row - 1, 0, 1, width);
  band.format = { fill: COLORS.blue, borders: { preset: "outside", style: "thin", color: COLORS.border } };
  sheet.getRange(`A${row}`).values = [[text]];
  sheet.getRange(`A${row}`).format.font = { name: FONT, size: 11, bold: true, color: COLORS.navy };
}

const activityRows = [
  ["快马", "兴路强", "满减", "配置截图与活动明细可识别", `满300固定减15；${xingluqiang.activities["满减"].eligible_order_count}/${xingluqiang.activities["满减"].eligible_order_count}一致`, "优惠金额与独立销售明细一致", `订单状态=已完成；${xingluqiang.activities["满减"].payment_risk_count}单未支付`, "退款退货终态、费用承担方缺失", "条件支持", "可验证活动执行，不能确认最终费用"],
  ["快马", "兴路强", "满赠", "配置截图与活动明细可识别", `满100赠抱枕；${xingluqiang.activities["满赠"].eligible_order_count}/${xingluqiang.activities["满赠"].eligible_order_count}一致`, "赠品与销售明细一致", `订单状态=已完成；${xingluqiang.activities["满赠"].payment_risk_count}单未支付`, "抱枕成本、赠品冲销、费用承担方缺失", "条件支持", "另有1个非活动明细抱枕待确认原因"],
  ["快马", "顺网精英", "满减", "配置与活动明细可识别", `已完成订单${shunying.activities["满减"].eligible_order_count}单，理论权益与实际权益一致`, "可逐单核验", "订单状态=已完成；支付仅作风险提示", "退款退货终态、费用承担方缺失", "支持（活动执行）", "经销商整体仍为条件支持"],
  ["快马", "顺网精英", "满赠", "配置与活动明细可识别", `已完成订单${shunying.activities["满赠"].eligible_order_count}单，理论赠品与实际赠品一致`, "可逐单核验", "订单状态=已完成；支付仅作风险提示", "赠品成本、赠品冲销、费用承担方缺失", "支持（活动执行）", "经销商整体仍为条件支持"],
  ["舟谱", "翌柏商贸", "下单返券", "截图及活动明细可识别", `已完成候选订单${yibai.activities["满减"].eligible_order_count}单，可局部重算`, "返券使用可部分关联", "订单状态可用；支付字段语义待确认", "完整活动期、触发订单号、售后与费用资料缺失", "条件支持", "不能完整证明每张券由哪笔订单触发"],
  ["舟谱", "翌柏商贸", "满赠", "截图及活动明细可识别", `已完成资格订单${yibai.activities["满赠"].eligible_order_count}单`, "81单赠品一致；4单未赠；1单异常赠送", "订单状态可用；支付字段语义待确认", "赠品冲销、成本、费用承担方缺失", "条件支持", "4单未赠和1单异常赠送需逐单复核"],
  ["财经云", "勤进", "满减", "正式活动配置未提供", "无法独立重算", "无独立活动执行明细", "订单状态、支付状态未提供", "活动配置、完整活动期、售后与费用资料缺失", "未验证", "只能确认数据存在，不能判断活动执行"],
  ["财经云", "勤进", "可口可乐专属套餐", "套餐配置已提供", "93单套餐中92单组成及金额一致", "93/93与按单号销售明细匹配", "订单状态、支付状态未提供", "活动执行明细、售后、抱枕成本、费用承担方缺失", "未验证", "1单缺抱枕行，待确认缺件原因"],
];

const ruleRows = [
  ["发放资格", "订单状态=已完成", "已作为当前活动发放口径", "已完成后是否仍可退款、退货或部分退货？", "业务/平台", "P0", "决定已完成能否作为最终发放条件"],
  ["售后冲销", "暂无统一规则", "退款退货终态普遍缺失", "退款、退货、拒收后，满减、满赠、返券如何冲回？", "业务/财务", "P0", "决定是否冻结、冲回或调整费用"],
  ["支付状态", "未支付不自动排除", "快马可见货到付款或未支付；舟谱部分字段为空", "未支付是否为货到付款、账期或异常订单？", "业务/平台", "P1", "影响风险提示和后续结算条件"],
  ["活动归因", "需订单与活动可关联", "部分平台缺活动编号或触发订单号", "一单多活动时权益如何拆分？返券由哪笔订单触发？", "业务/平台", "P0", "决定活动费用归属与审计链路"],
  ["费用承担", "未形成统一来源", "活动、订单数据普遍未标识承担方", "太古、经销商、平台分别承担哪些优惠/赠品费用？", "业务/财务", "P0", "无法形成正式费用台账"],
  ["满赠异常", "异常暂列待复核", "羿柏有未赠/异常赠送；兴路强有1个非活动抱枕", "是否为补发、人工赠送、其他活动或普通销售？", "业务/平台", "P0", "决定赠品费用是否应归入活动"],
  ["未上线活动", "仅做预验证", "尚无真实执行订单", "是否允许测试订单或沙箱验证？", "项目/业务/平台", "P1", "可验证配置和数据可达性，不能验证真实费用"],
];

const workbook = Workbook.create();

const summary = createSheet(workbook, "周报摘要", "EC101 项目本周进度汇报", "截至 2026-09-18｜6 家经销商、4 类接入方式；首轮验证完成不等同于正式费用闭环完成");
const kpiHeaders = ["经销商总数", "首轮验证完成", "条件支持", "未验证", "正式费用闭环完成"];
const kpiRows = [[6, 4, 3, 1, 0]];
writeTable(summary, 6, kpiHeaders, kpiRows, [18, 18, 18, 18, 22]);
summary.getRange("A7:E7").format.font = { name: FONT, size: 14, bold: true, color: COLORS.navy };
summary.getRange("A7:D7").format.horizontalAlignment = "center";
summary.getRange("E7").format.horizontalAlignment = "center";
summary.getRange("A7:C7").format.fill = COLORS.green;
summary.getRange("D7").format.fill = COLORS.amber;
summary.getRange("E7").format.fill = COLORS.red;

addSection(summary, 10, "本周已完成", 8);
writeTable(summary, 11, ["事项", "进展说明"], [
  ["验证方法与 Skill V1", "建立初版活动数据闭环验证方法，固化标准字段、活动规则、结论判定与统一报告模板。"],
  ["真实活动首轮验证", "完成满减、满赠、下单返券、套餐等真实活动首轮验证，已形成 4 家经销商验证输出。"],
  ["发放口径", "明确订单状态=已完成为当前发放资格条件；支付状态作为风险提示，不直接排除订单。"],
  ["取数质量控制", "识别活动配置错配、订单导出周期不完整等问题，后续纳入活动任务卡与输入质检闸门。"],
], [24, 95]);

addSection(summary, 17, "当前结论", 8);
writeTable(summary, 18, ["结论", "说明"], [
  ["活动执行", "3 家经销商达到条件支持，1 家未验证；多数案例可在一定范围内核验活动规则与实际权益。"],
  ["费用闭环", "0 家具备可直接支持正式费用发放的完整闭环。"],
  ["未上线活动", "可进行配置能力和数据可达性预验证，不应表述为活动执行已验证。"],
], [24, 95]);

addSection(summary, 23, "需要协作支持", 8);
writeTable(summary, 24, ["事项", "当前动作"], [
  ["剩余经销商数据", "已联系相关同事补充快易点及庆兴的订单、销售、活动配置和活动执行数据。"],
  ["共性业务规则", "已联系相关同事确认退款退货冲销、费用承担方、未支付订单和多活动叠加等规则。"],
  ["下周交付", "完成剩余 2 家首轮验证，输出 6 家统一能力矩阵、共性 Gap 与数据库 MVP 最小数据模型建议。"],
], [24, 95]);
summary.freezePanes.freezeRows(6);

const matrix = createSheet(workbook, "4家能力矩阵", "4 家已验证经销商平台能力活动矩阵", "说明：此表评价活动执行核验能力；“条件支持/未验证”不等同于正式费用发放结论。");
writeTable(matrix, 6, ["接入方式", "经销商", "活动", "活动配置/识别", "规则重算", "实际权益及销售交叉", "订单状态/支付", "履约、售后及费用", "当前结论", "关键说明"], activityRows, [12, 14, 20, 25, 30, 30, 25, 36, 18, 42]);
matrix.getRange("I7:I14").conditionalFormats.add("containsText", { text: "未验证", format: { fill: COLORS.red, font: { color: "#9C0006", bold: true } } });
matrix.getRange("I7:I14").conditionalFormats.add("containsText", { text: "条件支持", format: { fill: COLORS.amber, font: { color: "#7F6000", bold: true } } });
matrix.getRange("I7:I14").conditionalFormats.add("containsText", { text: "支持", format: { fill: COLORS.green, font: { color: "#375623", bold: true } } });
matrix.freezePanes.freezeRows(6);
matrix.freezePanes.freezeColumns(3);

const rules = createSheet(workbook, "闭环规则待确认", "费用闭环业务规则与待确认事项", "数据缺口与业务规则需并行解决；任一 P0 未确认，均不能形成正式费用发放闭环。");
writeTable(rules, 6, ["规则主题", "当前口径", "数据现状", "待确认事项", "建议确认方", "优先级", "对项目的影响"], ruleRows, [16, 24, 32, 48, 20, 12, 42]);
rules.getRange("F7:F13").conditionalFormats.add("containsText", { text: "P0", format: { fill: COLORS.red, font: { color: "#9C0006", bold: true } } });
rules.getRange("F7:F13").conditionalFormats.add("containsText", { text: "P1", format: { fill: COLORS.amber, font: { color: "#7F6000", bold: true } } });
rules.freezePanes.freezeRows(6);

workbook.recalculate();
await fs.mkdir(outputDir, { recursive: true });
const xlsx = await SpreadsheetFile.exportXlsx(workbook);
await xlsx.save(outputPath);

const summaryCheck = await workbook.inspect({ kind: "table", range: "周报摘要!A2:B27", include: "values,formulas", tableMaxRows: 30, tableMaxCols: 6 });
console.log(summaryCheck.ndjson);
const matrixCheck = await workbook.inspect({ kind: "table", range: "4家能力矩阵!A2:J14", include: "values,formulas", tableMaxRows: 20, tableMaxCols: 12 });
console.log(matrixCheck.ndjson);
const errors = await workbook.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!", options: { useRegex: true, maxResults: 100 } });
console.log(errors.ndjson);

for (const sheetName of ["周报摘要", "4家能力矩阵", "闭环规则待确认"]) {
  const image = await workbook.render({ sheetName, autoCrop: "all", scale: 1.25, format: "png" });
  const bytes = new Uint8Array(await image.arrayBuffer());
  await fs.writeFile(path.join(outputDir, `${sheetName}.png`), bytes);
}

console.log(JSON.stringify({ outputPath, sheets: ["周报摘要", "4家能力矩阵", "闭环规则待确认"] }, null, 2));
