# 费用与促销 TPM 实时 RESULT 工作区 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用“通用计算框架 + 满减、满赠、优惠券规则模板”生成可追溯的 RESULT，再将费用运营平台“费用与促销 TPM”工作区升级为只读展示这些真实结果。

**Architecture:** 先在核算层实现统一的“读取活动配置 → 判断资格 → 套用促销模板 → 比对实际执行 → 判断 T-2 → 写入 RESULT”流程；满减、满赠和优惠券仅替换各自的规则模板，不另建第二套流程。后端 `api/server.py` 再新增面向页面的只读聚合接口，按计算批次组合 CORE 与 RESULT 数据。React 页面只请求、筛选和展示接口返回的结果，不在浏览器重算门槛、T-2 或结算金额。第一期只读呈现真实的 `警告`/`提示` 质量等级；负责人、处理状态、P0/P1 和业务确认记录属于第二期协同闭环，不能再由前端静态数组伪造。

**Tech Stack:** Python 标准库 `http.server` 与 `sqlite3`、SQLite、React 19、TypeScript、Vinext、Tailwind CSS、Oxlint。

**Spec:** `docs/superpowers/specs/2026-09-26-ec101-fee-closure-product-prd.md`；优惠券数据接入边界见 `docs/superpowers/specs/2026-10-04-coupon-core-model-design.md`。

## 当前问题与实施边界

当前 [费用与促销 TPM 页面](../../../ec101-fee-platform-v1/app/page.tsx) 的 `activities`、`issues`、`settlements` 是静态数组。页面展示的 ¥1,995、98 个抱枕、¥675 及 100 个抱枕虽来自已核验快照，但切换数据库、计算批次或新增活动时不会自动更新；“查看证据”也只显示静态文案。现有导入脚本也把各类活动的计算写在各自脚本中，尚未收敛为可复用的促销计算框架。

本计划处理“统一计算、读取、展示、追溯、筛选和结算候选预览”，不做页面内重算、TPM/活动编辑、异常关闭、审批、付款、ERP 上账或数据库生产迁移。

## 目标数据链路

```text
tpm_application ──< activity ──< order_activity ──< result_entitlement
                       │                     └──< result_release_candidate
                       └──< result_fee ──> 当前活动/批次费用汇总

result_calc_batch ──> 上述 RESULT 记录的计算批次
result_quality_issue ──> 活动/批次异常列表与结算门禁
```

`result_fee.tpm_id` 为非空时，页面显示 TPM 编号、预算、预算预留号、费用承担方和预算余量；为 `NULL` 时明确显示“不走 TPM”，不能把空值显示为零预算。满赠等实物权益从 `result_entitlement.gift_qty_entitled` 与 `gift_qty_actual` 汇总展示，未确认成本不换算为人民币。

## RESULT 如何产生：通用计算框架 + 促销规则模板

页面不是直接从订单金额推导“¥1,995”。正确链路是：**CORE 保存事实与配置；通用框架选择模板并计算；RESULT 保存一次可复核的结论；费用平台只展示结论。**

```text
订单、商品、客户、履约、券台账         活动、规则、范围、TPM
              │                              │
              └───── 组成一次核算输入 ───────┘
                              │
                 通用计算框架（每种活动都经过）
      1. 读取规则版本和活动期间
      2. 判断客户/商品/支付/物流/场景是否符合
      3. 选择促销规则模板
      4. 算出理论权益，并与平台实际执行比对
      5. 判断“已完成 + T-2”是否可释放
      6. 识别数据缺口和差异，写入质量问题
                              │
       result_entitlement / result_release_candidate /
       result_fee / result_quality_issue / result_calc_batch
```

框架是统一的；每种促销只在第 3 步使用不同模板。模板不重复保存活动金额或范围，而是读取现有 CORE 配置。

