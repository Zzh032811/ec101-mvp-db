import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";


const [runJsonPath, outputDirArg] = process.argv.slice(2);
if (!runJsonPath || !outputDirArg) {
  throw new Error("Usage: node scripts/build_reports.mjs <run.json> <output-dir>");
}

const result = JSON.parse(await fs.readFile(runJsonPath, "utf8"));
const outputDir = path.resolve(outputDirArg);
const projectRoot = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
const templateDir = path.join(projectRoot, "templates");
const previewDir = path.join(outputDir, "_previews");
await fs.mkdir(outputDir, { recursive: true });
await fs.mkdir(templateDir, { recursive: true });
await fs.mkdir(previewDir, { recursive: true });

const FONT = "Arial";
const COLORS = {
  navy: "#1F4E78",
  blue: "#D9EAF7",
  lightBlue: "#EEF5FA",
  amber: "#FFF2CC",
  red: "#FCE4D6",
  green: "#E2F0D9",
  gray: "#F2F2F2",
  border: "#B7C9D6",
  text: "#1F2937",
};

function matrixRows(headers, objects) {
  return objects.map((object) => headers.map((header) => {
    const value = object[header] ?? "";
    // Keep long numeric order identifiers as text without showing a leading apostrophe.
    return /订单编号|订单号|单据编号|单号/.test(header) && /^\d{16,}$/.test(String(value))
      ? `\u200B${value}`
      : value;
  }));
}

function booleanText(value) {
  return value === true ? "一致" : value === false ? "不一致" : value;
}

function normalizeRows(rows) {
  return rows.map((row) => row.map((value) => booleanText(value)));
}

function createWorkbook(sheetName, title, subtitle) {
  const workbook = Workbook.create();
  const sheet = workbook.worksheets.add(sheetName);
  sheet.showGridLines = false;
  sheet.getRange("A2").values = [[title]];
  sheet.getRange("A2").format.font = { name: FONT, size: 15, bold: true, color: COLORS.navy };
  sheet.getRange("A3").values = [[subtitle]];
  sheet.getRange("A3").format.font = { name: FONT, size: 10, italic: true, color: "#5B6573" };
  sheet.getRange("A4:L4").format.borders = { bottom: { style: "thin", color: COLORS.navy } };
  return { workbook, sheet };
}

function writeTable(sheet, startRow, headers, rows, options = {}) {
  const startIndex = startRow - 1;
  const normalized = normalizeRows(rows);
  const headerRange = sheet.getRangeByIndexes(startIndex, 0, 1, headers.length);
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
  if (normalized.length) {
    const dataRange = sheet.getRangeByIndexes(startIndex + 1, 0, normalized.length, headers.length);
    dataRange.values = normalized;
    dataRange.format.font = { name: FONT, size: 10, color: COLORS.text };
    dataRange.format.verticalAlignment = "center";
    dataRange.format.borders = { preset: "inside", style: "thin", color: COLORS.border };
    dataRange.format.wrapText = Boolean(options.wrap);
    dataRange.format.autofitRows();
  }
  const fullRange = sheet.getRangeByIndexes(startIndex, 0, Math.max(normalized.length + 1, 1), headers.length);
  fullRange.format.autofitColumns();
  for (let column = 0; column < headers.length; column += 1) {
    const width = options.widths?.[column] ?? 18;
    sheet.getRangeByIndexes(startIndex, column, Math.max(normalized.length + 1, 1), 1).format.columnWidth = width;
  }
  sheet.freezePanes.freezeRows(startRow);
}

function addSourceNote(sheet, row, text) {
  sheet.getRange(`A${row}`).values = [[text]];
  sheet.getRange(`A${row}`).format.font = { name: FONT, size: 9, italic: true, color: "#5B6573" };
}

