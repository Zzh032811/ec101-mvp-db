# EC101 促销费用数据底座 — MVP 数据库使用说明 V1

> 一份复合文档：既讲清楚这个数据库**从哪来、干什么用、有哪些功能**（产品/设计视角），也给出**怎么打开、怎么查、怎么重跑**的操作手册（使用视角）。

| 文档属性 | 内容 |
|---|---|
| 对应数据库 | `mvp/ec101_mvp.db`（SQLite 单文件，6.9 MB，24 张业务表，其中 21 张已填充、3 张为空占位） |
| 文档定位 | MVP 阶段数据库的总说明：来源 + 用途 + 功能 + 数据字典 + 操作手册 |
| 版本 | V1.2（2026-09-23）——版本线：V1.0（满减+满赠）→ V1.1（优惠券台账接入、客户主数据换 9/22 新快照、满赠去 TPM/费用改数量口径/18 指定商品落库、修复读取器 OOXML 正则缺陷）→ **V1.2（为客户 9/22 快照补登 RAW 血缘批次 4，raw_import_batch 4 / raw_file 12，关闭"血缘 vs 数据"不一致）** |
| 建模试点 | 快马平台 × 深圳市兴路强商贸有限公司（下称"兴路强"），已接入**满减 + 满赠**两类活动并完成核算，**优惠券**已接入台账层（券核算待完整规则） |
| 编制依据 | 《EC101 数据底座建设方案 V1》、《EC101 逻辑数据模型设计说明 V1》、EC101 标准字段字典、SAP TPM 促销申请单、快马满减/满赠/优惠券配置截图、兴路强源数据（客户主数据以 9/22 新快照 `User-202609221722.xlsx` 为准）、`ec101-promotion-closure-validator` 业务规则库 |
| 建议读者 | 项目负责人、业务与市场、数据团队、技术团队，以及需要查数/复核的同事 |
| 阅读建议 | 只想看数 → 直接读 §7 操作说明；想懂设计 → 读 §3~§6；想推动业务确认 → 读 §8 Gap 清单 |

---

## 1 这是什么，解决什么问题

### 1.1 业务背景（PRD 诉求）

太古可口可乐（Swire Coca-Cola）通过经销商在第三方订货平台（如"快马"）做促销活动（满减、满赠、优惠券等）。促销产生的费用，最终由太古侧承担、向经销商结算。结算前必须回答四个问题：

1. **该不该给** —— 每一笔订单享受的优惠，是否符合活动规则？（平台算的 vs 太古规则重算的，是否一致）
2. **给多少** —— 符合规则的费用合计是多少？哪些已经到了可以结算的节点？
3. **谁承担、够不够** —— 费用由哪个部门承担？对应的促销预算（TPM 申请）还剩多少？
4. **能不能查** —— 任何一个结论，能不能一路追溯回原始的订单、活动配置、平台导出文件？

过去这些靠人工对 Excel，慢、易错、不可追溯。本数据库就是把这套"促销费用结算核验"的逻辑**沉淀成结构化、可查询、可追溯、可重复计算的数据底座**。

### 1.2 本库的定位：数据底座，不是验证脚本

项目里有一个配套工具叫 `ec101-promotion-closure-validator`（促销闭环验证器），它是**文件级的验证脚本**：读平台导出的 Excel，重算一遍，输出 1+4 份 Excel 报告。

本数据库（`ec101_mvp.db`）和它**共享同一套业务规则口径**（满减/满赠怎么算、T-2 怎么判、谁承担费用），但定位不同：

| | validator（验证器） | 本数据库（数据底座） |
|---|---|---|
| 产物 | Excel 报告（一次性结论） | 结构化数据库（事实 + 结论分层存储） |
| 形态 | 跑一次出一份报告 | 数据沉淀下来，可随时按任意维度查询、关联、追溯 |
| 价值 | 快速验证单个案例 | 多活动/多批次/多平台累积，支撑对账、审计、复用 |

一句话：**validator 算给你看，数据库把算的过程和结果存下来、连起来、可回查。**

### 1.3 当前能回答 / 还不能回答

**能回答（已接入并核验通过）：**
- 兴路强满减活动：136 笔订单，平台实际优惠与太古规则重算 100% 一致（合计 2040 元），其中 133 笔已到 T-2 可结算节点（1995 元）。
- 兴路强满赠活动：98 笔订单，应赠 = 实赠 = 98 个赠品（雪碧冰丝抱枕），100% 一致，全部已到可结算节点；赠品**按数量统计、不结算单价**（业务已决）。
- 优惠券台账：1 张定向优惠券（测试券）已落 `coupon_ledger`，券→订单关联实测命中 order_id 713（已完成）——证明"使用单号"按文本重导后精度阻断已解除。
- 客户匹配：2925 张订单的 customer_id **已全部匹配**（空值 0），客户主数据已换 9/22 新快照（2292 客户）。
- 任一结论可追溯到原始文件、导入批次、活动配置、订单行。

**还不能回答（范围外或挂起，详见 §3.3、§8）：**
- 优惠券类活动的**费用核算**（台账已建、关联已通，但仅 1 张测试券、无结构化券规则，未算券的理论权益/费用，等平台给完整券活动配置与全量领用数据）。
- 经销商拿货 vs 终端动销对比、业务员/线路考核（预留，未建表）。
- 跨系统映射（`cross_mapping` 空）：客户/商品与太古侧编号的权威对照表待人工修正后入库。

---

## 2 数据库来源

### 2.1 三类来源

本库的数据来自三个渠道，对应模型里不同的录入方式：

| 来源类型 | 具体内容 | 进入哪一层 | 录入方式 |
|---|---|---|---|
| **平台导出文件** | 快马后台导出的订单明细、销售明细、活动明细、客户列表、商品列表 | RAW → CORE | 脚本自动读取解析 |
| **业务录入** | SAP TPM 促销申请单（预算、承担方、计划期等） | CORE（tpm_application） | 人工录入（不在平台导出内） |
| **配置截图（人工结构化）** | 快马满减/满赠/优惠券活动方案截图 | CORE（activity 系列表） | 人工把截图里的规则结构化后录入 |

> 关键点：活动规则（满多少减多少、送什么赠品）**只存在于供应商后台的配置截图里**，平台导出的数据文件里并没有完整的规则定义。所以活动配置必须依据截图人工结构化——这也是为什么"配置截图"是重算公式的权威依据。

### 2.2 兴路强试点源文件清单

所有原始文件位于 `快马-兴路强-试点/` 目录：