| 模板 | 读取的 CORE 配置 | 模板计算 | 写出的 RESULT |
| --- | --- | --- | --- |
| 满减 | `activity_rule` 的门槛/立减金额，`activity_scope`，订单金额 | 符合范围且达到门槛 → 理论立减金额 | 理论/实际优惠、一致性、可结算金额 |
| 满赠 | `activity_rule_benefit` 的赠品数量，`activity_scope`，订单赠品行 | 符合范围且达到门槛 → 理论应赠数量 | 应赠/实赠数量、一致性；不自动折算金额 |
| 优惠券 | `activity_rule`，`coupon_issue_rule`，`coupon_use_rule`，`activity_scope`，`coupon_ledger` | 判断发券资格、领取上限、有效期、订单范围与核销事实 → 理论优惠 | 券是否可领/可用、理论/实际核销、一致性；未使用券不生成费用 |

例如“满 800 减 10”与“满 588 减 200”都使用同一个**满减模板**；不同的只有每个活动在 `activity_rule` 中保存的门槛和减免金额。优惠券并非另一种费用计算表，而是在通用框架中增加“券的发放与使用资格”校验后，再复用相同的理论权益、实际核销、T-2 和费用汇总步骤。

## 页面状态规则（第一期）

状态由接口返回的事实派生，页面不得用活动名称特判：

| 条件 | 页面状态 | 是否进入金额结算草稿 |
| --- | --- | --- |
| 金额活动有 `settle_amount`，存在 T-2 候选，且无同批次 `警告` | 可提交 | 是 |
| 应得与实际一致，或仅实物数量统计且无 `警告` | 已核验 | 否；实物仅展示数量 |
| 存在 `提示`，例如未达释放节点或待确认归因 | 待确认 | 否 |
| 存在 `警告`，例如真实权益差异或关联缺失 | 待处理 | 否 |
| 缺少结果、规则或计算批次 | 未验证 | 否 |

当前 `result_quality_issue` 只有“警告/提示”而没有 P0/P1、负责人或关闭记录。因此第一期异常页应显示原始等级与证据，而不是继续显示无数据库依据的 P0/P1、责任方和处理状态。

## API 契约

所有接口保持只读、JSON、分页上限 100，并沿用 `dealer`、`platform`、`limit`、`offset` 参数校验。`calc_batch_id` 可选：缺省为 `current` 模式，即每个活动选择自身最新的一个计算批次，因此首页可以同时正确显示 `calc-01`、`calc-02`、`calc-11` 等活动各自的最新结论；传入 `calc_batch_id` 时切换为历史回放模式，所有记录固定来自该批次。传入不存在的批次返回 404，不回退到其他批次。

| 路径 | 粒度 | 主要返回字段 |
| --- | --- | --- |
| `GET /api/fee-tpm/overview` | 当前活动集合或一个历史批次 | 模式、活动各自的 `calcBatchId`/`calcDate`/`ruleVersion`、可提交金额、实物实际数量、待确认数、待处理数、活动数 |
| `GET /api/fee-tpm/activities` | 活动 × 其当前批次，或活动 × 指定历史批次 | 经销商/平台、活动、促销类型、`tpm`（可空）、规则版本、金额或实物汇总、T-2 计数、异常计数、派生状态 |
| `GET /api/fee-tpm/activities/{activity_id}` | 一个活动 × 其当前批次，或指定历史批次 | 活动配置、TPM 预算信息、活动规则、范围摘要、权益汇总、T-2 汇总、质量问题和来源批次 |
| `GET /api/fee-tpm/issues` | 当前活动集合或一个历史批次中的质量问题 | 订单号、类型、原始等级、原因、证据、计算批次、可选活动关联与派生展示状态 |
| `GET /api/fee-tpm/settlements` | 活动 × 其当前批次，或活动 × 指定历史批次 | 仅返回“可提交”的金额活动；活动、TPM、结算对象、结算金额、预算余量、规则/计算批次 |

质量问题表当前没有 `activity_id`。接口应仅在能通过同一计算批次和订单的 `order_activity` 唯一定位活动时附带 `activityId`；否则保留为批次级问题，绝不按活动名称猜测归属。

## 文件结构