function buildCapabilityMatrix(template = false) {
  const { workbook, sheet } = createWorkbook(
    "能力矩阵",
    "EC101 平台活动闭环能力矩阵",
    template
      ? "模板：每个活动一行；总结果必须基于四份支撑材料形成。"
      : `${result.platform}-${result.dealer}｜整体结论：${result.overall_conclusion}`,
  );
  const headers = [
    "平台",
    "经销商",
    "验证对象",
    "活动识别",
    "规则重算",
    "实际权益核对",
    "销售交叉验证",
    "履约闭环",
    "费用重算",
    "支付风险",
    "最终状态",
    "核心依据",
  ];
  const reduction = result.activities["满减"];
  const gift = result.activities["满赠"];
  const rows = template
    ? []
    : result.report?.capability_rows
      ? matrixRows(headers, result.report.capability_rows)
      : [
        [result.platform, result.dealer, "整体", "支持", "支持", "支持", "支持", "条件支持", "条件支持", `${reduction.payment_risk_count + gift.payment_risk_count}单`, result.overall_conclusion, result.overall_basis],
        [result.platform, result.dealer, "满减", "支持", "支持", `${reduction.benefit_matched_order_count}/${reduction.eligible_order_count}`, `${reduction.sales_matched_order_count}/${reduction.eligible_order_count}`, "已完成口径支持", "优惠315元可重算；最终归属待确认", `${reduction.payment_risk_count}单`, reduction.conclusion, `活动期内已完成${reduction.eligible_order_count}单，理论与实际优惠均为${reduction.actual_benefit_total}元`],
        [result.platform, result.dealer, "满赠", "支持", "支持", `${gift.gift_result_matched_order_count}/${gift.eligible_order_count}`, `${gift.sales_matched_order_count}/${gift.eligible_order_count}`, `实发${gift.issued_order_count}单/${gift.issued_gift_quantity}个`, "缺赠品单价", `${gift.payment_risk_count}单`, gift.conclusion, `活动${gift.eligible_order_count}单，库存不足未发${gift.not_issued_order_count}单`],
      ];
  writeTable(sheet, 6, headers, rows, { wrap: true, widths: [12, 12, 14, 13, 13, 16, 16, 18, 24, 14, 14, 48] });
  if (!template) {
    sheet.getRange("K7:K9").format.font = { name: FONT, size: 10, bold: true, color: COLORS.navy };
    addSourceNote(sheet, 11, result.report?.source_note ?? `数据源：${result.source_root}`);
  }
  return workbook;
}

function addDetailSheet(workbook, name, title, details, headers) {
  const sheet = workbook.worksheets.add(name);
  sheet.showGridLines = false;
  sheet.getRange("A2").values = [[title]];
  sheet.getRange("A2").format.font = { name: FONT, size: 14, bold: true, color: COLORS.navy };
  writeTable(sheet, 4, headers, matrixRows(headers, details), {
    wrap: true,
    widths: headers.map((header) => (header.includes("政策") ? 50 : header.includes("订单编号") ? 23 : header.includes("客户") ? 22 : 16)),
  });
  if (details.length && (headers[0].includes("单号") || headers[0].includes("订单编号"))) {
    sheet.getRange(`A5:A${4 + details.length}`).format.numberFormat = "@";
  }
}