| 文件 | 模块 | 真实格式（按文件签名判定） | 数据行数 | 用于 |
|---|---|---|---|---|
| `Product-202609141043.xlsx` | 商品主数据 | OOXML | 9129 | 商品表 |
| `User-202609221722.xlsx` | 客户主数据（9/22 新快照） | OOXML | 2292 | 客户表 |
| `满减/快马-兴路强-满减-订单明细-20260831-20260917.xls` | 订单 | BIFF | 36157 | 订单头/订单行 |
| `满减/快马-兴路强-满减-销售明细-20260831-20260917.xlsx` | 销售 | OOXML | 31338 | 销售侧证据（仅登记血缘） |
| `满减/快马-兴路强-满减-活动明细-20260831-20260917.xls` | 活动明细 | HTML | 937 | 订单活动关系 |
| `满减/组合促销满减方案.png` | 活动配置 | PNG 截图 | — | 满减规则结构化依据 |
| `满赠/快马-兴路强-满赠-订单明细-20260819-20260831.xls` | 订单 | BIFF | 26254 | 订单头/订单行（含赠品行） |
| `满赠/快马-兴路强-满赠-销售明细-20260819-20260831.xls` | 销售 | OOXML | 26074 | 销售侧证据（仅登记血缘） |
| `满赠/快马-兴路强-满赠-活动明细-20260819-20260831.xls` | 活动明细 | HTML | 250 | 订单活动关系 |
| `满赠/满赠指定商品列表.xlsx` | 活动范围 | OOXML | 18 | 满赠 18 个指定雪碧 SKU → `activity_scope` |
| `满赠/组合促销满赠方案.png` | 活动配置 | PNG 截图 | — | 满赠规则结构化依据 |
| `优惠券/快马-兴路强-优惠券-定向优惠券-活动明细-20260909-20260912.xls` | 优惠券 | HTML | 1 | 券台账 `coupon_ledger`（1 张测试券） |
| `优惠券/快马-兴路强-优惠券-定向优惠券-订单明细-20260909-20260912.xls` | 订单 | BIFF | 8594 | 券→订单关联验证 |
| `优惠券/快马-兴路强-优惠券-定向优惠券-销售明细-20260909-20260912.xlsx` | 销售 | OOXML | 8541 | 销售侧证据（仅登记血缘） |
| `优惠券/优惠券方案.png` | 活动配置 | PNG 截图 | — | 券规则待补全（见 §8） |
| `平台操作手册.xlsx` | 操作指引 | OOXML | — | 数据导出方法参考 |

> **重要提醒：扩展名不可信。** 快马导出的文件后缀都是 `.xls`/`.xlsx`，但真实格式有三种：老式 BIFF（`.xls`）、OOXML（`.xlsx`，本质是 zip+XML）、以及 HTML 表格伪装成 `.xls`。所以读取时**按文件头魔数（magic bytes）判定真实格式**，不看后缀（见 §5.1）。
>
> **客户主数据血缘说明（已补登）**：批次 1 的 `raw_file` 登记的是**原始 9/14 快照**（`User2026091410413051852.xlsx`，2273 行）；客户表后来换成了 **9/22 新快照**（`User-202609221722.xlsx`，2292 客户）。为避免"血缘 vs 数据"对不上账，已按 RAW 层**不改不覆盖**原则**补登批次 4**（`KM-XLQ-CUST-REFRESH-20260922`）登记新快照文件（data_rows=2292），**保留批次 1 旧行作历史记录**。现库客户行的权威血缘 = 批次 4。补登只写血缘两张表，**不影响任何计算结果**（customer_id 校验和不变、FK 零违例）。

### 2.3 批次血缘

每一次导入登记为一个"批次"（`raw_import_batch`），每个文件登记一条"文件签名"（`raw_file`）。当前库里有 **4 个批次、12 个登记文件**：

| 批次 | batch_code | 来源 | 登记文件数 | 说明 |
|---|---|---|---|---|
| 1 | `KM-XLQ-MJ-20260831-20260917` | 快马-兴路强-满减 | 5 | 含商品/客户主数据（客户为 9/14 快照） |
| 2 | `KM-XLQ-MZ-20260819-20260831` | 快马-兴路强-满赠 | 3 | 追加，复用批次1的主数据 |
| 3 | `KM-XLQ-YHQ-20260909-20260912` | 快马-兴路强-优惠券（定向优惠券） | 3 | 追加，落 `coupon_ledger` + 券→订单关联验证 |
| 4 | `KM-XLQ-CUST-REFRESH-20260922` | 快马-兴路强-客户主数据刷新 | 1 | 补登 9/22 客户快照（2292 行）；**主数据刷新批，无对应计算批次** |

任何一个计算结果都能反查到"是哪个批次、哪个文件、第几行来的"——这是 P6"原始可追溯"原则的落地。

---

## 3 总体架构

### 3.1 四层数据模型

数据从原始文件到最终结论，分四层流转，每层职责单一：

```
平台原始文件 / TPM申请单 / 配置截图
        │  导入（登记批次与文件签名）
        ▼
RAW  原始数据层      平台给什么留什么，不改不覆盖，只登记"是什么、从哪来"
        │  字段映射 / 编码与类型标准化 / 质量校验
        ▼
STANDARD 标准数据层  把各平台字段翻译成 EC101 统一业务语言
        │  按业务对象组装
        ▼
CORE  业务事实层     经销商/客户/商品/订单/活动/履约/映射/券台账
        │  规则重算 / 资格判断 / 费用计算（带规则版本 + 计算批次）
        ▼
RESULT 应用结果层    理论权益 / 一致性 / 发放候选 / 费用结算 / 差异 / 质量台账
```

通俗类比：RAW 是"原始凭证扫描存档"，STANDARD 是"把各地方言翻译成普通话"，CORE 是"整理成台账"，RESULT 是"会计算出的结论"。

### 3.2 八条设计原则

| # | 原则 | 通俗解释 |
|---|---|---|
| P1 | 四层分治 | 原始、标准、事实、结论分开存，各管一段，不混 |
| P2 | 按业务对象建模 | 一个业务对象（客户/商品/订单）一张表，不按 Excel 文件建表 |
| P3 | 预算层与执行层分离 | TPM 促销申请是"预算/审批"（和订单无关），订单活动是"执行"（订单粒度），两者分开建表、用"活动"关联 |
| P4 | 单值列、多值行 | 活动配置里单项的（优惠方式、限购）放主表的列；多项的（阶梯、赠品、商品范围）拆成子表的行 |
| P5 | 活动双键 | 业务键 = 经销商+平台+活动名称（人看得懂）；技术主键 = 内部自增 activity_id（机器用，永不变） |
| P6 | 原始可追溯 | 任一结果能定位到导入批次、原始文件、来源平台 |
| P7 | 规则版本化 | T-2 口径、重算公式等业务规则存进"规则目录"，带版本/生效时间/确认人，不写死在代码逻辑里 |
| P8 | 编号一律字符串 | 订单号、券号、使用单号等长编号按文本存，避免被当成数字导致精度丢失（见 §8 的 Excel 截断问题） |

### 3.3 本 MVP 库的范围边界