| 文件 | 职责 |
| --- | --- |
| `mvp/scripts/promotion_calculator.py` | 通用核算流程、满减/满赠/优惠券模板分派，以及 RESULT 写入。 |
| `mvp/tests/test_promotion_calculator.py` | 用内存 SQLite 验证通用框架、三类模板与边界条件。 |
| `api/server.py` | 新增只读费控聚合查询、批次解析、URL 路由及 JSON 响应。 |
| `api/tests/test_fee_tpm_api.py` | 用临时 SQLite 数据库验证 API 查询、过滤、状态和错误响应。 |
| `ec101-fee-platform-v1/app/page.tsx` | 删除 TPM 工作区静态结果数组，改为调用 API、显示加载/空/错误状态和真实证据详情。 |
| `ec101-fee-platform-v1/app/fee-tpm.test.tsx` | 页面层契约测试：状态、金额/实物分离、结算候选过滤和空 TPM 文案。若仓库尚无前端测试运行器，本任务同时最小化配置 Vitest + Testing Library。 |
| `api/README.md` | 记录新增只读端点、筛选参数、批次默认规则和运行方式。 |

## Global Constraints

- 前端不得重算满减、满赠、优惠券资格、T-2 或结算金额；只展示 API 的 RESULT 结论。
- 所有订单号、券号与使用订单号均以字符串传输和展示。
- 金额与实物数量必须分列；没有确认单价的赠品不显示为人民币。
- `tpm_id IS NULL` 必须展示“不走 TPM”，不能推断预算、承担方或结算状态。
- 历史批次只读；未传 `calc_batch_id` 时展示每个活动的最新结果，传入时同一视图只展示该历史批次。
- 警告、提示和无法归属的质量问题不得被默认排除、归零或伪造为已关闭。
- 不新增写接口、支付、ERP、活动编辑或异常关闭功能。

## Review Focus

- 未指定批次时，每个活动只取自身最新批次；指定旧计算批次时，所有卡片、活动和异常必须来自该 `calc_batch_id`，不能混入最新数据。
- `tpm_id=NULL` 的返券或满赠不应显示成“预算 0”或可提交的 TPM 费用。
- 赠品“应赠/实赠”必须保留数量单位；不得把 `gift_cost_total=0` 当作赠品实际数量。
- 同批次无法唯一归属某活动的质量问题必须显示为批次级异常，不能因同名活动被错挂。
- API 不可用、结果为空或筛选无匹配时，页面必须明确提示，不能回退到静态快照数字。

### Task 1: 建立通用促销计算框架与三类规则模板

**Files:**
- Create: `mvp/scripts/promotion_calculator.py`
- Create: `mvp/tests/test_promotion_calculator.py`
- Modify: `mvp/scripts/ingest_manjian.py`
- Modify: `mvp/scripts/ingest_manzeng.py`
- Modify: `mvp/scripts/ingest_coupon.py`

**Interfaces:**
- Produces: `calculate_activity(connection, activity_id: int, calc_batch_id: int, calc_date: str) -> CalculationSummary`；其内部按活动配置分派 `calculate_discount`、`calculate_gift` 或 `calculate_coupon` 模板。
- Consumes: `activity`、`activity_rule`、`activity_rule_benefit`、`activity_scope`、`coupon_issue_rule`、`coupon_use_rule`、`coupon_ledger`、订单、履约与 TPM 事实；模板不得从活动名称分派。

- [ ] **Step 1: 写通用框架红灯测试**

在内存 SQLite 数据库中建立一个满减、一个满赠和一个券类活动，并为每个活动提供最小订单、实际执行和履约数据。测试同一个入口按 `activity_category`、`promotion_type` 和是否存在券规则选择模板：

```python
def test_calculate_activity_dispatches_discount_template_from_activity_configuration():
    summary = calculate_activity(connection, discount_activity_id, calc_batch_id=1, calc_date="2026-10-04")
    assert summary.template == "discount"
    assert summary.theoretical_benefit == Decimal("10.00")
```

- [ ] **Step 2: 运行红灯测试并确认失败**

Run: `python3 -m unittest mvp.tests.test_promotion_calculator -v`

Expected: FAIL，因为 `promotion_calculator.py` 和统一入口尚不存在。

- [ ] **Step 3: 实现四个共同阶段与结果写入**

在 `promotion_calculator.py` 实现固定顺序：加载活动配置 → 按 `activity_scope` 判断资格 → 分派模板计算理论权益 → 与 `order_activity`/券台账的实际执行比对 → 写入 `result_entitlement` → 依据履约结果写入 `result_release_candidate` → 汇总为 `result_fee` → 对缺失或差异写入 `result_quality_issue`。每次运行必须先创建或接收一个 `result_calc_batch`，以规则版本和批次保证可追溯。

