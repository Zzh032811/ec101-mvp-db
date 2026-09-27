import fs from "node:fs/promises";
import { Workbook, SpreadsheetFile } from "@oai/artifact-tool";

const outputDir = "/Users/18328618408163.com/Documents/GitHub/ec101-mvp-db/outputs/01a0dca2-4fc7-7773-9b04-f6de9acdb502";
const outputPath = `${outputDir}/EC101数据底座与费用平台路线图.xlsx`;

const workbook = Workbook.create();
const sheet = workbook.worksheets.add("路线图");
sheet.showGridLines = false;
sheet.tabColor = "#1F4E78";

const navy = "#1F4E78";
const blue = "#5B9BD5";
const green = "#70AD47";
const amber = "#ED7D31";
const purple = "#8064A2";
const paleBlue = "#D9EAF7";
const paleGreen = "#E2F0D9";
const paleAmber = "#FCE4D6";
const palePurple = "#E4DFEC";
const border = "#D9E2F3";

sheet.mergeCells("A2:O2");
sheet.getRange("A2").values = [["EC101 数据底座与费用平台路线图"]];
sheet.getRange("A2").format = {
  fill: "#FFFFFF",
  font: { name: "Aptos", size: 16, bold: true, color: navy },
  horizontalAlignment: "left",
  verticalAlignment: "center"
};
sheet.getRange("A3:O3").merge();
sheet.getRange("A3").values = [["项目目标：费用平台 V1 于 2026 年 10 月 24 日完成；2026 年 10 月 19 日至 24 日仅用于调整、验收与问题修复。"]];
sheet.getRange("A3").format = {
  font: { name: "Aptos", size: 10, italic: true, color: "#666666" },
  verticalAlignment: "center"
};

sheet.getRange("A5:D5").values = [["状态图例", "已完成", "进行中", "计划 / 调整预留"]];
sheet.getRange("A5:D5").format = { font: { name: "Aptos", size: 10, bold: true }, verticalAlignment: "center" };
sheet.getRange("B5").format.fill = green;
sheet.getRange("C5").format.fill = amber;
sheet.getRange("D5").format.fill = purple;
sheet.getRange("B5:D5").format.font = { name: "Aptos", size: 10, bold: true, color: "#FFFFFF" };

const headers = [[
  "工作流", "任务", "责任建议", "开始", "完成", "状态", "关键交付物",
  "09/02", "09/07", "09/14", "09/21", "09/28", "10/05", "10/12", "10/19"
]];
sheet.getRange("A7:O7").values = headers;
sheet.getRange("A7:O7").format = {
  fill: navy,
  font: { name: "Aptos", size: 10, bold: true, color: "#FFFFFF" },
  horizontalAlignment: "center",
  verticalAlignment: "center",
  wrapText: true,
  borders: { preset: "all", style: "thin", color: "#FFFFFF" }
};

const tasks = [
  ["数据底座", "业务梳理与数据准入", "项目 / 业务 / 数据", new Date("2026-09-02"), new Date("2026-09-11"), "已完成", "活动规则、数据源与准入口径"],
  ["数据底座", "多平台活动闭环验证", "数据 / 平台", new Date("2026-09-12"), new Date("2026-09-18"), "已完成", "快马、舟谱验证；财经云延后"],
  ["数据底座", "双平台 MVP 共库与核算", "数据 / 技术", new Date("2026-09-19"), new Date("2026-09-24"), "已完成", "双平台 CORE、RESULT、血缘与核验"],
  ["业务闭环", "关键差异与数据缺口确认", "业务 / 平台", new Date("2026-09-25"), new Date("2026-10-02"), "进行中", "35 单满赠、45 元返券、576 单 XD"],
  ["产品设计", "费用平台 V1 范围、原型与接口口径", "产品 / 业务 / 技术", new Date("2026-09-25"), new Date("2026-10-02"), "计划", "总览、台账、订单证据、异常、结算批次"],
  ["服务层", "MySQL 迁移与后端查询接口", "技术", new Date("2026-10-05"), new Date("2026-10-09"), "计划", "生产库、只读 API、权限与审计基础"],
  ["费用平台 V1", "真实数据展示页面", "前端 / 后端", new Date("2026-10-05"), new Date("2026-10-16"), "计划", "经销商总览、活动台账、订单证据"],
  ["费用平台 V1", "异常处理与结算批次", "前端 / 后端 / 业务", new Date("2026-10-12"), new Date("2026-10-16"), "计划", "处理留痕、结算清单、重复控制"],
  ["验收", "联调、UAT 与使用培训", "业务 / 技术", new Date("2026-10-12"), new Date("2026-10-16"), "计划", "真实案例演示、UAT 问题清单"],
  ["调整预留", "修复、口径调整与上线验收", "全体", new Date("2026-10-19"), new Date("2026-10-24"), "调整预留", "只处理已发现问题，不新增范围"]
];

const startRow = 8;
const weeks = [
  new Date("2026-09-02"), new Date("2026-09-07"), new Date("2026-09-14"), new Date("2026-09-21"),
  new Date("2026-09-28"), new Date("2026-10-05"), new Date("2026-10-12"), new Date("2026-10-19")
];
const fillForStatus = { "已完成": green, "进行中": amber, "计划": blue, "调整预留": purple };
const paleForStatus = { "已完成": paleGreen, "进行中": paleAmber, "计划": paleBlue, "调整预留": palePurple };