**已建并填充数据的（21 张表）**：RAW 血缘 2 张、CORE 事实 13 张（含 `coupon_ledger` 券台账 1 条）、RESULT 结论 6 张（含 `rule_catalog` 规则目录）。

**已建表但当前为空（3 张，MVP 阶段未填充）**：

| 表 | 为什么是空的 | 何时填充 |
|---|---|---|
| `cross_mapping` 跨系统映射 | 客户/商品与太古侧编号的对照表，需人工修正后入库 | 映射表确认后 |
| `std_field_mapping` 字段映射 | MVP 阶段映射关系直接写在脚本里，未落表 | 多平台接入时沉淀 |
| `std_quality_check` 质量校验 | MVP 阶段质量结论直接进 `result_quality_issue` | 标准化阶段细化 |

> 说明：`coupon_ledger`（券台账）在 V1.0 时为空、现已填充 1 条测试券，故从"空表"清单移出。

**明确未建表的预留模块**：经销商拿货/进货表（EC101 订单汇总，dealer sell-in，即经销商进货口径）、业务员/线路维度、深度库存、数据指标/业代考核。这些属于应用层，由 CORE 事实二次计算，不在导入时写死。

---

## 4 数据字典（24 张表）

> 类型约定：编号/单号 = TEXT（字符串）；金额 = NUMERIC（入库四舍五入 2 位，生产 MySQL 映射 DECIMAL(12,2)）；日期时间 = TEXT，ISO 格式 `YYYY-MM-DD HH:MM:SS`；布尔 = INTEGER（0/1）。"现状行数"为 2026-09-22 满减+满赠+优惠券三批接入、且客户主数据换 9/22 新快照后的实际值。

### 4.1 RAW / 血缘层（2 张）

| 表 | 职责 | 粒度 | 关键字段 | 现状行数 |
|---|---|---|---|---|
| `raw_import_batch` 导入批次 | 血缘根，一次导入一条 | 批次 | batch_code（唯一）、source_platform、dealer_name、imported_at、operator | 4 |
| `raw_file` 原始文件登记 | 一个文件一条，记录真实格式与读取方式 | 文件 | batch_id、file_name、module、file_signature（OOXML/BIFF/HTML）、read_method、sheet_name、data_rows | 12 |

### 4.2 CORE 业务事实层（14 张）

| 表 | 职责 | 粒度 | 关键字段 | 现状行数 |
|---|---|---|---|---|
| `dealer_platform` 经销商·平台 | 数据来源归属 | 经销商×平台 | dealer_name、platform_name、swire_partner_code（太古合作伙伴编号，预留）、admission_status | 1 |
| `customer` 客户 | 标准客户主数据 | 客户 | platform_customer_no、customer_name、customer_type/level/tag/region、salesperson_name、swire_outlet_no（太古售点号，来自映射） | 2292 |
| `product` 商品 | 商品（SKU）主数据 | SKU | platform_product_no、product_name、brand、category、barcode、base_unit、box_conversion、actual/occupied/available_stock、shelf_status、cost_avg_price、swire_product_code（太古产品代码，来自映射） | 9129 |
| `order_header` 订单头 | 一张订单一条 | 订单 | order_no（字符串）、order_time、customer_id、order_status、pay_method、pay_status、order_source、order_type、batch_id | 2925 |
| `order_line` 订单行 | 订单×商品一条 | 订单行 | order_id、product_id、order_qty/unit、base_qty/unit、pre_discount_amount、discount_amount、unit_price、return_qty（预留） | 59631 |
| `tpm_application` 促销申请(TPM) | 预算/审批层，**不挂订单**（P3） | 一张 TPM 单 | tpm_code（如 DCN-9926018）、apply_amount（预算，如 30000）、fee_pay_dept（费用支付部门）、invoice_title（发票抬头）、plan_start/end、release_start/end、approval_status、wbs_id | 1 |
| `activity` 活动主表 | 一个活动一条（单值配置列） | 活动 | activity_name、activity_category（券类/非券类）、promo_method（阶梯/叠加）、promotion_type（满额立减/立赠）、purchase_limit_type/value、start_time/end_time、allow_stack、allow_coupon、tpm_id | 2 |
| `activity_rule` 活动规则行 | 活动×每档门槛一条（阶梯，多值行 P4） | 阶梯档 | activity_id、tier_no、threshold_type（金额/数量）、threshold_value、reduce_amount、free_shipping | 2 |
| `activity_rule_benefit` 活动权益行 | 规则×每权益一条（赠品/券，多值行） | 权益 | rule_id、benefit_type（立减/免邮/赠品/送券）、gift_product_no/name、gift_qty、coupon_id/name/qty | 2 |
| `activity_scope` 活动范围行 | 活动×每个范围取值一条（商品/客户范围，多值行） | 范围值 | activity_id、scope_category（商品/禁用商品/客户/禁用客户）、scope_dimension（品牌/商品/类型/区域…）、scope_value | 30 |
| `order_activity` 订单活动关系 | **全链路最核心**：一单命中一活动一条 | 订单×活动 | order_id、activity_id、rule_id、activity_product_amount、platform_actual_benefit（平台实际优惠）、gift_qty_actual（赠品实发数）、policy_text、exec_status、evidence_ref | 234 |
| `fulfillment` 履约 | 订单履约状态与释放候选 | 订单 | order_id、order_status、completed_at、t2_release_candidate（T-2 候选标志）、return_qty、special_reason（破损等例外，预留） | 2925 |
| `cross_mapping` 跨系统映射 | EC101 客户/商品 ↔ 太古对象 | 映射对 | mapping_object_type（客户/商品）、ec101_key、swire_key、match_status、hit_field、fuzzy_score、manual_corrected | 0（预留） |
| `coupon_ledger` 优惠券台账 | 券类活动执行明细（领取/使用/失效） | 一张券 | coupon_no（字符串）、coupon_name、customer_id、receive_time、use_period、coupon_status、use_time、use_order_no（字符串，=订单号同类型）、discount_amount、fee_month | 1（台账已接入） |

### 4.3 RESULT 应用结果层（6 张）

| 表 | 职责 | 粒度 | 关键字段 | 现状行数 |
|---|---|---|---|---|
| `rule_catalog` 规则目录 | 业务规则版本化（P7） | 规则×版本 | rule_topic（T-2释放节点/满减权益重算/满赠权益重算）、version、effective_from、confirmed_by、rule_text | 3 |
| `result_calc_batch` 计算批次 | 一次计算一条，保证可重复 | 计算批次 | calc_date、rule_version、input_batch_id、operator、created_at | 3 |
| `result_entitlement` 理论权益与一致性 | 订单活动一条 | 订单×活动 | order_activity_id、theoretical_benefit（理论权益）、platform_actual_benefit（平台实际）、gift_qty_entitled/actual（应赠/实赠数）、consistency（一致/差异）、diff_amount、formula_ref、calc_batch_id | 234 |
| `result_release_candidate` 发放候选 | 订单一条，判 T-2 是否可结算 | 订单×计算日 | order_id、calc_date、is_candidate、reason、calc_batch_id；唯一键(order_id, calc_batch_id) | 234 |
| `result_fee` 费用结果/结算 | TPM单×活动一条 | 活动×批次 | actual_discount_total、gift_cost_total、fee_bearer（承担方）、settle_target（结算对象）、budget_amount、settle_amount、diff_amount、settle_status、calc_batch_id | 2 |
| `result_quality_issue` 质量台账 | 一个异常/Gap 一条，逐单可追溯 | 异常 | order_no、issue_type、level（警告/提示）、reason、evidence_ref、calc_batch_id | 7 |