- [ ] **Step 4: 实现最小规则模板**

`calculate_discount` 从 `activity_rule` 读取金额或数量门槛与 `reduce_amount`；`calculate_gift` 从 `activity_rule_benefit` 读取赠品数量并比对赠品行；`calculate_coupon` 读取 `coupon_issue_rule`、`coupon_use_rule`、`activity_scope` 与 `coupon_ledger`，验证发券/领取/使用条件，且只对已使用券产生费用。三者都返回统一的 `TemplateResult`，由共同阶段写表。

- [ ] **Step 5: 补齐模板边界测试并运行绿灯测试**

覆盖：门槛不足、范围不符、未完成或未到 T-2、满赠实物数量不转金额、手动券超过个人上限、自动券早于发放时间、未使用券不写入 `result_fee`。运行：

```bash
python3 -m unittest mvp.tests.test_promotion_calculator -v
```

Expected: PASS。

- [ ] **Step 6: 将现有导入脚本改为调用统一入口并做回归验证**

保留各导入脚本各自的文件读取与 CORE 入库职责；删除或迁移其内嵌 RESULT 计算段，改为调用 `calculate_activity`。运行现有快马、舟谱核验脚本，确认已核验快照的金额、赠品数量、T-2 结果和质量问题不发生未授权变化。

- [ ] **Step 7: Commit**

```bash
git add mvp/scripts/promotion_calculator.py mvp/tests/test_promotion_calculator.py mvp/scripts/ingest_manjian.py mvp/scripts/ingest_manzeng.py mvp/scripts/ingest_coupon.py
git commit -m "feat: add reusable promotion calculation framework"
```

### Task 2: 固化 API 数据契约与测试数据库

**Files:**
- Create: `api/tests/test_fee_tpm_api.py`
- Modify: `api/server.py`

**Interfaces:**
- Produces: `query_fee_tpm_overview`, `query_fee_tpm_activities`, `query_fee_tpm_activity_detail`, `query_fee_tpm_issues` 和 `query_fee_tpm_settlements`，每个函数接收 `db_path: Path` 和已验证的查询参数，返回可 JSON 序列化的字典。
- Consumes: 现有 `mvp/ddl/ec101_mvp_sqlite.sql` 中的 CORE、RESULT 表；不得依赖前端常量。

- [ ] **Step 1: 写 API 红灯测试**

在临时 SQLite 文件中执行 DDL，插入：一个关联 TPM 的金额活动、一个 `tpm_id=NULL` 的赠品活动、两个计算批次、一条警告、一条提示及一条无法归属活动的批次级问题。测试：

```python
def test_activities_uses_requested_calculation_batch_and_keeps_gifts_as_quantities():
    payload = query_fee_tpm_activities(db_path, {"calc_batch_id": "2"})
    assert payload["calcBatchId"] == 2
    assert payload["rows"][0]["benefitKind"] == "gift"
    assert payload["rows"][0]["tpm"] is None
```

- [ ] **Step 2: 运行 API 测试并确认失败**

Run: `python3 -m unittest api.tests.test_fee_tpm_api -v`

Expected: FAIL，因为费控聚合函数和路由尚不存在。

- [ ] **Step 3: 实现当前模式、历史回放和只读聚合函数**

在 `api/server.py` 实现显式 `calc_batch_id` 校验；缺省时先为每个活动选取最新 `result_fee.calc_batch_id`，传入批次时只查该批次；按活动和批次聚合 `result_entitlement`、`result_release_candidate`、`result_fee`，并用 `activity.tpm_id` 联结 TPM。状态只依据本计划“页面状态规则”派生；赠品数量从权益表聚合；预算余量使用 `result_fee.diff_amount`，不重新计算。

- [ ] **Step 4: 补齐状态与异常归属测试**

加入以下测试：警告使活动为 `待处理` 并被 settlement 过滤；提示使活动为 `待确认`；无法唯一归属的异常仍在 issues 响应中但 `activityId` 为 `None`；不存在批次产生 404 对应的 `not_found` 响应。

- [ ] **Step 5: 运行 API 绿灯测试**