function buildValidationReport(template = false) {
  const { workbook, sheet } = createWorkbook(
    "验证摘要",
    "单平台数据闭环验证报告",
    template
      ? "模板：记录输入、关联、重算、实际权益、销售、履约和费用证据。"
      : result.report?.validation_subtitle ?? `${result.platform}-${result.dealer}｜订单状态=已完成为发放条件；支付状态仅作风险提示。`,
  );
  const headers = ["活动", "活动期间", "已完成活动单数", "理论权益", "实际权益", "权益一致", "销售匹配", "支付风险", "活动执行结论", "费用闭环说明"];
  const reduction = result.activities["满减"];
  const gift = result.activities["满赠"];
  const rows = template
    ? []
    : result.report?.validation_summary_rows
      ? matrixRows(headers, result.report.validation_summary_rows)
      : [
        ["满减", reduction.activity_period, reduction.eligible_order_count, `${reduction.theoretical_benefit_total}元`, `${reduction.actual_benefit_total}元`, `${reduction.benefit_matched_order_count}/${reduction.eligible_order_count}`, `${reduction.sales_matched_order_count}/${reduction.eligible_order_count}`, reduction.payment_risk_count, reduction.conclusion, "优惠金额可重算；售后终态和费用承担方待确认"],
        ["满赠", gift.activity_period, gift.eligible_order_count, `${gift.eligible_order_count}个`, `${gift.issued_gift_quantity}个`, `${gift.gift_result_matched_order_count}/${gift.eligible_order_count}`, `${gift.sales_matched_order_count}/${gift.eligible_order_count}`, gift.payment_risk_count, gift.conclusion, "实物数量可核验；库存不足2单；赠品单价和费用承担方待确认"],
      ];
  writeTable(sheet, 6, headers, rows, { wrap: true, widths: [12, 36, 18, 16, 16, 15, 15, 14, 16, 46] });
  if (!template) {
    addSourceNote(sheet, 10, result.report?.source_note ?? `数据源：${result.source_root}`);
    if (result.report?.detail_sheets) {
      for (const detail of result.report.detail_sheets) {
        addDetailSheet(workbook, detail.name, detail.title, detail.rows, detail.headers);
      }
    } else {
      addDetailSheet(workbook, "满减逐单", "满减逐单核验", reduction.details, ["订单编号", "下单时间", "客户名称", "订单状态", "支付方式", "支付状态", "参与商品金额", "理论优惠金额", "实际优惠金额", "权益一致", "销售明细匹配", "支付风险", "活动政策"]);
      addDetailSheet(workbook, "满赠逐单", "满赠逐单核验", gift.details, ["订单编号", "下单时间", "客户名称", "订单状态", "支付方式", "支付状态", "活动侧雪碧金额", "订单侧雪碧金额", "组合金额一致", "理论赠品数量", "实际赠品数量", "库存不足标记", "赠品结果一致", "销售明细匹配", "支付风险", "活动政策"]);
    }
  }
  return workbook;
}

function buildQuestions(template = false) {
  const { workbook, sheet } = createWorkbook(
    "待确认事项",
    "业务规则与待确认事项",
    template ? "模板：记录数据无法回答、且需要业务或平台确认的规则。" : `${result.platform}-${result.dealer}｜仅列证据不足事项，不替业务作结论。`,
  );
  const headers = ["ID", "分类", "级别", "问题", "影响", "责任方", "状态"];
  const rows = template ? [] : matrixRows(headers, result.issues);
  writeTable(sheet, 6, headers, rows, { wrap: true, widths: [10, 14, 10, 42, 44, 18, 24] });
  if (!template && rows.length) {
    sheet.getRange(`B7:B${6 + rows.length}`).conditionalFormats.add("containsText", { text: "风险提示", format: { fill: COLORS.amber } });
    sheet.getRange(`B7:B${6 + rows.length}`).conditionalFormats.add("containsText", { text: "Gap", format: { fill: COLORS.red } });
  }
  return workbook;
}

function buildGapList(template = false) {
  const { workbook, sheet } = createWorkbook(
    "Gap清单",
    "最小数据要求与 Gap 清单",
    template ? "模板：逐项对照 EC101 最小数据要求与平台现状。" : `${result.platform}-${result.dealer}｜缺口不等同于执行失败；说明其对结论的具体影响。`,
  );
  const headers = ["模块", "最小数据要求", "平台现状", "是否可达", "级别", "对结论的影响", "建议动作"];
  const rows = template
    ? []
    : result.report?.gap_rows
      ? matrixRows(headers, result.report.gap_rows)
      : [
        ["活动执行", "订单与活动唯一关联", "活动明细订单号可直连订单编号", "可达", "P0", "支持逐单活动归因", "保持导出"],
        ["活动执行", "理论权益与实际权益", "满减20/20一致；满赠100/100结果可解释", "可达", "P0", "支持活动执行验证", "保持导出"],
        ["销售事实", "活动订单进入销售明细", "满减20/20；满赠100/100", "可达", "P0", "支持销售交叉验证", "保持订单号"],
        ["支付", "支付方式与支付状态", "已提供；货到付款未支付语义待解释", "条件可达", "P1", "不影响本次发放统计", "确认未支付是否仅指未在线支付"],
        ["履约售后", "已完成后的退款/退货终态", "未提供", "不可达", "P0", "最终费用只能条件闭环", "补充退款状态、退款金额、退货数量"],
        ["满赠费用", "赠品采购单价", "未提供", "不可达", "P0", "98个抱枕不能换算费用金额", "补充抱枕单位成本"],
        ["费用归属", "费用承担方", "未提供", "不可达", "P0", "不能证明由太古承担", "补充活动费用主体或审批依据"],
      ];
  writeTable(sheet, 6, headers, rows, { wrap: true, widths: [16, 28, 40, 16, 10, 42, 40] });
  return workbook;
}