### 4.4 STANDARD 标准层（2 张，轻量）

| 表 | 职责 | 关键字段 | 现状行数 |
|---|---|---|---|
| `std_field_mapping` 字段映射 | 平台原始字段 → EC101 标准字段 | platform、module、raw_field、ec101_field、confidence、is_non_v1、gap_flag | 0（MVP 未落表） |
| `std_quality_check` 质量校验 | 入库前质量门禁结论 | batch_id、check_item、result（通过/条件通过/阻断）、level、impact | 0（MVP 未落表） |

### 4.5 实体关系总览（逻辑外键）

```
dealer_platform ──┬─ customer ───┐
                  ├─ product ────┤
                  │              ▼
                  │         order_header ─┬─ order_line ── product
                  │                       ├─ fulfillment
                  │                       └─ order_activity ── activity ─┬─ activity_rule ── activity_rule_benefit
                  │                                    │                 └─ activity_scope
                  ├─ tpm_application ── activity       │
                  └─ coupon_ledger ── order_header     ▼
                                          result_entitlement / result_release_candidate / result_fee / result_quality_issue
                                                   │
                              全部 RESULT 表 ──→ result_calc_batch + rule_catalog
```

数据库启用了外键约束（`PRAGMA foreign_keys = ON`），当前**外键违例 = 0**，即所有关联都指向真实存在的记录。

---

## 5 核心功能与业务逻辑

本节讲清楚这个库"会算什么、怎么算"。八个功能对应数据从导入到结论的完整链路。

### 5.1 功能一：格式感知的原始数据登记

**解决的问题**：快马导出文件后缀全是 `.xls`/`.xlsx`，但真实格式有三种，用错读取方式会乱码或报错。

**做法**：读取器 `readers.py` 先读文件头 8 字节魔数判定真实格式，再选对应解析方式：

| 文件头魔数 | 真实格式 | 解析方式 |
|---|---|---|
| `PK\x03\x04` | OOXML（`.xlsx`，本质 zip+XML） | 标准库 zipfile + XML 解析 |
| `\xd0\xcf\x11\xe0` | BIFF（老式 `.xls`） | BIFF 记录解析 |
| 其它 | HTML（伪 `.xls` 表格） | 标准库 HTMLParser |

每个文件登记批次、签名、读取方式、数据行数（`raw_file`）。所有单元格读出来先当**字符串**，日期统一归一为 ISO 格式 `YYYY-MM-DD HH:MM:SS`（避免后续按字符串比较时间时出错）。

> 实现说明：读取器**只用 Python 标准库**（zipfile/re/html.parser/datetime），不依赖 openpyxl/pandas——因为本机 openpyxl 对部分损坏的 XML（如非法 `<dimension>`）不稳定。

> **2026-09-22 修复一个 OOXML 解析缺陷**：原单元格切分正则把"自闭合分支"放在后面，导致空样式格 `<c r="D12" s="1"/>` 与后一个有值格合并——列值左移错位、且丢失共享字符串标记（值被存成原始索引）。修复=把自闭合分支前置。**影响面**：只波及含"内部空样式格"的 `.xlsx`（客户主数据、销售明细），`.xls`(BIFF) 不走此正则、完全安全；且计算结果全部来自 `.xls` 或不受影响的文件，**结果未受污染**。修复后已用修正读取器就地重灌客户表 2292 行描述列（`customer_id` 校验和不变、FK 零违例）。

### 5.2 功能二：跨系统主数据匹配

**解决的问题**：平台里的客户/商品编号，和太古侧的售点号/产品代码是两套编号体系，要对上。

**做法**：
- 客户：按 `platform_customer_no` 建索引，订单按客户编号关联。客户主数据已换 **9/22 新快照**（2292 客户），当前 2925 张订单的 customer_id **已全部匹配（空值 0）**——原先 2 张 9/16 订单因客户晚于 9/14 快照注册而挂空，已用新快照补齐回填。
- 商品：先按 `platform_product_no`（商品编号）匹配，匹配不上再按 `barcode`（条码）兜底。

**现状缺口（已澄清，非缺陷）**：全库 59631 行订单明细中约 **1115 行**（1.87%）未匹配到商品主数据（product_id 为空），整体匹配率 **98.1%**。业务已明确：**产品映射只覆盖太古可口可乐系列产品**，这些空值经核实多为怡宝水、红牛、姚记扑克、哈啤等**非可乐商品**，按设计不纳入映射，属**正常而非数据错误**；`cross_mapping` 仅需覆盖可乐系。质量台账"商品跨系统匹配缺口"记录的是**满减批次口径的 844 行**（全库含满赠/券订单后为 1115 行）。

### 5.3 功能三：活动配置结构化（满减 vs 满赠）

**解决的问题**：活动规则只在配置截图里，要把截图变成可计算的数据库结构。

**做法**：按 P4"单值列、多值行"拆分——

- **满减**（活动 id=1，"可口可乐满减"，挂 TPM `DCN-9926018`）：
  - 主表：非券类、阶梯、满一定金额立减、指定品牌、每用户限购、窗口 2026-08-31 10:58 ~ 09-17 23:59、允许叠加、允许用券
  - 规则行：阶梯 1，金额满 **300**，立减 **15**
  - 权益行：立减
  - 范围行：商品=品牌"可口可乐"（1 条）+ 客户类型 6 项，共 **7 条**
- **满赠**（活动 id=2，"满赠优惠"，**不走 TPM**，tpm_id=NULL）：
  - 主表：非券类、阶梯、满一定金额立赠、指定商品、每用户限购 1、窗口 2026-08-19 15:15 ~ 08-31 23:59、允许叠加、允许用券
  - 规则行：阶梯 1，金额满 **100**，立减 **0**（满赠不减钱）
  - 权益行：赠品 = 商品 348721357"雪碧 冰丝抱枕（赠品勿下）"× **1**
  - 范围行：商品=**18 个指定雪碧 SKU**（来自 `满赠指定商品列表.xlsx`，编号=`platform_product_no`，18/18 精确匹配 product 表）+ 客户类型 5 项（西乡/零售/线下付款客户/闪电仓/可口可乐业务），共 **23 条**（已替换 V1.0 的占位记录）

