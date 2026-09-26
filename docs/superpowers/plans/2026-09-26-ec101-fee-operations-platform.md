# EC101 费用运营平台重构 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将现有费用看板重构为承接 EC101 核算结果的 TPM 费用运营台，并在不开发 KPI/分销业务的前提下纳入两者的产品入口与数据依赖说明。

**Architecture:** 保留 Sites/Vinext 单页应用结构，使用一组明确的 EC101 快照数据契约驱动多个工作区视图。页面只呈现已计算的 RESULT 结果、证据链和待确认事项，不在前端重写促销公式；KPI 与分销仅作为规划视图。

**Tech Stack:** React 19、TypeScript、Vinext、Tailwind CSS、Lucide icons、Sites private deployment。

**Spec:** `docs/superpowers/specs/2026-09-26-ec101-fee-closure-product-prd.md`

## Global Constraints

- 数据底座四层分治：RAW、STANDARD、CORE、RESULT。
- `order_activity` 是订单到活动规则和权益结果的证据链中心。
- 金额权益与赠品数量分开展示；赠品未确认单价时不生成金额结算。
- T-2 候选以已核算的 `result_release_candidate` 为准，支付状态只作风险观察。
- P0、阻断和未验证数据不能进入可结算候选。
- KPI 考核与分销管理本期只做规划入口和数据依赖说明。
- 继续使用现有 Sites project、私密访问和现有部署 URL，不创建第二个站点。

## Review Focus

- 金额与赠品数量被混合计算或混合展示：由核算工作区的分组字段和文案验收。
- 待确认结果被误标记为可结算：由状态模型和结算草稿过滤验收。
- 不同经销商的平台结果串数据：由活动数据的 dealer/platform 字段和筛选验收。
- 规划中的 KPI/分销模块被误认为已上线：由规划页的范围边界和依赖提示验收。
- 证据链缺少批次、规则版本或订单入口：由证据详情视图验收。

---

### Task 1: 建立 EC101 产品视图数据契约与导航

**Files:**
- Modify: `ec101-fee-platform-v1/app/page.tsx`
- Modify: `ec101-fee-platform-v1/app/layout.tsx`
- Modify: `ec101-fee-platform-v1/app/globals.css`

**Interfaces:**
- Produces typed-in-file contracts for `ActivityRow`, `IssueRow`, `SourceRow`, `SettlementRow`, `PlanningMetric` and a navigation model used by later views.
- Consumes snapshot facts already verified in `memory.md` and the PRD: 快马×兴路强, 舟谱×羿柏, amount/gift separation, T-2 and open issues.

- [ ] **Step 1: Add the failing acceptance checklist**

  Record the required labels and invariants in a local comment block or testable constants: `金额权益`, `赠品权益`, `数据接入`, `证据与异常`, `核销与对账`, `KPI 考核`, and `分销管理`. Confirm the current page does not expose all required labels.

- [ ] **Step 2: Implement the view model and grouped navigation**

  Replace the current flat navigation with three groups: `数据底座`, `费用与促销 TPM`, and `增长运营`. Move all snapshot rows into named typed arrays and preserve the exact status wording `可提交`, `待确认`, `待处理`, `规划中`, and `未验证`.

- [ ] **Step 3: Apply the intentional visual system**

  Keep the dark navy rail and teal action color, add neutral data-workspace surfaces, and define responsive table/card behavior in `globals.css` without introducing a second theme or external asset.

- [ ] **Step 4: Run build verification**

  Run `npm run build` from `ec101-fee-platform-v1`. Expected: exit 0 and the root route is classified/renderable.

- [ ] **Step 5: Commit**

  Commit as `feat: establish EC101 operations view contract`.

### Task 2: Implement TPM operations workspaces

**Files:**
- Modify: `ec101-fee-platform-v1/app/page.tsx`

**Interfaces:**
- Consumes: Task 1 navigation and typed snapshot arrays.
- Produces: state-driven workspaces for `运营总览`, `数据接入`, `活动中心`, `权益核算`, `证据与异常`, `核销与对账`.

- [ ] **Step 1: Write the failing interaction checks**

  Define the expected state transitions in the page model: selecting a nav item changes the workspace heading; dealer/platform filters reduce rows; selecting an activity exposes its evidence summary; settlement rows exclude `待确认` and `待处理` entries.

- [ ] **Step 2: Implement the operations workspaces**

  Add a shared workspace header and render one of the six views from `active`. Build representative content from verified snapshot values, including import batches and quality gates, activity configuration, entitlement rows, issue ownership/status, and a settlement draft.

- [ ] **Step 3: Implement evidence and settlement affordances**

  Add non-destructive “查看证据”, “查看处理记录”, “打开活动详情” and “生成对账草稿” controls. They may update local panel state only; no payment, ERP write, or rule mutation is allowed.

- [ ] **Step 4: Run build and lint verification**

  Run `npm run build` and `npm run lint`. Expected: both exit 0; no runtime route error is introduced.

- [ ] **Step 5: Commit**

  Commit as `feat: add TPM operations workspaces`.

### Task 3: Add KPI/distribution planning views and publish

**Files:**
- Modify: `ec101-fee-platform-v1/app/page.tsx`
- Modify: `ec101-fee-platform-v1/app/layout.tsx` if metadata needs the final module wording.

**Interfaces:**
- Consumes: Task 1 navigation and Task 2 workspace shell.
- Produces: planning views that explicitly show future KPI and distribution dependencies without calculating or mutating business results.

- [ ] **Step 1: Write the failing scope checks**

  Assert the planning copy includes `规划中`, `依赖数据`, `业代/线路`, `目标任务`, `库存`, `sell-in`, and `sell-out`, and does not present KPI ranks or distribution quantities as real results.

- [ ] **Step 2: Implement planning views**

  Add cards for KPI metric candidates (sales, active customers, execution rate, entitlement difference rate, issue aging) and distribution dependencies (dealer, region, product, inventory, sell-in, sell-out, terminal coverage). Add a clear “本期不开发” boundary.

- [ ] **Step 3: Run final local preview gate**

  Start the existing Vinext dev server, confirm the exact local route responds with HTTP 200, and open the root URL in the existing Codex browser tab. Do not perform browser clicking or screenshot QA.

- [ ] **Step 4: Run final validation**

  Run `npm run build` and `npm run lint` after the preview gate. Expected: both exit 0.

- [ ] **Step 5: Package and publish the exact pushed source privately**

  Commit as `feat: add KPI and distribution planning surfaces`, push to the existing Sites source repository, package the build, save one version, deploy privately, poll until `succeeded`, and open the deployed URL in the existing browser tab.

## Completion Criteria

- The deployed site presents a TPM operations platform rather than a single dashboard.
- Every amount/gift value is labeled with its unit and status.
- Evidence and issue workspaces visibly preserve batch/rule/status context.
- KPI and distribution are visible as future product modules with explicit dependencies and no fabricated live calculations.
- The build, lint, and private deployment all succeed.