Run: `python3 -m unittest api.tests.test_fee_tpm_api -v`

Expected: PASS，所有契约、批次和异常归属测试通过。

- [ ] **Step 6: Commit**

```bash
git add api/server.py api/tests/test_fee_tpm_api.py
git commit -m "feat: add fee TPM result query API"
```

### Task 3: 暴露费控 API 路由并验证现有端点不回归

**Files:**
- Modify: `api/server.py`
- Modify: `api/tests/test_fee_tpm_api.py`
- Modify: `api/README.md`

**Interfaces:**
- Consumes: Task 2 的五个查询函数。
- Produces: `/api/fee-tpm/*` 的 `GET` 路由；旧 `/api/business-data/*` 路由及其响应不变。

- [ ] **Step 1: 写路由红灯测试**

用 `make_handler` 和临时 HTTP 服务器测试：

```python
def test_fee_tpm_activity_detail_returns_404_for_an_unknown_activity():
    status, payload = get_json("/api/fee-tpm/activities/999?calc_batch_id=2")
    assert status == 404
    assert payload["error"] == "not_found"
```

- [ ] **Step 2: 运行路由测试并确认失败**

Run: `python3 -m unittest api.tests.test_fee_tpm_api.FeeTpmRouteTests -v`

Expected: FAIL，因为 `/api/fee-tpm/*` 尚未被分派。

- [ ] **Step 3: 在 `make_handler` 中实现费控路由**

增加 overview、activities 列表、activities 详情、issues 和 settlements 的 `GET` 分派。复用现有 `_conditions`、`_bounds` 的参数验证风格；未知路径返回已有的 404 JSON 格式；不开放 POST、PUT、PATCH 或 DELETE。

- [ ] **Step 4: 记录接口与人工核验命令**

在 `api/README.md` 新增端点表和示例：

```bash
curl 'http://127.0.0.1:8787/api/fee-tpm/activities?calc_batch_id=11'
```

明确服务是只读、`calc_batch_id` 省略时“每活动最新”与传入时“历史回放”的选择规则，以及 `tpm=null` 的含义。

- [ ] **Step 5: 运行完整 API 测试与旧业务数据回归**

Run: `python3 -m unittest discover -s api/tests -v`

Expected: PASS；再运行 `python3 -m unittest api.tests.test_server -v`（若该文件存在），或为现有 `query_dataset` 添加一个订单查询回归断言。

- [ ] **Step 6: Commit**

```bash
git add api/server.py api/tests/test_fee_tpm_api.py api/README.md
git commit -m "feat: expose fee TPM result endpoints"
```

### Task 4: 用 API 数据替换 TPM 页面静态快照

**Files:**
- Modify: `ec101-fee-platform-v1/app/page.tsx`
- Create: `ec101-fee-platform-v1/app/fee-tpm.test.tsx`
- Modify: `ec101-fee-platform-v1/package.json`
- Create: `ec101-fee-platform-v1/vitest.config.ts`

**Interfaces:**
- Consumes: Task 3 的 `/api/fee-tpm/overview`、`/activities`、`/issues`、`/settlements` 和 activity-detail 响应。
- Produces: `FeeTpmActivityRow`、`FeeTpmIssueRow`、`FeeTpmSettlementRow` TypeScript 类型，及一个可复用的 `useFeeTpmData(calcBatchId, dealer, platform)` 读取边界。

- [ ] **Step 1: 写页面红灯测试**

使用 `fetch` mock 提供 API 响应，并验证：

```tsx
it('renders a non-TPM gift as a quantity and never as currency', async () => {
  render(<Home />)
  await screen.findByText('98 个抱枕')
  expect(screen.getByText('不走 TPM')).toBeInTheDocument()
  expect(screen.queryByText('¥ 0')).not.toBeInTheDocument()
})
```

同时覆盖 API 失败时显示“无法加载核算结果，未使用快照回退”，以及 `待确认`/`待处理` 行不在结算草稿中。

- [ ] **Step 2: 运行页面测试并确认失败**

Run: `npm test -- --run app/fee-tpm.test.tsx`

Expected: FAIL，因为测试依赖和动态数据边界尚不存在。

