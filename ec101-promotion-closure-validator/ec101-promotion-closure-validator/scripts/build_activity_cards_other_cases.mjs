import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const outputRoot = path.resolve(process.argv[2] ?? "outputs");
const FONT = "Arial";
const COLORS = { navy: "#1F4E78", lightBlue: "#EAF3F8", amber: "#FFF2CC", green: "#E2F0D9", border: "#B7C9D6", text: "#1F2937" };
const utc = (value) => new Date(`${value.replace(" ", "T")}Z`);

const packages = [
  {
    dealer: "顺英",
    platform: "快马",
    file: "活动任务卡_快马_顺英.xlsx",
    summary: "活动配置来源：满减.png、满赠1.png。满赠的本次样本仅覆盖活动期前段，不能替代完整活动期数据。",
    cards: [
      {
        id: "KM-SY-20260914-MJ-01", sheet: "满减任务卡", name: "可口满减", type: "组合促销－满减",
        start: utc("2026-09-14 20:13:00"), end: utc("2026-09-18 20:13:00"), source: "满减.png",
        rule: "可口品牌每满 300 元减 15 元", gate: "订单状态=已完成", sample: "2026-09-14 至 2026-09-16",
        rules: [
          ["优惠方式", "叠加优惠", "截图"], ["促销方式", "满一定金额立减", "截图"], ["活动门槛", "每满 300 元", "截图与案例配置"],
          ["权益", "立减 15 元", "截图与案例配置"], ["活动商品范围", "指定品牌：可口", "截图"], ["活动客户范围", "全部客户", "截图"],
          ["购买限制", "每用户限购 0 单（不限制）", "截图"], ["禁用对象", "无", "截图"], ["使用设备", "不限", "截图"],
          ["限制充值赠送客户", "关闭", "截图"], ["使用场景", "截图未见已选场景，待确认", "待确认"],
          ["允许与其他活动同时参与", "否", "截图"], ["允许使用优惠券", "是", "截图"], ["最少参与 SKU 数", "0（不限制）", "截图"], ["必买商品", "截图未完整展示，待确认", "待确认"],
        ],
        rows: [
          ["活动配置", "满减.png", "活动名称、规则、时间、品牌范围", "已提供", "核对截图与任务卡一致"],
          ["活动执行明细", "满减活动明细20260914_20260916132107.xls", "订单号、活动商品金额、实际优惠", "待质检", "当前样本仅至 9 月 16 日"],
          ["订单明细", "满减订单明细20260914-2026091613272066347.xls", "订单编号、下单时间、订单状态、支付状态、商品、金额", "待质检", "必须覆盖至 9 月 18 日 20:13"],
          ["销售明细", "满减销售明细20260914-20260916132549.xls", "单据编号、销售商品、数量、金额", "待质检", "与订单明细按订单号交叉核验"],
          ["客户/商品资料", "User、Product 导出文件", "客户编号、品牌、商品编号", "待质检", "验证客户与品牌范围"],
          ["售后/费用", "退款退货、成本、费用承担方", "最终履约与费用归属", "待补充", "缺失时只能条件支持"],
        ],
      },
      {
        id: "KM-SY-20260821-MZ-01", sheet: "满赠任务卡", name: "雪碧抱枕", type: "组合促销－满赠",
        start: utc("2026-08-21 15:54:00"), end: utc("2027-08-31 15:54:00"), source: "满赠1.png",
        rule: "雪碧指定商品满 100 元赠抱枕 1 个", gate: "订单状态=已完成", sample: "2026-08-21 至 2026-08-31",
        rules: [
          ["优惠方式", "阶梯优惠", "截图"], ["促销方式", "满一定金额立赠", "截图"], ["活动门槛", "金额满 100 元", "截图"],
          ["权益", "赠（雪碧赠品）抱枕一个 1 件", "截图"], ["赠品商品编号", "0877", "截图与案例配置"], ["活动商品范围", "指定商品；完整 SKU 清单未提供", "截图与案例配置"],
          ["活动客户范围", "全部客户", "截图"], ["购买限制", "每用户限购 0 单（不限制）", "截图"], ["禁用对象", "无", "截图"],
          ["使用设备", "不限", "截图"], ["限制充值赠送客户", "关闭", "截图"], ["使用场景", "截图未见已选场景，待确认", "待确认"],
          ["允许与其他活动同时参与", "否", "截图"], ["允许使用优惠券", "是", "截图"], ["最少参与 SKU 数", "0（不限制）", "截图"], ["必买商品", "截图未完整展示，待确认", "待确认"],
        ],
        rows: [
          ["活动配置", "满赠1.png", "活动名称、规则、时间、赠品", "已提供", "完整指定商品清单待补充"],
          ["活动执行明细", "满赠活动明细_20260821-20260831.xls", "订单号、活动商品金额、活动政策", "待质检", "当前样本仅为活动期前段"],
          ["订单明细", "满赠订单明细_20260821-20260831.xls", "订单编号、下单时间、订单状态、赠品 SKU", "待质检", "完整活动期至 2027-08-31"],
          ["销售明细", "满赠销售明细_20260821-20260831.xls", "单据编号、赠品 SKU、数量、库存标记", "待质检", "与订单明细按订单号交叉核验"],
          ["客户/商品资料", "User、Product 导出文件", "客户编号、商品编号、品牌、规格", "待质检", "验证指定商品范围"],
          ["售后/费用", "退款退货、赠品冲销、成本、费用承担方", "最终履约与费用归属", "待补充", "缺失时只能条件支持"],
        ],
      },
    ],
  },
  {
    dealer: "羿柏",
    platform: "舟谱",
    file: "活动任务卡_舟谱_羿柏.xlsx",
    summary: "活动配置来源：满减方案.png、满赠方案1.png、满赠方案2.png、满赠方案3.png。下单返券当前数据仅覆盖局部窗口。",
    cards: [
      {
        id: "ZP-YB-20260826-QUAN-01", sheet: "下单返券任务卡", name: "可口可乐产品满288返15元券", type: "下单返券",
        start: utc("2026-08-26 00:00:00"), end: utc("2026-09-26 23:59:59"), source: "满减方案.png",
        rule: "可口可乐产品金额满 288 元返 15 元券，每客户每日限 1 次", gate: "订单状态=已完成（待业务确认）", sample: "2026-08-28 至 2026-09-10",
        rules: [
          ["优惠券名称", "可口可乐产品288返15元券", "截图"], ["优惠券类型", "下单返券", "截图"], ["活动门槛", "可口可乐产品金额满 288 元", "截图与案例配置"],
          ["权益", "返 15 元抵扣券", "截图与案例配置"], ["可领取期间", "2026-08-26 至 2026-09-26", "截图"], ["券有效期", "永久有效", "截图"],
          ["发放数量", "333 张", "截图"], ["活动客户范围", "全部客户", "截图"], ["客户限制", "每人每日限领 1 次", "截图"],
          ["支付限制", "不限支付方式可享", "截图"], ["红包叠加", "可叠加红包使用", "截图"], ["活动商品范围", "可口可乐产品；完整 SKU 清单待确认", "案例配置"],
          ["返券归因", "活动明细无触发订单编号，不能逐单归因", "已知数据限制"],
        ],
        rows: [
          ["活动配置", "满减方案.png", "规则、时间、券额、限领条件", "已提供", "核对截图与任务卡一致"],
          ["活动执行明细", "舟谱-羿柏-活动明细-20260826-20260908.xls", "领取客户、领取/使用数量、关联使用单据", "待质检", "无触发订单号，不能做逐单发券归因"],
          ["订单明细", "销售订单明细表导出 0828-0910", "订单号、下单时间、状态、品牌金额", "待质检", "缺 8 月 26-27 日及 9 月 11-26 日"],
          ["销售明细", "舟谱-羿柏-销售明细-20260812-20260910.xlsx", "订单号、销售商品、数量、金额", "待质检", "当前样本仅至 9 月 10 日"],
          ["客户/商品资料", "客户档案.xlsx、商品档案.xlsx", "客户编号、商品编号、品牌", "待质检", "验证客户与商品范围"],
          ["售后/费用", "退款退货、券核销终态、费用承担方", "最终履约与费用归属", "待补充", "缺失时不能形成费用闭环"],
        ],
      },
      {
        id: "ZP-YB-20260819-MZ-01", sheet: "满赠任务卡", name: "雪碧系列满100元送抱枕", type: "满赠",
        start: utc("2026-08-19 12:29:37"), end: utc("2026-08-26 12:29:40"), source: "满赠方案1.png、满赠方案2.png、满赠方案3.png",
        rule: "雪碧指定商品满 100 元赠（赠品）雪碧抱枕 1 个", gate: "订单状态=已完成", sample: "2026-08-19 至 2026-08-26",
        rules: [
          ["活动类型", "满 100 元赠", "截图"], ["活动门槛", "金额满 100 元", "截图与案例配置"], ["权益", "固定赠品：（赠品）雪碧抱枕 1 个", "截图"],
          ["活动期间", "2026-08-19 12:29:37 至 2026-08-26 12:29:40", "截图"], ["活动商品范围", "指定商品；截图展示部分雪碧 SKU，完整清单未导出", "截图与案例配置"],
          ["活动客户范围", "全部客户", "截图"], ["购买限制", "单客最多下单 1 次", "截图与案例配置"], ["活动总量上限", "100 个赠品", "案例配置"],
          ["支付限制", "不限支付方式可享", "截图"], ["优惠券/红包叠加", "截图均未选；系统优先级待确认", "截图与案例配置"], ["下单门槛", "活动商品计入下单门槛", "截图"],
          ["赠品重复添加", "不允许", "截图"],
        ],
        rows: [
          ["活动配置", "满赠方案1/2/3.png", "规则、时间、商品范围、赠品、限购", "已提供", "完整活动商品 SKU 清单待补充"],
          ["订单明细", "满赠订单明细20260819-20260826.xlsx（分段）", "订单号、下单时间、状态、雪碧金额、抱枕行", "待质检", "去重后完整覆盖活动期"],
          ["销售明细", "满赠销售明细20260819-20260826.xlsx", "订单号、赠品、数量、金额", "待质检", "与订单明细按订单号交叉核验"],
          ["活动执行明细", "未提供", "订单－活动关联、实际权益", "Gap", "以订单和销售明细重构，不能替代活动归因"],
          ["客户/商品资料", "满赠/客户档案.xlsx、满赠/商品档案.xlsx", "客户编号、商品编号、商品范围", "待质检", "验证客户与指定商品范围"],
          ["售后/费用", "退款退货、赠品冲销、成本、费用承担方", "最终履约与费用归属", "待补充", "缺失时只能条件支持"],
        ],
      },
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
  const head = sheet.getRangeByIndexes(start, 0, 1, headers.length);
  head.values = [headers];
  head.format = { fill: COLORS.navy, font: { name: FONT, size: 10, bold: true, color: "#FFFFFF" }, horizontalAlignment: "center", verticalAlignment: "center", wrapText: true, borders: { preset: "all", style: "thin", color: "#FFFFFF" } };
  head.format.rowHeight = 26;
  const data = sheet.getRangeByIndexes(start + 1, 0, rows.length, headers.length);
  data.values = rows;
  data.format = { font: { name: FONT, size: 10, color: COLORS.text }, verticalAlignment: "center", wrapText: true, borders: { preset: "inside", style: "thin", color: COLORS.border } };
  data.format.autofitRows();
  widths.forEach((width, index) => { sheet.getRangeByIndexes(start, index, rows.length + 1, 1).format.columnWidth = width; });
}

function section(sheet, row, label) {
  const range = sheet.getRange(`A${row}:D${row}`);
  range.values = [[label, "", "", ""]];
  range.format = { fill: COLORS.lightBlue, font: { name: FONT, size: 10, bold: true, color: COLORS.navy }, borders: { preset: "outside", style: "thin", color: COLORS.border } };
}

function buildPackage(definition) {
  const workbook = Workbook.create();
  const overview = workbook.worksheets.add("任务卡总览");
  applyTitle(overview, "EC101 活动任务卡", `${definition.platform}－${definition.dealer}｜${definition.summary}`);
  const summaryRows = definition.cards.map((card) => [card.id, definition.dealer, definition.platform, card.name, card.type, card.start, card.rule, `${card.start.toISOString().slice(0, 10)} 至 ${card.end.toISOString().slice(0, 10)}`, "待收数质检"]);
  writeTable(overview, 6, ["验证编号", "经销商", "平台", "活动名称", "活动类型", "活动期间", "核心规则", "订单应导期间", "当前状态"], summaryRows, [28, 14, 12, 22, 18, 28, 34, 30, 16]);
  overview.getRange(`F7:F${6 + summaryRows.length}`).format.numberFormat = "yyyy-mm-dd hh:mm";
  overview.getRange(`I7:I${6 + summaryRows.length}`).format = { fill: COLORS.amber, font: { name: FONT, size: 10, bold: true, color: COLORS.text }, horizontalAlignment: "center" };
  overview.getRange(`A${9 + summaryRows.length}`).values = [["发放条件以任务卡为准；支付状态仅作风险提示，除非业务规则另有明确规定。"]];
  overview.getRange(`A${9 + summaryRows.length}`).format = { font: { name: FONT, size: 10, italic: true, color: "#5B6573" } };
  overview.freezePanes.freezeRows(6);

  definition.cards.forEach((card) => {
    const sheet = workbook.worksheets.add(card.sheet);
    applyTitle(sheet, `${card.name}活动任务卡`, `验证编号：${card.id}｜活动配置来源：${card.source}`);
    section(sheet, 6, "任务基本信息");
    const basicRows = [
      ["验证编号", card.id, "来源", "EC101 生成"], ["经销商", definition.dealer, "平台", definition.platform],
      ["活动名称", card.name, "活动类型", card.type], ["活动编号", "未在现有证据中展示", "活动状态", "未在现有证据中展示"],
      ["活动开始时间", card.start, "活动结束时间", card.end], ["订单应导范围", card.start, "至", card.end],
      ["发放条件", card.gate, "支付状态", "仅作风险提示"], ["当前样本范围", card.sample, "当前任务状态", "待收数质检"],
    ];
    writeTable(sheet, 7, ["字段", "内容", "字段", "内容"], basicRows, [24, 44, 24, 44]);
    sheet.getRange("B12:B13").format.numberFormat = "yyyy-mm-dd hh:mm";
    sheet.getRange("D12:D13").format.numberFormat = "yyyy-mm-dd hh:mm";
    sheet.getRange("D15").format = { fill: COLORS.amber, font: { name: FONT, size: 10, bold: true, color: COLORS.text }, horizontalAlignment: "center" };

    section(sheet, 17, "活动配置与规则");
    const ruleRows = card.rules.map(([field, value, evidence]) => [field, value, evidence, evidence.includes("待") ? "待确认" : "已记录"]);
    writeTable(sheet, 18, ["配置字段", "已记录值", "证据", "状态"], ruleRows, [24, 66, 24, 16]);
    const ruleStart = 19;
    const ruleEnd = 18 + ruleRows.length;
    sheet.getRange(`D${ruleStart}:D${ruleEnd}`).conditionalFormats.add("containsText", { text: "待确认", format: { fill: COLORS.amber } });

    const collectionStart = ruleEnd + 3;
    section(sheet, collectionStart, "收数与输入数据质检");
    writeTable(sheet, collectionStart + 1, ["资料类型", "取数路径/证据", "关键检查字段", "状态", "质检要求"], card.rows, [18, 40, 44, 16, 44]);
    const statusStart = collectionStart + 2;
    const statusEnd = statusStart + card.rows.length - 1;
    sheet.getRange(`D${statusStart}:D${statusEnd}`).conditionalFormats.add("containsText", { text: "待", format: { fill: COLORS.amber } });
    sheet.getRange(`D${statusStart}:D${statusEnd}`).conditionalFormats.add("containsText", { text: "已提供", format: { fill: COLORS.green } });
    sheet.freezePanes.freezeRows(6);
  });
  return workbook;
}

for (const definition of packages) {
  const workbook = buildPackage(definition);
  workbook.recalculate();
  const inspection = await workbook.inspect({ kind: "table", range: "任务卡总览!A2:I11", include: "values,formulas", tableMaxRows: 12, tableMaxCols: 10 });
  console.log(inspection.ndjson);
  const errors = await workbook.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!", options: { useRegex: true, maxResults: 100 }, summary: `${definition.dealer} formula error scan` });
  console.log(errors.ndjson);
  const folder = path.join(outputRoot, definition.dealer);
  await fs.mkdir(folder, { recursive: true });
  const outputPath = path.join(folder, definition.file);
  const output = await SpreadsheetFile.exportXlsx(workbook);
  await output.save(outputPath);
  const preview = await workbook.render({ sheetName: "任务卡总览", autoCrop: "all", scale: 1.25, format: "png" });
  const previewPath = outputPath.replace(/\.xlsx$/i, ".preview.png");
  await fs.writeFile(previewPath, new Uint8Array(await preview.arrayBuffer()));
  console.log(JSON.stringify({ outputPath, previewPath }));
}
