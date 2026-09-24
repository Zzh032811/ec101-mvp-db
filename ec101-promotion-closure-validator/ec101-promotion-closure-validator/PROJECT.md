# EC101 Promotion Closure Validator

## Purpose

Validate whether 快马-顺英 promotion data can support activity execution and fee closure, with auditable evidence and fixed Chinese business fields.

## Current capabilities

- Reads OOXML files carrying `.xls`, legacy BIFF `.xls`, and HTML tables carrying `.xls`.
- Recalculates the 快马-顺英 cases and validates the 财经云-勤进 sales-side evidence for full reduction and full gift.
- Applies activity time, completed-order, sales-match, entitlement-match, and payment-risk checks.
- Generates a stable `run.json` contract for the 1+4 reports.

## How to run

```bash
python3 scripts/validate_case.py --config cases/快马-顺英/案例配置.json
node scripts/build_reports.mjs outputs/顺英/run.json outputs/顺英
python3 -m unittest discover -s tests -v
```

## Main flow

Raw 快马 files → format-aware readers → normalized order/activity evidence → activity recalculation → sales and payment checks → `run.json` → 1+4 Excel reports.

Dealer outputs are isolated under `outputs/<经销商名称>/`. Shared blank workbooks remain under `templates/`.

## Important files

- `SKILL.md`: operating rules for future Codex runs; changing it affects judgment and output behavior.
- `scripts/validate_case.py`: owns the verified business calculation; changing it affects all totals.
- `cases/快马-顺英/案例配置.json`: owns activity times and thresholds; changing it changes eligibility.
- `platform-rules/快马.md`: owns platform-specific field and status interpretation.

## Current limits and next step

Implemented and verified for 快马-顺英 and 财经云-勤进. 财经云-勤进 currently lacks activity-period full-reduction data, order status, payment status, activity configuration, after-sales finality, gift unit cost, and fee owner; its requested two-activity scope therefore remains `未验证` overall.

## Latest milestone

- Added: runnable validator, format-aware readers, Chinese rule references, 快马 platform rules, case configuration, reusable templates, and the completed 1+4 reports.
- Added for 财经云-勤进: multi-row header parsing, platform-specific rules, independent case configuration, sales-side gift-bundle reconstruction, period-coverage checks, and a separate `outputs/勤进/` 1+4 delivery.
- Field mapping contract: every dealer report now uses `经销商各模块原始字段全集 ∪ EC101 V1 标准字段全集`; source-only fields are retained as `非V1字段`, while missing V1 fields remain visible as `Gap`、`人工确认` or `可计算` fields.
- Changed files: all files under this new standalone project only; original 快马-顺英 source files were not modified.
- Flow impact: the same command now recreates `run.json` and all five case reports from the original source folder under `outputs/顺英/`. Future dealers use their own `outputs/<经销商名称>/` folder.
- Verified: 20 automated tests pass; Skill structure validation passes; 满减 is 20 completed orders and 315 yuan; 满赠 is 100 completed activity orders, 98 issued orders/98 gifts, and 2 inventory-shortage non-issues.
- Current limit: payment status is a risk dimension only. Refund finality, gift unit cost, and fee ownership still require external confirmation.
- Next useful step: obtain those three business inputs, update the case configuration/evidence, and rerun the same outputs before deciding whether to generalize the Skill.