> 口径要点：优惠方式 = **阶梯 + 单档** ⇒ 固定减一次（满减 300 减 15，不是每满 300 都减）；= 叠加 ⇒ 每满循环。配置截图即重算公式的依据。

### 5.4 功能四：权益重算与一致性校验

这是核算的核心——**用太古的规则重算一遍，和平台实际给的优惠比对**，结果存 `result_entitlement`。

**满减口径**：
- 活动明细里"促销优惠金额"是按参与商品行**分摊**的，所以先按订单号**汇总**，再和理论值比。
- 理论权益：订单商品金额 ≥ 300 ⇒ 应减 15（定额一次）。
- 结果：136 笔订单，理论合计 = 平台实际合计 = **2040 元**，**136 笔全部一致，0 差异**。

**满赠口径（关键区别）**：
- 满赠的"促销优惠金额"全是 **0**——因为满赠不发金额优惠，只发**实物赠品**。
- 所以满赠的权益**按赠品个数算，不按金额算**：
  - 应赠（gift_qty_entitled）：订单商品金额 ≥ 100 且在活动窗口内 ⇒ 应赠 1 个。
  - 实赠（gift_qty_actual）：订单明细里商品 348721357 的赠品行数量（真实发货证据）。
- 金额列（theoretical_benefit / platform_actual_benefit）对满赠记 **0**；赠品数走专门的可空列 `gift_qty_entitled` / `gift_qty_actual`。满减行这两列保持 NULL——两类活动互不污染。
- 结果：98 笔订单，**应赠 98 = 实赠 98，98 笔全部一致，0 差异**。

> 为什么这么设计：如果沿用满减的"金额权益"口径，满赠权益会被错记成 0，既看不出赠品发了多少，也会误用金额列。赠品是实物，结算基础是"发了多少个抱枕 × 单价"。

### 5.5 功能五：T-2 费用释放判定

**解决的问题**：费用不是下单就结算，要等到订单完成、且过了观察期。

**口径（已确认业务规则，存 `rule_catalog` 的"T-2释放节点 v1"）**：
- 可释放条件：`订单状态 = 已完成` **且** `下单时间 ≤ 计算日 T-2 的 00:00:00`。
- **支付状态不过滤**：货到付款 + 未支付 + 已完成，仍计入有效促销（支付状态只作风险观察维度）。
- 当前计算日 = 2026-09-22，T-2 切割点 = 2026-09-20 00:00:00。

**结果**：
- 满减：136 笔里 133 笔可释放，3 笔暂不可（状态=部分发货，未达完成）。
- 满赠：98 笔全部可释放（窗口 08-31 结束，远早于切割点）。

### 5.6 功能六：费用归集与预算对账

**解决的问题**：算出该结多少、谁承担、预算够不够。结果存 `result_fee`。

| 项 | 满减（批次1） | 满赠（批次2） |
|---|---|---|
| 实际优惠合计 | 2040 元 | 0 元（满赠无金额优惠） |
| 赠品成本合计 | — | 0（不结算单价，只统计数量） |
| 本次可结算（T-2） | 1995 元 | 0 元 |
| 费用承担方 | 渠道市场部（发票抬头：装瓶厂） | 同左 |
| 结算对象 | 深圳市兴路强商贸有限公司 | 同左 |
| 关联 TPM | `DCN-9926018`（预算预留号 3900088916） | **不走 TPM**（tpm_id=NULL） |
| 协议预算 | 30000 元 | NULL（不挂 TPM） |
| 预算余量 | 28005 元 | — |
| 结算状态 | 待结算 | **按赠品数量统计(不结算单价)** |

- **承担方来源**：TPM 申请单的"费用支付部门"+"发票抬头"（P3：预算层提供承担方，执行层不重复定义）。
- **预算控制**：以 TPM 申请金额（30000）为上限，结算金额与预算对账，余量 = 30000 − 1995 = 28005。
- **满赠结算（业务已决）**：满赠**不走 TPM**，赠品**只按数量统计、不结算单价**——结算基础 = 98 个抱枕（数量），金额记 0、状态"按赠品数量统计(不结算单价)"。原先"赠品单价未确认"的 Gap 已由业务关闭（不再追单价金额）。**不臆造单价**。

### 5.7 功能七：数据质量台账

所有异常、缺口、待确认项逐条记入 `result_quality_issue`，带级别（警告/提示）、原因、证据、所属批次。当前 **7 条**（满减 4 + 满赠 1 + 券 2）：

| 批次 | 异常类型 | 级别 | 订单号 | 说明 |
|---|---|---|---|---|
| 1 满减 | 权益已计未达释放节点 | 提示 | 1012420526026091400090 | 状态=部分发货，未进入 T-2 释放 |
| 1 满减 | 权益已计未达释放节点 | 提示 | 1012420526026091400066 | 状态=部分发货，未进入 T-2 释放 |
| 1 满减 | 权益已计未达释放节点 | 提示 | 1012420526026090500083 | 状态=部分发货，未进入 T-2 释放 |
| 1 满减 | 商品跨系统匹配缺口 | 警告 | （全局） | 满减批次 844 行订单商品未匹配到主数据（多为非可乐品，见 §5.2） |
| 2 满赠 | 赠品已发但无活动明细记录 | 警告 | 1012420526026081900082 | 孤儿赠品单（见下） |
| 3 优惠券 | 优惠券数据已按文本重导，精度阻断解除 | 提示 | （全局） | 使用订单号为完整 22 位文本，券→订单关联命中 1 笔，coupon_ledger 已填 1 条 |
| 3 优惠券 | 券类理论优惠核算暂不可行 | 警告 | （全局） | 仅 1 张测试券、无结构化券规则，按"只报告不猜测"未算券权益/费用，待完整数据 |

> **V1.0 → V1.1 已移除的 4 条**（业务决策关闭）：①"客户匹配缺口"（换 9/22 快照后 customer_id 空值 2→0）；②"赠品结算单价未确认"（业务决定只统计数量、不结算单价）；③"满赠指定商品清单未导出"（18 个雪碧 SKU 已落 `activity_scope`）；④"满赠窗口早于 TPM 计划开始"（满赠改为不走 TPM，问题作废）。

> **孤儿赠品单**：订单 1012420526026081900082 在订单明细里有赠品行（抱枕×1），但活动明细里查不到这单。它没被计入 98 笔权益，单独标记为警告，需查"为什么发了赠品却没登记活动"（仍开放，待业务反馈）。

### 5.8 功能八：批次血缘与可重复计算

当前库里有 **4 个导入批次 + 3 个计算批次**（批次 4 是主数据刷新批，不产生计算批次）：

