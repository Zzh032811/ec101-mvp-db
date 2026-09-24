---
name: ec101-promotion-closure-validator
description: Use when validating EC101 dealer promotion data closure from activity task cards, platform extraction guidance, and customer, product, order, sales, activity-detail, and activity-configuration files.
---

# EC101 Promotion Closure Validator

## Purpose

Turn a verified activity task package into an auditable promotion conclusion. Keep platform facts, calculated results, and human-confirmed rules separate. Never infer a fee conclusion from field availability alone.

## Control inputs before source data

Every new activity verification starts from these control inputs before the ordinary source files.

1. **活动任务卡** is the single verification baseline. It defines the case ID, dealer, platform, activity name/type/ID when available, activity period, key rule, required order-data period, distribution gate, after-sales observation period, configuration evidence, and open business questions.
2. **平台操作手册** is the extraction knowledge base. Use it when locating or re-exporting source data. It records the platform/module navigation, export date field, filters, export limits, known data limitations, and evidence location. It does not replace the task card or source files.

Do not place or read platform account credentials in either document. A task card may contain `待确认` values. Preserve them as open items rather than guessing.

For an existing legacy case without an activity task card, its documented case configuration and platform rule may be used as a temporary baseline. Create a task card before the next source-data refresh.

## Verified scope and platform routing

- For `快马 × 顺英 × 满减/满赠`, read [platform-rules/快马.md](platform-rules/快马.md) and run `scripts/validate_case.py`.
- For `快马 × 兴路强 × 满减/满赠`, read [platform-rules/快马.md](platform-rules/快马.md) and run `scripts/validate_kuaima_xingluqiang_case.py`.
- For `财经云 × 勤进 × 满减/满赠`, read [platform-rules/财经云.md](platform-rules/财经云.md) and run `scripts/validate_caijingyun_case.py`.
- For `舟谱 × 羿柏 × 下单返券/满赠`, read [platform-rules/舟谱.md](platform-rules/舟谱.md) and run `scripts/validate_zhoupu_case.py`.
- Do not reuse one platform's field meanings or status assumptions for another platform. Any new platform requires its own evidence-backed platform rule before it is described as supported.

## Required flow

0. Read the activity task card. Confirm the validation object, rules, activity period, required data period, and configuration evidence.
0.5. Run the input-data quality gate in [references/输入数据质检规则.md](references/输入数据质检规则.md). Read [references/平台操作手册标准.md](references/平台操作手册标准.md) only when source data must be located, re-exported, or its extraction method needs checking.
1. Identify the six input categories and preserve their original files.
2. Map source fields to the Chinese dictionary in [references/EC101标准字段字典V1.md](references/EC101标准字段字典V1.md).
3. Check customer, order, SKU, activity, sales, fulfillment, and fee relationships.
4. Structure the activity using [references/活动规则标准.md](references/活动规则标准.md).
5. Recalculate theoretical entitlement, then compare actual entitlement and sales evidence.
6. Apply [references/验证规则.md](references/验证规则.md) and classify unresolved items with [references/问题分类与风险等级.md](references/问题分类与风险等级.md).
7. Assign only a conclusion allowed by [references/结论判定规则.md](references/结论判定规则.md).
8. Output one total result plus four evidence workbooks. Never omit the total capability matrix.

### Input-data quality gate

Check the task card against actual input files before any eligibility or fee calculation:

- required files exist, open successfully, and contain data rows;
- actual minimum/maximum business time covers the task card's required period;
- dealer and platform match the task card where evidence is available;
- activity configuration matches the task card by activity ID, or by activity name, type, and period when no ID is exported;
- order, sales, and activity files carry usable join keys and unambiguous source versions;
- the task card's required status fields and configuration evidence are present, or explicitly classified as a Gap.

Record the result as `通过`、`条件通过`、or `阻断` in the run evidence. A P0 mismatch, empty critical export, wrong activity configuration, or incomplete required period is `阻断`: do not state a complete activity or fee conclusion. Output the missing-data list and mark affected conclusions `未验证`; do not reinterpret missing coverage as zero participation.