function buildFieldMapping(template = false) {
  const { workbook, sheet } = createWorkbook(
    "字段映射",
    "EC101 标准字段映射表",
    template
      ? "模板：逐项展示经销商原始字段全集与 EC101 V1 标准字段全集；非 V1 原始字段也必须保留。"
      : `${result.platform}-${result.dealer}｜经销商原始字段全集 ∪ EC101 V1 标准字段全集；字段可达不等于平台能力结论。`,
  );
  const headers = [
    "模块",
    "来源文件",
    "经销商原始字段",
    "EC101标准字段",
    "字段关系",
    "来源类型",
    "重要度",
    "证据等级",
    "状态",
    "说明",
  ];
  const rows = template ? [] : matrixRows(headers, result.field_mappings);
  writeTable(sheet, 6, headers, rows, {
    wrap: true,
    widths: [16, 34, 28, 26, 16, 18, 10, 14, 18, 42],
  });
  return workbook;
}

const definitions = [
  ["EC101平台活动闭环能力矩阵.xlsx", buildCapabilityMatrix],
  ["单平台数据闭环验证报告.xlsx", buildValidationReport],
  ["业务规则与待确认事项.xlsx", buildQuestions],
  ["最小数据要求与Gap清单.xlsx", buildGapList],
  ["标准字段映射表.xlsx", buildFieldMapping],
];

async function exportWorkbook(workbook, destination, previewPath = null) {
  workbook.recalculate();
  const firstSheet = workbook.worksheets.getItemAt(0);
  const used = firstSheet.getUsedRange();
  const inspect = await workbook.inspect({
    kind: "table",
    sheetId: firstSheet.name,
    range: used?.address ?? "A1:L30",
    include: "values,formulas",
    tableMaxRows: 12,
    tableMaxCols: 12,
    maxChars: 5000,
  });
  console.log(inspect.ndjson);
  const errors = await workbook.inspect({
    kind: "match",
    searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!",
    options: { useRegex: true, maxResults: 100 },
    summary: `formula errors in ${path.basename(destination)}`,
  });
  console.log(errors.ndjson);
  if (previewPath) {
    const preview = await workbook.render(
      path.basename(destination) === "标准字段映射表.xlsx"
        ? { sheetName: firstSheet.name, range: "A1:J20", scale: 1, format: "png" }
        : { sheetName: firstSheet.name, autoCrop: "all", scale: 1, format: "png" },
    );
    await fs.writeFile(previewPath, new Uint8Array(await preview.arrayBuffer()));
    if (path.basename(destination) === "单平台数据闭环验证报告.xlsx" && result.report?.detail_sheets) {
      for (const detail of result.report.detail_sheets) {
        const detailPreview = await workbook.render({ sheetName: detail.name, autoCrop: "all", scale: 1, format: "png" });
        const detailPath = path.join(path.dirname(previewPath), `单平台数据闭环验证报告-${detail.name}.png`);
        await fs.writeFile(detailPath, new Uint8Array(await detailPreview.arrayBuffer()));
      }
    }
  }
  const output = await SpreadsheetFile.exportXlsx(workbook);
  await output.save(destination);
}

for (const [fileName, builder] of definitions) {
  await exportWorkbook(
    builder(false),
    path.join(outputDir, fileName),
    path.join(previewDir, `${fileName}.png`),
  );
  await exportWorkbook(builder(true), path.join(templateDir, fileName));
}

console.log(JSON.stringify({ outputDir, templateDir, files: definitions.map(([name]) => name) }, null, 2));