| 导入批次（raw_import_batch） | batch_code | operator | 计算批次（result_calc_batch） | 说明 |
|---|---|---|---|---|
| 1 | `KM-XLQ-MJ-20260831-20260917` | 小凡 | 1 | 满减（含商品/客户 9/14 主数据） |
| 2 | `KM-XLQ-MZ-20260819-20260831` | 满赠接入 | 2 | 满赠（追加） |
| 3 | `KM-XLQ-YHQ-20260909-20260912` | 优惠券接入 | 3 | 优惠券台账（追加，仅填 coupon_ledger） |
| 4 | `KM-XLQ-CUST-REFRESH-20260922` | 小凡 | —（无） | 客户主数据 9/22 快照补登血缘（不重算） |

- 每次计算生成一个 `result_calc_batch`（计算日、规则版本、输入批次、操作人），所有 RESULT 表都挂 calc_batch_id——任一结论可反查到"哪个计算批次、基于哪个导入批次"。
- 规则口径存 `rule_catalog` 并带版本（满减权益重算 v1 / 满赠权益重算 v1 / T-2 释放节点 v1），不写死在代码里——规则变了就加新版本，旧结果仍可复现。
- 脚本**幂等**：重跑会先按活动名/批次/operator 清理本批旧数据再重算，不会重复累积。**满减脚本会重建整个库**（清掉满赠/券，需再依次重跑）；满赠、优惠券脚本只在现有库上**追加**。

---

## 6 数据现状快照（2026-09-22）

### 6.1 总量

| 表 | 行数 | | 表 | 行数 |
|---|---|---|---|---|
| order_header 订单头 | 2925 | | result_entitlement 权益 | 234 |
| order_line 订单行 | 59631 | | result_release_candidate 释放候选 | 234 |
| customer 客户 | 2292 | | result_fee 费用 | 2 |
| product 商品 | 9129 | | result_quality_issue 质量台账 | 7 |
| activity 活动 | 2 | | result_calc_batch 计算批次 | 3 |
| activity_scope 活动范围 | 30 | | rule_catalog 规则目录 | 3 |
| order_activity 订单活动 | 234 | | coupon_ledger 优惠券台账 | 1 |
| fulfillment 履约 | 2925 | | raw_import_batch / raw_file | 4 / 12 |
| tpm_application TPM | 1 | | dealer_platform | 1 |

> 24 张表里 **21 张已填充**，3 张为空占位（`cross_mapping` / `std_field_mapping` / `std_quality_check`）。

外键违例：**0**。

### 6.2 满减核算结果（批次 1）

- 活动订单 136 笔；理论权益合计 = 平台实际优惠合计 = **2040 元**；一致性 **136/136 全部一致**。
- T-2 可释放 **133 笔（1995 元）**，暂不可释放 3 笔（部分发货，45 元）。
- 预算 30000，余量 28005，状态"待结算"。

### 6.3 满赠核算结果（批次 2）

- 活动订单 98 笔；**应赠 98 = 实赠 98**，一致性 **98/98 全部一致**。
- T-2 可释放 **98 笔（全部）**。
- 金额优惠 0；结算基础 = 98 个抱枕；**业务已定按赠品数量统计、不结算单价**（`result_fee.settle_status` = "按赠品数量统计(不结算单价)"，`gift_cost_total` = 0）。满赠不走 TPM（`tpm_id` = NULL）。

### 6.4 优惠券台账（批次 3）

- `coupon_ledger` 已接入 **1 条**：券号 `202609091700313431`（test1），面额 200，状态"已使用"，使用订单号 `1012420526026091000081`。
- 券→订单关联**命中 1 笔**（`order_header` 中 order_id=713，状态"已完成"，下单 2026-09-10 16:18:49）——精度阻断已解除。
- **券类理论优惠核算暂未做**：本批仅 1 张测试券、无结构化券规则（门槛/面额/适用商品），按"只报告不猜测"未建券活动、未算 entitlement/fee，待平台提供真实券活动配置与全量领用数据后再核算。

### 6.5 三批合并

- 权益记录 234（满减 136 + 满赠 98），全部"一致"。
- 费用记录 2（满减一条 2040/可结算 1995；满赠一条 0/按数量统计）。
- 质量台账 **7 条**（满减 4 + 满赠 1 + 券 2）。

---

## 7 操作说明

### 7.1 环境与文件位置

| 项 | 路径 |
|---|---|
| 数据库文件 | `数据底座/第三阶段数据库设计/mvp/ec101_mvp.db` |
| 建表 DDL | `mvp/ddl/ec101_mvp_sqlite.sql` |
| 读取器 | `mvp/scripts/readers.py`（按文件头魔数判格式；2026-09-22 修复 OOXML 自闭合分支前置的正则缺陷） |
| 接入脚本 | `ingest_manjian.py`（重建+满减）、`ingest_manzeng.py`（追加满赠）、`ingest_coupon.py`（追加优惠券台账） |
| 修正脚本 | `fix_manzeng_tpm_fee.py`（满赠去 TPM/费用改数量口径）、`fix_manzeng_scope.py`（18 指定商品落 activity_scope）、`fix_customer_reread.py`（修 readers.py 后定点重灌客户描述列）、`fix_customer_refresh.py`（客户主数据换 9/22 快照）、`fix_lineage_cust_refresh.py`（为客户 9/22 快照补登 RAW 血缘批次 4） |
| 探查/诊断脚本 | `probe_manjian.py`、`probe_manzeng.py`、`probe_manzeng2.py`、`probe_custtype.py`、`probe_rawxml.py`、`probe_blast.py`、`probe_scope18.py`、`diag_prod_match.py`、`doc_sync_snapshot.py`（生成本文档对账快照） |
| 接入报告 | `mvp/ingest_report.txt`（满减）、`ingest_report_manzeng.txt`（满赠）、`ingest_report_coupon.txt`（优惠券） |
| 核验报告 | `mvp/verify_db.txt`（满减）、`verify_mz.txt`（满赠+满减）、`verify_coupon.txt`（优惠券）、`verify_align.txt`（对齐核验） |
| 现状快照 | `mvp/scripts/doc_sync_snapshot.txt`（24 表行数 + 关键结论的只读导出，本文档对账依据） |
| 源数据 | `快马-兴路强-试点/`（满减/满赠/优惠券子目录） |

运行环境：Python 3（脚本仅用标准库 + SQLite，无需额外安装第三方包）。

### 7.2 用 Navicat 打开查看（推荐方式）

**前提**：Navicat 必须是 **Premium** 或 **for SQLite** 版本（纯 for MySQL 版打不开 SQLite）。

**步骤**：
1. （建议）先复制一份副本再看：把 `ec101_mvp.db` 复制改名为 `ec101_mvp_view.db`，用副本看，原库留作准，防手滑改坏。
2. 打开 Navicat → 左上角「连接」→ 选 **SQLite**（不是 MySQL）。
3. 新建连接窗口：
   - 连接名：随意，如 `EC101-MVP`
   - 类型：选「**现有的数据库文件**」（不要选"新建数据库"）
   - 数据库文件：点 `...` 浏览到 `…\mvp\ec101_mvp.db`（或副本）
   - SQLite 不用填主机/端口/密码