- [ ] **Step 3: 最小化配置前端测试并实现只读数据钩子**

在 `package.json` 添加 Vitest、jsdom、Testing Library 和 `test` script；只为该页面配置测试环境。将 API 基地址继续使用现有 `NEXT_PUBLIC_EC101_API_URL` 约定；请求缺省批次时不带 `calc_batch_id`，显式选择批次时传递该参数。

- [ ] **Step 4: 改造各个 TPM 工作区**

移除静态 `activities`、`issues`、`settlements`。用 overview 驱动运营总览，用 activities 驱动活动中心/权益核算，用 issues 驱动证据与异常，用 settlements 驱动核销与对账/结算批次。活动详情抽屉请求 detail 接口并展示：活动、规则、TPM 或“不走 TPM”、预算信息、权益、T-2、质量问题与计算批次。保留业务数据工作区的现有 API 行为。

- [ ] **Step 5: 运行页面绿灯测试**

Run: `npm test -- --run app/fee-tpm.test.tsx`

Expected: PASS；金额、赠品、空 TPM、API 失败和结算过滤断言都通过。

- [ ] **Step 6: Commit**

```bash
git add ec101-fee-platform-v1/app/page.tsx ec101-fee-platform-v1/app/fee-tpm.test.tsx ec101-fee-platform-v1/package.json ec101-fee-platform-v1/vitest.config.ts
git commit -m "feat: read live fee TPM results in workspace"
```

### Task 5: 端到端只读验证与文档同步

**Files:**
- Modify: `PROJECT.md`
- Modify: `ec101-fee-platform-v1/README.md`（不存在则创建）

**Interfaces:**
- Consumes: Task 3 API 与 Task 4 页面。
- Produces: 可复现的本地运行、验证和已知限制说明。

- [ ] **Step 1: 启动本地 API 和平台**

Run in separate terminals:

```bash
python3 api/server.py
NEXT_PUBLIC_EC101_API_URL=http://127.0.0.1:8787 npm run dev
```

- [ ] **Step 2: 验证快马、舟谱、异常和无 TPM 情况**

用浏览器或 HTTP 请求核验：

1. 快马满减显示当前批次的 T-2 可结算金额与 TPM 预算余量；
2. 快马/舟谱满赠显示应赠、实赠和数量单位，且注明不走 TPM；
3. 舟谱返券存在提示时为待确认且不进入草稿；
4. 警告活动显示待处理；
5. 断开 API 或返回 500 时页面不显示旧静态金额。

- [ ] **Step 3: 运行完整验证**

Run:

```bash
python3 -m unittest discover -s api/tests -v
cd ec101-fee-platform-v1 && npm test -- --run && npm run lint && npm run build
```

Expected: 全部退出码为 0。

- [ ] **Step 4: 更新项目说明**

在 `PROJECT.md` 和前端 README 中说明：费用与促销 TPM 工作区已读取 RESULT；计算仍由导入/核算脚本生成；异常确认、负责人、P0/P1、支付和 ERP 上账仍未实现；生产多人使用前仍须迁离本地 SQLite。

- [ ] **Step 5: Commit**

```bash
git add PROJECT.md ec101-fee-platform-v1/README.md
git commit -m "docs: document live fee TPM workspace"
```

## 第二期：协同闭环（不属于本计划的实现范围）

在第一期稳定后，单独立项并增加可审计的异常协同模型：质量问题的 `priority`、`owner`、`resolution_status`、`resolution_note`、`resolved_by`、`resolved_at`，以及结算批次及确认记录。届时才可在页面真实展示 P0/P1、负责人、待确认/处理中/关闭，并由确认状态影响结算门禁；不能先在前端写按钮或静态状态冒充已实现。

## Completion Criteria

- 费用与促销 TPM 所有金额、数量、状态、异常和结算候选均来自指定的 API 计算批次，不再来自前端静态数组。
- 每一活动结果可显示活动、规则、计算批次、TPM（或不走 TPM）、权益、T-2 和质量问题证据。
- `警告`、`提示`、无结果和无 TPM 的语义不会被简化为可提交或零值。
- 结算页面只显示满足第一期门禁的金额活动；赠品保持数量展示。
- API、页面测试、lint 和构建均有可重复的通过证据。