## Complete field mapping contract

- The mapping population is always: **经销商各模块原始字段全集 ∪ EC101 V1 标准字段全集**.
- Include every source column from customer, product, order, sales, activity execution, and any other supplied module, even when it is outside V1.
- Mark a source-only column as `非V1字段` and retain its original name and source file; never drop it from the mapping report.
- Add every V1 standard field even when the dealer has no matching source column; use original field `—` and status `Gap`, `人工确认`, or `可计算` as appropriate.
- Do not produce a selected or core-field-only mapping unless the user explicitly requests an abbreviated view in addition to the complete table.

## Output organization

- Create one independent output folder for every dealer: `outputs/<经销商名称>/`.
- Put that dealer's `run.json` and complete 1+4 workbooks in the same folder.
- Keep each activity's task card and original input package identifiable by its verification ID. A dealer with multiple activities must not mix one activity's screenshots or source exports into another activity's validation package.
- Different dealers' outputs must never be mixed: **不同经销商的输出不得混放**.
- Reusable blank templates remain in `templates/`; they are shared resources and do not belong to any dealer output folder.
- If the same dealer is rerun, update only that dealer's folder unless the user requests a dated snapshot.

## 异常订单证据输出

- 能力矩阵、验证摘要或问题清单中出现的每一项异常数量，必须在《单平台数据闭环验证报告》中有对应的“异常订单”明细页逐单支撑。
- 异常订单明细至少展示：订单编号、业务时间、客户、订单状态、支付状态或支付风险、活动资格/金额证据、理论权益、实际权益、销售明细匹配情况、异常类型与异常原因。
- 不得只输出异常数量或订单号；未赠、异常赠送、活动前非关联赠品等均须完整列示。

## Non-negotiable cross-platform rules

- `2026-09-14 20:13:00` is only the supplied start time for `快马 × 顺英 × 可口可乐每满300减15`; other platforms must use their own activity evidence and must not inherit this time.
- `订单状态=已完成` is the distribution gate when order status is supplied. If a platform provides only sales-outbound facts, report the missing order status as a P0 Gap and do not silently treat outbound rows as completed orders.
- Payment status is a risk dimension. `货到付款 + 未支付 + 已完成` remains in valid promotion totals.
- A sales row is a gift only when the platform's activity marker and gift-product evidence both support that classification. Ordinary paid sales of the same product must be excluded.
- Source data ending before the activity start is `未验证`, not zero participation and not support.
- Missing refund finality, gift unit cost, or fee owner must be reported, not guessed.
- The total result is evidence-derived: raw files → mapping → relationships → recalculation → gaps/confirmations → conclusion.

## Run

From the skill directory:

```bash
python3 scripts/validate_case.py \
  --config cases/快马-顺英/案例配置.json

node scripts/build_reports.mjs \
  outputs/顺英/run.json \
  outputs/顺英

python3 scripts/validate_kuaima_xingluqiang_case.py \
  --config cases/快马-兴路强/案例配置.json

node scripts/build_reports.mjs \
  outputs/兴路强/run.json \
  outputs/兴路强

python3 scripts/validate_caijingyun_case.py \
  --config cases/财经云-勤进/案例配置.json

node scripts/build_reports.mjs \
  outputs/勤进/run.json \
  outputs/勤进

python3 scripts/validate_zhoupu_case.py \
  --config cases/舟谱-羿柏/案例配置.json

node scripts/build_reports.mjs \
  outputs/羿柏/run.json \
  outputs/羿柏
```

Use a Python environment with `pandas`, `openpyxl`, `xlrd`, `beautifulsoup4`, and `lxml`. The report builder uses the Codex bundled `@oai/artifact-tool` runtime.

## Stop conditions

Stop and request business confirmation only when a P0 ambiguity would change activity attribution, entitlement, final fulfillment, or fee ownership. The Phase 0.5 `阻断` result also stops substantive verification until the correct data package is supplied. Continue through P1/P2 gaps and risk notices while preserving them in the outputs.