4. 确定 → 双击连接打开 → 左侧展开 24 张表，双击表名看数据，点「查询」写 SQL。

**打开后建议先看这几张表**：

| 表 | 应该看到 |
|---|---|
| `activity` | 2 行：可口可乐满减（挂 TPM 1）+ 满赠优惠（tpm_id 为空，不走 TPM） |
| `result_entitlement` | 234 行；consistency 全"一致"；满赠行（calc_batch_id=2）gift_qty_entitled/actual=1、金额列=0 |
| `result_fee` | 2 行：满减 2040/可结算 1995/状态"待结算"；满赠 金额 0/状态"按赠品数量统计(不结算单价)" |
| `coupon_ledger` | 1 行：test1 券，面额 200，使用订单号 1012420526026091000081 |
| `result_quality_issue` | 7 行：4 行 calc_batch_id=1（满减）、1 行=2（满赠孤儿赠品单）、2 行=3（券） |
| `order_header` / `order_line` | 2925 / 59631 行 |

**常用核验 SQL**（在 Navicat「查询」里跑）：

```sql
-- 各批权益一致性总览（满减=1、满赠=2；券批 3 无权益行）
SELECT calc_batch_id, consistency, COUNT(*) AS 单数
FROM result_entitlement
GROUP BY calc_batch_id, consistency;

-- 满赠：应赠 vs 实赠（赠品口径，金额列为0）
SELECT COUNT(*) 单数,
       SUM(gift_qty_entitled) 应赠,
       SUM(gift_qty_actual)   实赠,
       SUM(theoretical_benefit) 理论金额,
       SUM(platform_actual_benefit) 实际金额
FROM result_entitlement WHERE calc_batch_id = 2;

-- 费用结算与预算
SELECT a.activity_name, f.actual_discount_total 实际优惠,
       f.settle_amount 可结算, f.budget_amount 预算,
       f.diff_amount 余量, f.settle_status 状态
FROM result_fee f JOIN activity a ON a.activity_id = f.activity_id;

-- 质量台账（Gap 清单）
SELECT calc_batch_id, level, issue_type, order_no, reason
FROM result_quality_issue ORDER BY calc_batch_id, issue_id;

-- 追溯某订单：从订单号一路查到权益
SELECT oh.order_no, oh.order_status, a.activity_name,
       oa.platform_actual_benefit 平台优惠, oa.gift_qty_actual 实赠,
       e.consistency 一致性, e.theoretical_benefit 理论权益
FROM order_header oh
JOIN order_activity oa ON oa.order_id = oh.order_id
JOIN activity a          ON a.activity_id = oa.activity_id
LEFT JOIN result_entitlement e ON e.order_activity_id = oa.order_activity_id
WHERE oh.order_no = '1012420526026082900098';
```

### 7.3 重新生成 / 追加数据（脚本运行）

> ⚠️ 运行脚本会**写库**。查看数据用 §7.2 的 Navicat 只读方式即可；只有需要重算时才跑脚本，且建议先备份 `.db` 文件。

**顺序不能反**：

```bash
cd "数据底座/第三阶段数据库设计/mvp/scripts"

# 第 1 步：重建库 + 接入满减（会按 DDL 重新建表，清空后装入满减）
python ingest_manjian.py

# 第 2 步：在现有库上追加满赠（不重建，幂等）
python ingest_manzeng.py

# 第 3 步：在现有库上追加优惠券台账（不重建，幂等）
python ingest_coupon.py
```

- `ingest_manjian.py` 会**从 DDL 重建整个库**——所以重跑它会清掉满赠/优惠券数据，必须再依次跑 `ingest_manzeng.py`、`ingest_coupon.py`。
- `ingest_manzeng.py` / `ingest_coupon.py` 是**追加 + 幂等**：重跑会先按活动名/批次码/operator 清理本批旧数据再重算，不会重复累积；对与满减重叠的订单用"存在即跳过"复用。
- 满赠的两处业务修正（去 TPM/费用改数量口径、18 指定商品落范围）由 `fix_manzeng_tpm_fee.py`、`fix_manzeng_scope.py` 落地；客户主数据 9/22 快照刷新与 readers.py 修复后的定点重灌由 `fix_customer_refresh.py`、`fix_customer_reread.py` 落地——这些是**一次性修正脚本**，常规重算无需再跑。
- 每次运行会刷新报告文件 `ingest_report*.txt`；脚本退出码 0 且末尾 `FK violations: []` 表示成功。

### 7.4 只读查看 vs 修改的风险