const formatDate = (date) => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
const values = tasks.map(([stream, task, owner, start, end, status, deliverable]) => [stream, task, owner, start, end, status, deliverable, ...Array(8).fill("")]);
sheet.getRange(`A${startRow}:O${startRow + tasks.length - 1}`).values = values;
sheet.getRange(`D${startRow}:E${startRow + tasks.length - 1}`).format.numberFormat = "yyyy-mm-dd";
sheet.getRange(`A${startRow}:O${startRow + tasks.length - 1}`).format = {
  font: { name: "Aptos", size: 10, color: "#1F1F1F" },
  verticalAlignment: "center",
  borders: { preset: "all", style: "thin", color: border }
};
sheet.getRange(`A${startRow}:G${startRow + tasks.length - 1}`).format.wrapText = true;

tasks.forEach(([, task, , start, end, status], index) => {
  const row = startRow + index;
  const activeStartIndex = weeks.findIndex((weekStart) => {
    const weekEnd = new Date(weekStart);
    weekEnd.setDate(weekEnd.getDate() + 6);
    return start <= weekEnd;
  });
  sheet.getRange(`A${row}:G${row}`).format.fill = paleForStatus[status];
  sheet.getRange(`F${row}`).format.font = { name: "Aptos", size: 10, bold: true, color: "#FFFFFF" };
  sheet.getRange(`F${row}`).format.fill = fillForStatus[status];
  weeks.forEach((weekStart, weekIndex) => {
    const weekEnd = new Date(weekStart);
    weekEnd.setDate(weekEnd.getDate() + 6);
    if (start <= weekEnd && end >= weekStart) {
      const col = String.fromCharCode("H".charCodeAt(0) + weekIndex);
      sheet.getRange(`${col}${row}`).values = [[weekIndex === activeStartIndex ? task : ""]];
      sheet.getRange(`${col}${row}`).format = {
        fill: fillForStatus[status],
        font: { name: "Aptos", size: 9, color: "#FFFFFF", bold: weekIndex === activeStartIndex },
        horizontalAlignment: "center",
        verticalAlignment: "center",
        wrapText: true,
        borders: { preset: "all", style: "thin", color: "#FFFFFF" }
      };
    }
  });
});

sheet.getRange("A20:D20").merge();
sheet.getRange("A20").values = [["关键完成条件"]];
sheet.getRange("A20").format = { fill: navy, font: { name: "Aptos", size: 11, bold: true, color: "#FFFFFF" }, verticalAlignment: "center" };
sheet.getRange("A21:D21").values = [["事项", "最晚完成", "责任建议", "未完成影响"]];
sheet.getRange("A21:D21").format = { fill: "#D9E2F3", font: { name: "Aptos", size: 10, bold: true, color: navy }, horizontalAlignment: "center", verticalAlignment: "center", borders: { preset: "all", style: "thin", color: border } };
const conditions = [
  ["满赠与返券差异确认、XD 文件补齐", new Date("2026-10-02"), "业务 / 舟谱", "真实费用无法形成稳定结论"],
  ["生产数据库、部署环境、接口访问方式确认", new Date("2026-10-02"), "技术", "前端只能演示，无法安全接真实数据"],
  ["费用平台页面与字段口径评审", new Date("2026-10-02"), "业务 / 产品", "开发期间反复返工"],
  ["UAT 账号、真实样例与验收人确认", new Date("2026-10-16"), "业务 / 技术", "无法在 10 月 24 日按时验收"]
];
sheet.getRange("A22:D25").values = conditions;
sheet.getRange("B22:B25").format.numberFormat = "yyyy-mm-dd";
sheet.getRange("A22:D25").format = { font: { name: "Aptos", size: 10 }, verticalAlignment: "center", wrapText: true, borders: { preset: "all", style: "thin", color: border } };

sheet.getRange("A27:O27").merge();
sheet.getRange("A27").values = [["说明：截至 2026-09-24，数据底座 MVP 已完成双平台共库与核心核算验证。10 月 19 日至 24 日为硬性调整窗口，禁止新增 KPI、分销分析、SAP 深度集成等范围。"]];
sheet.getRange("A27").format = { font: { name: "Aptos", size: 10, italic: true, color: "#666666" }, wrapText: true, verticalAlignment: "center" };

sheet.getRange("A:A").format.columnWidth = 15;
sheet.getRange("B:B").format.columnWidth = 27;
sheet.getRange("C:C").format.columnWidth = 18;
sheet.getRange("D:E").format.columnWidth = 12;
sheet.getRange("F:F").format.columnWidth = 12;
sheet.getRange("G:G").format.columnWidth = 32;
sheet.getRange("H:O").format.columnWidth = 12;
sheet.getRange("A2:O2").format.rowHeight = 27;
sheet.getRange("A7:O7").format.rowHeight = 30;
sheet.getRange(`A${startRow}:O${startRow + tasks.length - 1}`).format.rowHeight = 38;
sheet.getRange("A27:O27").format.rowHeight = 32;
sheet.freezePanes.freezeRows(7);
sheet.freezePanes.freezeColumns(2);

workbook.recalculate();
const keyCheck = await workbook.inspect({ kind: "table", range: "路线图!A2:O25", include: "values,formulas", tableMaxRows: 25, tableMaxCols: 15 });
console.log(keyCheck.ndjson);
const errors = await workbook.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!", options: { useRegex: true, maxResults: 50 } });
console.log(errors.ndjson);
const preview = await workbook.render({ sheetName: "路线图", range: "A1:O27", scale: 1.4 });
await fs.mkdir(outputDir, { recursive: true });
await fs.writeFile(`${outputDir}/EC101数据底座与费用平台路线图-preview.png`, Buffer.from(await preview.arrayBuffer()));
const file = await SpreadsheetFile.exportXlsx(workbook);
await file.save(outputPath);
console.log(`Saved ${outputPath}`);