1. **别在 Navicat 里改数据。** 这个库是脚本生成的结果库，手改后会和 `ingest_report*.txt`、`verify_*.txt` 里的核验数字对不上；真要重来，重跑脚本会覆盖你的改动。要看就只读地看（或用副本）。
2. **长单号在 Navicat 里是完整文本、不会截断**（库里订单号按 TEXT 存，P8 原则）。但如果从 Navicat **导出到 Excel**，长数字又会被 Excel 变成科学计数法或截断——导出时要把该列设成"文本"格式。这正是优惠券"使用单号"那个 Gap 的同源问题。
3. **路径含中文/空格**：一般 Navicat 能处理；若老版本连接报错，把 `.db` 复制到纯英文无空格路径（如 `D:\ec101\`）再连。

---

## 8 已知 Gap 与待业务确认事项

V1.0 列的 7 项 Gap，到 V1.1 已**关闭 5 项、仍开放 2 项**。对接人参考：满减配置来源 = 江列涛（江总，微信）；系统性需求 = 林楷森。

### 8.1 仍开放（2 项，均在质量台账）

| # | Gap | 级别 | 现状 / 影响 | 下一步 |
|---|---|---|---|---|
| 1 | **孤儿赠品单 1012420526026081900082** | 警告 | 订单明细有赠品行（抱枕×1），但活动明细查不到这单，未计入 98 笔权益 | 查平台为何该单发了赠品却没登记活动参与 |
| 2 | **券类理论优惠核算暂不可行** | 警告 | 本批仅 1 张测试券（test1/面额 200），无结构化券规则（门槛/面额/适用商品）；台账已接入、券→订单已命中，但**未算券权益/费用** | 待平台提供真实券活动配置 + 全量领用数据后再核算（按"只报告不猜测"，不臆造规则） |

> 另有 3 条满减"权益已计未达释放节点"（提示级，订单状态=部分发货）和 1 条"商品跨系统匹配缺口"（警告级）属常态观察项，非待确认 Gap，详见 §5.7。

### 8.2 已关闭（5 项，V1.0 → V1.1）

| 原 Gap | 关闭方式 |
|---|---|
| 赠品结算单价未确认 | ✅ **业务已决**：满赠按赠品数量统计、不结算单价（`result_fee.settle_status`="按赠品数量统计(不结算单价)"，金额记 0） |
| 商品跨系统匹配缺口（作为待确认项） | ✅ **已澄清**：未匹配的约 1115 行多为非可乐品；`cross_mapping` 只需覆盖可乐系商品，非缺陷（见 §5.2） |
| 满赠窗口早于 TPM 计划开始 | ✅ **业务已决**：满赠改为不走 TPM（`tpm_id`=NULL），窗口冲突问题作废 |
| 满赠指定商品清单未导出 | ✅ **已补充**：18 个雪碧 SKU 已落 `activity_scope`（范围行 13→30） |
| 客户匹配缺口（2 单 customer_id 为空） | ✅ **已解决**：客户主数据换 9/22 快照（2273→2292）并回填，customer_id 空值 2→0 |
| 优惠券使用单号精度已损 | ✅ **已解除**：平台按文本重导，券→订单命中 order_id=713，`coupon_ledger` 已填 1 条（券核算本身仍开放，见 §8.1 #2） |

> 处理原则：缺失的退款终态、赠品单价、费用承担方等，**只报告、不猜测**；源数据时间早于活动开始，判"未验证"而非"零参与"。

---

## 9 从 SQLite 到生产 MySQL 的映射注意

本库是 **MVP 阶段的 SQLite 本地库**，用于快速验证模型与核算逻辑。生产环境目标是 MySQL。迁移时注意：

| SQLite（当前） | MySQL（生产） | 说明 |
|---|---|---|
| `NUMERIC`（金额，入库 round 2 位） | `DECIMAL(12,2)` | 金额必须用定点小数，不能用 FLOAT/DOUBLE（避免精度误差） |
| `TEXT`（日期时间 ISO 字符串） | `DATETIME` 或保持 `CHAR(19)` | 当前按字符串存 ISO 格式，便于字典序比较；生产可用 DATETIME |
| `INTEGER`（布尔 0/1） | `TINYINT(1)` | |
| `TEXT`（长编号/单号） | `VARCHAR(n)` | **绝不能改成数值类型**，否则长 ID 精度丢失（P8） |
| `INTEGER PRIMARY KEY AUTOINCREMENT` | `BIGINT AUTO_INCREMENT PRIMARY KEY` | |
| `PRAGMA foreign_keys = ON` | InnoDB 外键（默认强制） | MySQL 外键默认生效 |
| `UNIQUE(...)` 复合唯一键 | 同名唯一索引 | 业务键约束需保留（如 order_header 的 平台+订单号） |

迁移工作还包括：把脚本里的映射/重算逻辑沉淀为存储过程或 ETL 作业、补全 STANDARD 层的 `std_field_mapping`/`std_quality_check`、接入第二/第三平台验证模型复用性（只加映射、不改核心关系）。

---

## 10 附录

### 10.1 术语表

| 术语 | 全称 / 含义 |
|---|---|
| EC101 | 本项目代号（太古促销费用数据底座建设） |
| MVP | Minimum Viable Product，最小可行版本——先跑通核心链路，预留项后补 |
| TPM | Trade Promotion Management，贸易促销管理；这里指 SAP 里的促销申请单（预算/审批），单号形如 DCN-9926018 |
| DCN | TPM 促销申请单的编号前缀 |
| T-2 | 费用释放节点口径：订单已完成，且下单时间 ≤ 计算日往前推 2 天的 00:00:00 |
| SKU | Stock Keeping Unit，库存量单位，即一个具体商品规格 |
| UC | Unit Case，标准箱（可口可乐计量单位） |
| WBS | Work Breakdown Structure，工作分解结构（SAP 预算/项目层级标识） |
| TG | Target Group，目标组（TPM 里的目标客户群，形如 TG-…） |
| SXD | 舟谱平台的权威订单号前缀（本 MVP 未涉及舟谱，列为背景术语） |
| sell-in / sell-out | 经销商进货（拿货）/ 终端动销（卖出）；EC101 订单汇总属 sell-in，预留 |
| RAW / STANDARD / CORE / RESULT | 四层数据模型：原始层 / 标准层 / 业务事实层 / 应用结果层 |
| OOXML / BIFF / HTML | 三种文件真实格式：Office Open XML（.xlsx，zip+XML）/ 老式 Excel 二进制（.xls）/ 网页表格 |
| 魔数（magic bytes） | 文件头几个字节，用来判定真实格式，比扩展名可靠 |
| IEEE-754 | 浮点数标准；双精度只有约 15-17 位有效数字，长编号当数字存会丢精度，故一律按字符串 |
| FK（外键） | Foreign Key，表间关联约束；"FK 违例=0"指所有关联都指向真实存在的记录 |
| 权益（entitlement） | 订单按活动规则应得的优惠（金额或赠品数） |
| 一致性 | 太古规则重算的理论权益 与 平台实际给的优惠 是否相符（一致/差异） |
| 承担方 | 促销费用由谁出（来自 TPM 的费用支付部门 + 发票抬头） |
| 幂等 | 同一脚本重复运行结果不变（先清理本批旧数据再重算，不重复累积） |

### 10.2 关联文档与工具

| 名称 | 位置 | 关系 |
|---|---|---|
| EC101 数据底座建设方案 V1 | `第三阶段数据库设计/EC101数据底座建设方案 V1.docx` | 项目总体方案（PRD 来源） |
| EC101 逻辑数据模型设计说明 V1 | `第三阶段数据库设计/EC101逻辑数据模型设计说明V1.md` | 本库的逻辑设计依据（四层模型、八原则、实体清单） |
| MVP 薄物理模型 DDL | `mvp/ddl/ec101_mvp_sqlite.sql` | 本库的建表脚本（物理结构权威来源） |
| 促销闭环验证器 | `第三阶段数据库设计/ec101-promotion-closure-validator/` | 配套的文件级验证工具，与本库共享业务规则口径 |
| 平台规则 / 字段字典 / 验证规则 | validator 的 `platform-rules/`、`references/` | 活动规则标准、验证规则、结论判定、字段字典等业务规则文档 |

### 10.3 文档维护

- 本文档对应数据库状态截至 **2026-09-23**，版本 **V1.2**：满减 + 满赠 + 优惠券台账**三批**接入完成；含客户主数据换 9/22 快照（2273→2292）、满赠去 TPM/费用改数量口径/18 指定商品落范围、readers.py OOXML 正则缺陷修复后定点重灌客户描述列、以及为客户 9/22 快照**补登 RAW 血缘批次 4**（raw_import_batch 4 / raw_file 12）等修正。所有数字以 `scripts/doc_sync_snapshot.txt` 只读快照为准。
- 数据库重跑、新平台接入、Gap 确认后，应同步更新 §6 现状快照与 §8 Gap 清单。
- 表结构变更（DDL 修改）后，应同步更新 §4 数据字典。

---

*本文档由数据底座接入结果自动整理，所有数字均来自 `ec101_mvp.db` 的实际查询与 `ingest_report*.txt` / `verify_*.txt` 核验记录，可复现。*
