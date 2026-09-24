# 舟谱-羿柏 第二平台接入实施计划（SXD/XD 两层版）

> **本文档下方 `## Context` 起为最初接入轮（2026-09-23）的原始计划，保留不改以存档。**
> 实施后又做了两轮调整，权威现状见本节；正文中已变更处加了「09-24 更新」内联标注。

## 更新记录（实施后补记）

**名词**：SXD = 销售订单号（客户前端下单口径，前缀 `SXD`）；XD = 履约/出库单号（系统履约口径，前缀 `XD`，退货前缀 `TD`）。

### 轮次 A — 2026-09-24 满赠源去重叠
- **改了什么**：满赠 SXD 源文件窗口 `0821-0823` 与 `0819-0821` 在 08-21 交叉重叠 → 换成 **`0822-0823`**，三窗口连续无重叠（0819-0821 / 0822-0823 / 0824-0826）。
- **怎么做的**：teardown RESULT（`ingest_result_zhoupu.py --teardown-only`）→ 重灌 CORE → 重建 RESULT。
- **结果**：**核算数字全不变**（属逻辑 no-op——加载器早已按 `order_no` 跨文件去重 + `INSERT OR IGNORE`，重叠从未污染 DB），仅 **RAW 血缘**记录更正为真实加载文件。`calc_batch` 8→9。双验证绿（CORE 43 / RESULT 21），兴路强 Δ=0。
- **副产品修复**：`verify_zhoupu.py` 硬编码 `product_id` 崩溃（重灌后自增 id 漂移）；`ingest_result_zhoupu.py` 新增 `--teardown-only`（重灌 CORE 前先拆 RESULT，避 FK 崩溃）。
- **备份**：`ec101_mvp.db.bak-pre-manzeng-update-20260924`。

### 轮次 B — 2026-09-24 XD 驱动结算改造（范围扩张·最重要）
- **用户指示**：**以 XD 订单状态 `已完成` 进行结算，不管是否关联 SXD**（SXD 只代表"用户下过单"，履约完成才是结算触发点）。
- **改了什么（新增第三条路径）**：原计划订单只有「SXD→XD」两条链；现新增 **XD-only 订单**——没有任何 SXD 的"下游订单编号"指向它、但自身已履约的 XD 单据，也建成一等 `order_header`：
  - `order_no ← XD.单据`（XD号）；`order_source = 'XD履约(无SXD)'`；`order_time ← XD.单据时间`。
  - `customer_id`：XD 文件自带"客户名称+客户助记码"两列 → 直接拼复合键 `客户名称|助记码` 命中 customer（**无需过桥**，命中率 2507/2508=100%，唯一 miss 是"测试|cs"测试数据）。
  - `order_line`：`product_id ← XD.商品id`（=商品唯一序号）；`pre_discount_amount ← XD.下单金额`（SXD 无此单，金额取自 XD）。
  - `fulfillment`：同样为 XD-only 单建一行（原计划只对 SXD-hit 建）。
  - 过滤：只收 `单据` 以 `XD` 开头的行；排除表尾"合计"总计行、`TD` 退货单、`客户名称=='测试'`。
- **结果（已落库·live 核验）**：
  - CORE：`order_header` 4053→**6697**（+2644）；`order_line`→**76055**；`fulfillment`→**6118**。
  - RESULT 满赠：合格 96→**142** / 应赠 90→**135** / 一致 82→**99** / 差异 14→**43** / 实赠抱枕 82→**100**（= 82 SXD-linked + **18 XD-only**，闭合了历史"~100 抱枕"缺口）。
  - RESULT 返券：**不变** 45 单×15=675 元。
  - `release` 候选 133→**179**；`calc_batch`→**11**。
  - 兴路强 8 表 Δ=**0**；验证 CORE 48/0、RESULT 25/0。
- **范围相对原计划的变化**：原"决策 3 / 本轮明确不做"写的 **"RESULT 层本轮不做" 已作废**——返券 + 满赠 RESULT 现已完成核算并落库。
- **备份**：`ec101_mvp.db.bak-pre-xd-driven-20260924`。
- **开放项（需业务确认）**：XD-only 订单来源须舟谱（林楷森/江总）确认——XD 的"综合订单号"列全空，XD-only 单与被 SXD 引用的 XD 在单号层面不相交，理论上存在**重复计费**风险；本轮按"XD 即权威履约"落地并计数，未臆造关联。

## Context（为什么做）

EC101 促销费用数据底座的 MVP 库 `mvp/ec101_mvp.db` 目前只接入了第一个平台 **快马-兴路强**（满减/满赠/优惠券已跑通，24 表中 21 张有数据，STANDARD 层 `std_field_mapping`/`std_quality_check` 仍为 0 行）。现在接入 **第二个平台 舟谱-羿柏**，验证底座的多平台承载能力，并首次把 STANDARD 层填起来。

本轮五个已确认决策：
1. **共库追加**：舟谱作为新的 `dealer_platform=羿柏/舟谱` 写进同一个 `ec101_mvp.db`；兴路强数据按 `dealer_platform_id` 隔离，完全不动。
2. **配置驱动 + 薄适配**：把 skill 已算好的舟谱字段映射灌进 `std_field_mapping` 表作为映射真源，通用加载器读表落库；舟谱特有解析怪癖放薄适配层。
3. **范围＝主数据 + 订单两层落地**：落 客户/商品主数据 + **SXD 订单(表头+行) + XD 履约(fulfillment)** + RAW 血缘进 CORE 表。**返券核算、满赠核算、销售明细、活动明细、退货冲回、RESULT 层 本轮都不做。**
   > ⚠️ **09-24 更新（部分作废）**：返券核算 + 满赠核算 + RESULT 层 **已在轮次 B 完成并落库**（见顶部「更新记录」）；且订单新增第三条路径 **XD-only**（无 SXD 指向的已履约 XD 单也建 order_header/line/fulfillment）。销售明细、退货冲回核算 仍不做。
4. **订单两层都落（用户确认）**：`order_header`/`order_line` ← SXD（保住促销优惠经济），`fulfillment` ← XD（权威完成状态），客户匹配走 SXD→XD→助记码 桥（见下）。
5. **订单状态以 XD 为准（用户指示）**：`order_header.order_status` 取 XD 履约状态（权威口径），**不取 SXD 状态**；无 XD 命中的单回退用 SXD 状态（详见数据事实与步骤 3）。
   > ⚠️ **09-24 更新（口径升级）**：用户进一步指示 **以 XD 订单状态 `已完成` 触发结算，不管是否关联 SXD**（SXD 只代表"用户下过单"）。据此新增 XD-only 路径，`order_no` 可为 XD 号、`order_source='XD履约(无SXD)'`；结算/release 以 XD 履约完成为准。详见顶部「更新记录·轮次 B」。

**主数据主键（用户确认，因源数据仍在开发中）**：
- 客户 `platform_customer_no = 客户名称 + "|" + 助记码`（**组合键**；不用"客户唯一序号"，因开发期该序号可能不稳定）。分隔符 `|` 由我设定，可按需调整。
- 商品 `platform_product_no = 商品唯一序号`（确认不变；"编号"列为空不可用）。**已核验：商品唯一序号 = XD.商品id（同一个键，XD.商品id 命中商品档案.商品唯一序号 1699/1701=99.88%）；SXD 表无"商品id"列、只有"商品条码"（命中小单位条码 898/899=99.9%）。订单行按用户选定走"过 XD 取商品id"（见图6）。**

**订单两层模型（已逐列字节级核验）**：
- **SXD** = 客户前端下单生成的销售订单号（下单口径，全量 6,169）；**XD** = SXD 下发后系统履约生成的下游出库单号（履约口径）。
- **链接**：`SXD.下游订单编号 = XD.单据`，已映射的一对一（6,099/6,169 有 XD，70 个未生成）。链接是**单向**的——XD 侧本可回指 SXD 的"综合订单号"列全空，无法 XD→SXD 反查。
  > ⚠️ **09-24 更新（新增第三条路径）**：除「SXD→XD」外，还有一批 **XD-only 单据**（自身已履约、但没有任何 SXD 的"下游订单编号"指向它）。轮次 B 起，这些 XD-only 单也建成一等 `order_header`（`order_no`=XD号、`order_source='XD履约(无SXD)'`），客户直接靠 XD 自带的"客户名称+助记码"两列命中（无需过桥）。详见顶部「更新记录·轮次 B」。
- **两层装不同语义**（这是必须分两层的根因）：

| 数据 | SXD（22 列） | XD（63 列） |
|---|---|---|
| 优惠前金额 / 实际金额 / 实际单价 | ✅ 第 18-21 列 | ❌ 无 |
| 支付方式（误标在"支付时间"列） | ✅ 第 12 列 | — |
| 下游订单编号（→XD） | ✅ 第 15 列 | — |
| 客户助记码 / 老板电话 / 客户片区 / 客户等级 | ❌ 无（仅客户名称/片区/渠道） | ✅ 第 16/18/20/22 列 |
| 订单状态 + 结款状态（权威完成口径） | 仅 SXD 状态（第 14 列） | ✅ 第 46/47 列 |
| 出库/签收/结算数量金额、退货结算数量 | ❌ 无 | ✅ 第 31/32/33/51 列 |

- **客户匹配死结的解法**：客户复合键需要"助记码"，但 **SXD 没有助记码，只有 XD 有**。故订单连客户必须过桥：`SXD.下游订单编号 → XD.单据 → 取 XD.客户助记码 → 配客户档案"名称|助记码"复合键`。这正是分析文件 r23 验证过的口径（客户档案─[老板电话/助记码+片区]─XD，1,008/1,008 客户、4,134/4,134 订单命中）。

已字节级核验的数据事实：
- **订单状态 SXD vs XD（已核验·支撑决策 5）**：试点 4,054 个 distinct SXD 订单中，3,474 个有下游 XD 且命中——其中 **3,338 单两层状态一致**，**136 单 SXD 标"已完成"但 XD 实为"待签收"(115)/"待出库"(21)**（SXD 偏乐观，XD 才是真实履约口径）→ 故 `order_status` 取 XD。**580 单拿不到 XD 状态**（576 单的下游 XD 不在本轮两个 XD 文件窗口内 + 4 单无下游编号）→ 回退用 SXD 状态并计数（`order_status` 是 NOT NULL，不能留空）。
- 权威源目录 = `第三阶段数据库设计\舟谱-羿柏-试点`（用户指定）。phase-2 的 `第二阶段验证\舟谱-羿柏` 不含满减销售明细，不是本轮源。
- 舟谱表头在 **第 4 行**（活动明细在第 3 行），第 1–3 行是 标题/导出时间/筛选条件；兴路强表头在第 1 行。
- **本轮加载文件清单（12 个）**：主数据 2（根目录 客户档案-20260914 / 商品档案-20260914）+ SXD 订单 8（满减 5：订单明细 0826-0827/0828-0830/0831-0902/0903-0905/0906-0908；满赠 3：满赠订单明细 0819-0821/**0822-0823**/0824-0826）+ XD 履约 2（满减 订单明细-XD-20260826-20260908；满赠 满赠XD20260819-20260826）。**不加载**：销售明细 2、活动明细 1、满赠/下主数据副本 2。
  > ⚠️ **09-24 更新（满赠源去重叠·轮次 A）**：满赠中间窗口原为 `0821-0823`，与 `0819-0821` 在 08-21 交叉 → 已换为 **`0822-0823`**，三窗口连续无重叠。核算数字未变（加载器早按 `order_no` 去重），仅更正 RAW 血缘。
- `readers.py` 两处限制：① `read_table` 无 `header_row` 参数（永远把第 1 行当表头）——读舟谱任何文件的硬前提；② `_read_ooxml` 第 131 行 rels 正则假设 `Id=` 在 `Target=` 之前，而舟谱部分文件是 **Target-first** → `KeyError:'xl/'`（第 135 行已 `lstrip('/')`，前导斜杠不是问题；唯一根因是 131 行正则顺序依赖）。两处都修。
- 舟谱"满减"实为 **288 返 15 返券**（答案 C），本轮不核算；**暂不算退货冲回**（答案 C），故 `order_line.return_qty` 留空（注：`fulfillment.return_qty` 仅原样落 XD.退货结算数量，是数据落地不是冲回核算）。
- 舟谱 skill 映射 = `outputs\缇挎煆\run.json`（442949 字节，`缇挎煆` 是 `羿柏` 的 mojibake）；seed 脚本按 `platform=='舟谱'` 字段选取，不靠目录名。**run.json 基于 phase-2，可能不含 XD 列映射 → 需手工补 XD 侧字段。**
- 根目录 `客户档案-20260914.xlsx`/`商品档案-20260914.xlsx` 与 `满赠\客户档案.xlsx`/`满赠\商品档案.xlsx` 字节相同（重复副本）——主数据只加载一次。

## 图示：表关联 + 主数据主键（重点·用户要求）

### 图 1 — 五张业务源表怎么连（XD 是枢纽）

```
  ┌──────────────┐         ┌──────────────┐
  │  客户档案     │         │  商品档案     │
  │ 名称/助记码   │         │ 唯一序号/条码 │
  │ 老板电话/片区 │         │ 单位换算      │
  └──────┬───────┘         └──────┬───────┘
         │ 老板电话 / 助记码+片区    │ 商品唯一序号 / 小单位条码
         │ (1008/1008客户·4134单)   │ (1700/1701 SKU·品牌100%)
         ▼                         ▼
  ┌─────────────────────────────────────────────┐
  │              XD 履约明细 (枢纽)               │
  │  单据 = XD号 · 客户助记码 / 老板电话 / 片区     │
  │  订单状态 / 结款状态 (权威完成口径)            │
  │  签收 / 出库 / 结算数量 · 退货结算数量         │
  └─────────────────────────────────────────────┘
         ▲  单据 = SXD.下游订单编号  (1对1·6099/6169有XD·70个未生成)
         │
  ┌──────┴──────────────────┐    关联单据编号 (按券张数拆逗号)
  │      SXD 下单明细        │ ◀────────────────────────┐
  │  订单编号 = SXD号        │    48条→拆出51个独立SXD    │
  │  优惠前/实际金额·实际单价 │                         ┌─┴──────────┐
  │  支付时间 (实为支付方式)  │                         │优惠券活动明细│
  │  客户名称 (✗ 无助记码!)   │                         │  (券核销)   │
  └─────────────────────────┘                         └────────────┘
```

> 一句话：**XD 是中心**——客户、商品、SXD 都向它对齐；优惠券指向 SXD，SXD 再经"下游订单编号"指向 XD。

### 图 2 — 主数据主键怎么构造

```
  customer 主键 = 组合键 (开发期"客户唯一序号"不稳定 → 用户确认改用 名称+助记码)
  ┌──────────────────────────────────────────────────────────────┐
  │ 客户档案.客户名称 = "张三便利店" ┐                              │
  │ 客户档案.助记码   = "ZS001"     ├─▶ platform_customer_no        │
  │                                ┘    = "张三便利店|ZS001"        │
  │ 注1: 分隔符 "|" 由我设定, 可改 (顺序也可换成 助记码|名称)         │
  │ 注2: 客户编码列填充率仅 0.4% → 不能当主键                        │
  │ 注3: 助记码为空 → 退化为 "张三便利店|" (此时唯一性靠名称兜底)      │
  └──────────────────────────────────────────────────────────────┘

  product 主键 = 商品唯一序号 (用户确认; "编号"列为空不可用)
  ┌──────────────────────────────────────────────────────────────┐
  │ 商品档案.商品唯一序号 = "1025" ──▶ platform_product_no = "1025" │
  │ ★已核验: 商品唯一序号 = XD.商品id (同一个键, 命中 1699/1701)     │
  │ 订单行回连(用户选定): SXD行 →过XD→ 商品id → product (见图6)     │
  │   回退: 无XD的行才用 SXD.商品条码 = product.barcode(小单位条码)  │
  └──────────────────────────────────────────────────────────────┘
```

### 图 3 — 客户匹配过桥（死结的解法·最关键）

```
  死结: 客户复合键需要"助记码", 但 SXD 订单没有助记码 (只有 XD 有)
  解法: 借 SXD→XD 的链接, 从 XD 把"助记码"取回来再配复合键

   SXD 订单行                XD 履约行 (桥)            customer 表
  ┌────────────┐ 下游订单编号 ┌────────────┐ 客户助记码 ┌──────────────────┐
  │订单编号=SXD │═══════════▶│单据 = XD号  │══════════▶│platform_customer_no│
  │客户名称     │ (=XD.单据)  │客户助记码   │ (+客户名称)│ = 客户名称|助记码   │
  │下游订单编号 │            │老板电话/片区│  拼复合键  │                  │
  │✗ 无助记码   │            │            │           │                  │
  └────────────┘            └────────────┘           └──────────────────┘
        │                                                     ▲
        └──────────  拼 "客户名称|助记码" → 命中 customer ───────┘

  回退链 (桥断时·只报告不猜测):
    ① 无下游订单编号 / XD桥查无此单据 → 按"客户名称"匹配 (羿柏内名称唯一才连)
    ② 名称重名歧义 → customer_id 置空 + 记入未决清单, 打印数量交人工
```

### 图 4 — 源文件 → CORE 表 落库映射

```
  源文件 (舟谱-羿柏-试点·表头在第4行)         CORE 表          主键 / 匹配路径
  ────────────────────────────────         ──────────       ──────────────────────
  客户档案-20260914.xlsx          ─────▶   customer    key = 客户名称|助记码
  商品档案-20260914.xlsx          ─────▶   product     key = 商品唯一序号
  SXD订单明细 ×8 (满减5+满赠3)     ─────▶   order_header  order_no=SXD号; order_status←XD(权威·无XD回退SXD)
                                 ─────▶   order_line    product_id ← XD.商品id 过桥(图6)
                                          │             customer_id ← 助记码过桥(图3)
  XD履约明细 ×2 (满减1+满赠1)      ─────▶   fulfillment   order_id ← 经 SXD.下游订单编号
                                                          = XD.单据 回连 order_header
                                                          order_status = XD.订单状态
                                                          completed_at = XD.签收时间
  ──────────────────────────────────────────────────────────────────────────────
  不加载: 销售明细×2 · 活动明细×1 · 满赠/下主数据副本×2
```

> ⚠️ **09-24 更新（图4 补充·轮次 B）**：XD 履约明细新增**第二重角色**——除经 `SXD.下游订单编号` 过桥喂 fulfillment 外，**XD-only 单据**（无 SXD 指向、自身已履约）现直接落 `order_header`(order_no=XD号) + `order_line`(product_id←XD.商品id, pre_discount_amount←XD.下单金额) + `fulfillment`；客户靠 XD 自带"客户名称+助记码"直配复合键（不过桥）。

### 图 5 — CORE 表之间的外键关系（DB 层 ER）

```
  dealer_platform (羿柏/舟谱)
        │
        ├──< customer        (dealer_platform_id FK; UNIQUE 平台+客户编号)
        ├──< product         (dealer_platform_id FK; UNIQUE 平台+商品编号)
        └──< order_header    (dealer_platform_id FK; order_no = SXD号;
                │             downstream_order_no = XD号【本轮新增列】)
                │
                ├──< order_line   (order_id FK→order_header;
                │                  product_id FK→product;
                │                  UNIQUE(order_id, product_id))
                │
                └─── fulfillment  (order_id UNIQUE FK→order_header;
                                   order_status = XD状态)

  跨表匹配 (非 FK·加载时解析后写入外键 id):
    order_header.customer_id ──过桥──▶ customer  (SXD→XD→助记码→ 名称|助记码)
    order_line.product_id    ──过桥──▶ product   (SXD行→XD行→商品id=商品唯一序号; 回退条码)
```

> `──<` = 一对多（crow's foot）；`───` = 一对一。fulfillment 与 order_header 是 1:1（order_id 唯一外键）。

> ⚠️ **09-24 更新（图5 补充·轮次 B）**：`order_header.order_no` **不再恒为 SXD 号**——XD-only 单的 `order_no` 是 **XD 号**，以 `order_source='XD履约(无SXD)'` 区分；这类单同样 1:1 带一行 fulfillment，`downstream_order_no` 为空（它自己就是 XD）。`UNIQUE(dealer_platform_id, order_no)` 仍保证 SXD 号与 XD 号不撞（前缀不同）。

### 图 6 — 订单行怎么找到对应的商品（填 order_line.product_id）

**要解决的问题**：order_line 每行都要填一个 `product_id`（指向 product 表的外键），product 表主键是"商品唯一序号"。但三个事实凑一起，导致不能直接填：
- **SXD 订单文件没有"商品id / 商品唯一序号"这一列**——SXD 每行只有 商品名称 + 商品条码；
- **"商品id"这一列只在 XD 履约文件里**（XD 每行有 商品id、条形码、商品名称）；
- 所以想拿到商品id，必须先从 SXD 跳到 XD 再取回来。**XD 就是那座"桥"。**

**三步过桥（用真实一单 SXD260827000153 走一遍）**：

| 步 | 做什么 | 真实值 |
|---|---|---|
| ① | 在 SXD 里看这一行，取它的"下游订单编号"（这是过桥的钥匙） | 商品=宝矿力500ml*24，条码=6937761805015，下游订单编号=**XD260827000227** |
| ② | 用 `下游订单编号 = XD.单据` 跳到 XD；在该单据下用 `条码 = 条形码` 对上同一件商品，读它的商品id | XD 那行 条形码=6937761805015 → **商品id=262** |
| ③ | 商品id 就是 product 主键（商品唯一序号）；取 product 表里 序号=262 那条记录的内部 id | → 填进 `order_line.product_id` ✅ |

```
SXD行 ──(下游订单编号 = XD.单据)──▶ XD行 ──(同单据内 条码/名称 对上)──▶ 商品id ──▶ product
```

**第②步"行内怎么对上"**：同一个 XD 单据下，先用 `SXD.商品条码 = XD.条形码` 对；若该行条码为空（如赠品），退而用 `SXD.商品名称 = XD.商品名称` 对。

**已核验**：本例 SXD260827000153→XD260827000227 共 16 行，全部经条码命中商品id（16/16）。另抽检 2 单 28/28、16/16 全中；其中一单有一行"珠江原浆"条码为空，靠商品名称也对上并取到商品id（2762）。

**回退链（桥断时·只报告不猜测）**：
1. 该 SXD 无下游 XD，或 XD 里找不到对应行 → 退用 `SXD.商品条码 = product.barcode(=小单位条码)` 直接配 product（已核验 898/899=99.9%）。
2. 仍配不上（赠品：无条码又无名称）→ `product_id` 留空 + 记未匹配清单，打印交人工，不猜、不阻断加载。

## 改动文件清单

| 文件 | 动作 | 说明 |
|---|---|---|
| `mvp/scripts/readers.py` | 改 | ① `read_table(path, header_row=1)` 加参数；② 第 131 行 rels 正则改为顺序无关 |
| `mvp/ddl/ec101_mvp_sqlite.sql` | 改 | `order_header` 增列 `downstream_order_no TEXT`（存 XD 号；供未来重建库时一致） |
| `mvp/scripts/std_mapping.py` | 新建 | 共享：`load_mapping` / `map_rows` / `EC101_TO_CORE`（含 fulfillment 绑定，平台无关，可复用给第三平台） |
| `mvp/scripts/seed_std_mapping_zhoupu.py` | 新建 | 读 skill `run.json` 的 `field_mappings` → 灌 `std_field_mapping`(platform=舟谱)；手工补 XD 侧映射 |
| `mvp/scripts/ingest_zhoupu.py` | 新建 | 舟谱薄适配 + 两层加载（SXD→order_header/line，XD→fulfillment）+ 客户过桥匹配 + RAW 血缘（append，非破坏） |

**DDL 加列说明（重要）**：选项描述提"order_header/fulfillment 各加一列存对方单号"，但经核验**只有 `order_header.downstream_order_no`（=XD号）承载新信息**；fulfillment 的"对方单号"(SXD)已可经 `fulfillment.order_id → order_header.order_no` 取得，无需冗余列。故默认**只加 1 列**。若你要 fulfillment 自描述（不 join 即知 XD/SXD 号），可再加 `fulfillment.upstream_order_no`，批准时告知即可。
- 库已存在兴路强数据，**严禁重建**。加列用 `ALTER TABLE order_header ADD COLUMN downstream_order_no TEXT`（非破坏，兴路强既有行得 NULL，符合"兴路强无 XD"语义）；`ingest_zhoupu.py` 内用 `PRAGMA table_info` 守卫，幂等可重跑。

**复用（不重写）**：
- `mvp/scripts/ingest_manzeng.py`：append 连接（L42 不删库）、幂等清理（L54-75 按 dealer_platform 精确删）、`dealer_platform` SELECT 复用（L93-95）。
- `mvp/scripts/readers.py`：`to_num`（L56-71，已支持 "1箱" 文本取数）、`to_datetime_text`（L41-53）。
- skill：`ec101-promotion-closure-validator/.../scripts/field_mapping.py` 的 `RAW_TO_STANDARD`（L93-99，已含舟谱别名）；`outputs/*/run.json` 的 `field_mappings`。

**严禁**复用 `mvp/scripts/ingest_manjian.py` 的 L48-53（`os.remove(DB)` + 重建）——破坏性建库会抹掉兴路强。

## 实施步骤

### 步骤 0 — 修 readers.py（前置，独立可验）
- `read_table` 增 `header_row=1`：`header = rows[header_row-1]`，`data = rows[header_row:]`；越界返回空。默认 1 → 兴路强零回归。
- 第 131 行改为逐个 `<Relationship>` 解析、Id/Target 分别取（顺序无关）：
  ```python
  rid2target = {}
  for m in re.finditer(r'<Relationship\b[^>]*>', rels):
      tag = m.group(0)
      rid = re.search(r'\bId="([^"]+)"', tag)
      tgt = re.search(r'\bTarget="([^"]+)"', tag)
      if rid and tgt:
          rid2target[rid.group(1)] = tgt.group(1)
  ```
- 验证：读 `满减\舟谱-羿柏-销售明细-20260826-20260908.xlsx`（Target-first）应成功返回数据行；再读兴路强任一文件确认无回归。

### 步骤 0.5 — DDL 加列（非破坏）
- 改 `ec101_mvp_sqlite.sql`：`order_header` 增 `downstream_order_no TEXT`（注释：存 SXD 的下游 XD 号）。
- `ingest_zhoupu.py` 开头守卫式 ALTER（见步骤 3）。验证：`PRAGMA table_info(order_header)` 出现该列；兴路强既有 order_header 行该列为 NULL。

### 步骤 1 — 灌 std_field_mapping（配置驱动真源）
- `seed_std_mapping_zhoupu.py`：glob `outputs/*/run.json`，选 `platform=='舟谱'` 的那份；遍历 `field_mappings`，**只保留 `经销商原始字段` 为真实列名的行**（排除 `—` 与 `Skill计算`，避免 `UNIQUE(platform,module,raw_field)` 撞键）；写入：`platform='舟谱'`, `module=模块`, `raw_field=经销商原始字段`, `ec101_field=EC101标准字段`（`—`→NULL）, `confidence=证据等级`, `is_non_v1=(字段关系=='非V1字段')`, `gap_flag=状态`。
- 幂等：先 `DELETE FROM std_field_mapping WHERE platform='舟谱'`。
- **手工补 XD 侧映射**（run.json 基于 phase-2，大概率缺 XD 列）：至少补 `单据→XD单号`、`客户助记码→客户助记码`、`老板电话→老板电话`、`客户片区→客户区域`、`客户等级→客户等级`、`订单状态→履约订单状态`、`结款状态→结款状态`、`签收时间→完成时间`、`出(入)库时间→出库时间`、`退货结算数量→退货数量`、`条形码→商品条码`。module 用 `订单履约`（与 SXD 的 `订单` 区分）。
- **已知必补别名（已字节级核验·满减/满赠列名不同）**：SXD 数量列 满减叫 `订单数量（大）`、满赠叫 `实际数量` → 都映射到 `订货数量`；SXD 单位列 满减叫 `单位名称（大）`、满赠叫 `单位名称` → 都映射到 `订货单位`。XD 侧 `退货结算数量` 仅满减有、满赠无（满赠该字段留空）。
- **补齐 + 未映射报告**：灌完跑 dry-run，对**每个**待加载文件打印实际表头里未在 std_field_mapping 出现的列，人工补别名直到清单为空（或仅剩确认无需入库的列，如 XD 的成本/毛利/库区/送货员等）。

### 步骤 2 — 通用映射工具 std_mapping.py
- `load_mapping(conn, platform, module) -> {raw_field: ec101_field}`（取 `is_non_v1=0` 且 `ec101_field` 非空）。
- `map_rows(header, rows, mapping) -> [{ec101_field: value}]`（按列名映射，天然容忍满减/满赠同类文件的列序差异）。
- `EC101_TO_CORE`（ec101 标准字段 → CORE 列，平台无关，按目标表分组）：
  - **customer**：客户名称→customer_name, 客户类型→customer_type, 客户等级→customer_level, 客户标签→customer_tag, 客户区域→customer_region, 所属业务员→salesperson_name, 建档时间→created_at, 客户状态→status（`platform_customer_no` 不在此——由薄适配层用 客户名称+"|"+助记码 组合生成）
  - **product**：平台商品编号→platform_product_no, 商品名称→product_name, 商品品牌→brand, 商品目录/品类→category, 商品规格→spec, 商品条码→barcode, 基本单位→base_unit, 箱规→box_conversion, 太古产品代码→swire_product_code（注：舟谱 `platform_product_no` 由薄适配层取 `商品唯一序号`，不走此 1:1 映射；商品唯一序号=XD.商品id）
  - **order_header（SXD）**：订单编号→order_no, 下单时间→order_time, 支付方式→pay_method, 支付状态→pay_status, 下游订单编号→downstream_order_no（新列）, 订单来源→order_source, 订单类型→order_type（注：`order_status` **不在此 1:1 映射**——按决策 5 由薄适配层取 XD.订单状态，无 XD 命中才回退 SXD.订单状态；SXD"订单状态"仍需读出作回退源）
  - **order_line（SXD）**：订货数量→order_qty, 订货单位→order_unit, 基本单位数量→base_qty, 基本单位→base_unit, 优惠前金额→pre_discount_amount, 单价→unit_price, 退货数量→return_qty（`discount_amount` 为计算列，见步骤 3）
  - **fulfillment（XD）**：履约订单状态→order_status, 完成时间→completed_at, 退货数量→return_qty（XD 号经 order_header.downstream_order_no 关联，fulfillment 不单独存号）

### 步骤 3 — 舟谱薄适配 + 两层加载 ingest_zhoupu.py
- 连接 `ec101_mvp.db`（append，**不删库**），`PRAGMA foreign_keys=ON`；守卫式 `ALTER TABLE order_header ADD COLUMN downstream_order_no TEXT`（先查 `PRAGMA table_info`，已存在则跳过）。
- 幂等清理（只删羿柏，按 FK 顺序）：`fulfillment → order_line → order_header → product → customer`（`WHERE` 经 dealer_platform_id=羿柏；fulfillment 经 order_id 关联羿柏 order_header）；RAW 按 `batch_code` 删。
- `dealer_platform`：SELECT 复用 else INSERT（`dealer_name='羿柏'`, `platform_name='舟谱'`）。
- **客户主数据**：读 `客户档案-20260914.xlsx`(header_row=4) → map → customer。`platform_customer_no = 客户名称 + "|" + 助记码`（薄适配层直接拼这两列，不走 1:1 映射；助记码空则退化 `客户名称 + "|"`）；`customer_name ← 客户名称`。只加载根目录这份，跳过满赠副本。
- **商品主数据**：读 `商品档案-20260914.xlsx`(header_row=4) → map → product。`platform_product_no ← 商品唯一序号`；`box_conversion ← 单位换算`('1箱=15瓶')；`barcode ← 小单位条码`（SXD 订单行按此回连商品）。跳过满赠副本。
- **建 XD 桥索引**（先于 SXD 加载；一次读 2 个 XD 文件 header_row=4，建两套索引）。**⚠ 一律按列名定位，禁止按固定列序**：已核验满减 XD 63 列、满赠 XD 83 列，"订单状态"在满减第 46 列、满赠第 58 列（位置不同）；且**满赠 XD 无"退货结算数量"列**（满减有，第 51 列）。
  - **订单级**（供客户过桥 + fulfillment）：按 `单据`(XD号) 聚合 `{xd单据: {助记码, 客户名称, 老板电话, 片区, 等级, 订单状态, 结款状态, 签收时间, 出库时间, 退货结算数量}}`。同一 `单据` 的状态/时间应一致——校验 `GROUP BY 单据 HAVING COUNT(DISTINCT 订单状态)>1`，不一致取首条并记录。
  - **行级**（供商品过桥）：`{(单据, 条形码): 商品id}` 与 `{(单据, 商品名称): 商品id}`（已核验同单内 SXD↔XD 行按条码/名称一一对应，名称兜底空条码行）。
- **SXD 订单**：读 8 个 SXD 文件(header_row=4) → order_header + order_line。
  - `order_header`：`order_no ← 订单编号`(SXD…)；`order_time ← 下单时间`；`order_status ← XD.订单状态`（**用户指示：取 XD 权威履约状态**——经本单 `downstream_order_no` 过桥取该 XD 单据的订单状态；**580 个无 XD 命中的单回退用 SXD 订单状态**并计数，因 `order_status` NOT NULL 不能空）；`pay_method ← 支付时间列`（**陷阱：该列值是 '货到付款'，是方式不是时间**）；`downstream_order_no ← 下游订单编号`(XD号)；order_source/order_type 舟谱无 → NULL。`UNIQUE(dealer_platform_id, order_no)`：满赠窗口重叠 → `INSERT OR IGNORE` 去重并计数。
  - **customer_id 过桥匹配**：用本单 `downstream_order_no` 查 XD 桥索引 → 取 `客户助记码` → 拼 `客户名称|助记码` → 命中 customer。**回退链**：① 无 downstream_order_no 或 XD 桥未命中 → 退化为按 `客户名称` 匹配（羿柏内名称唯一才连）；② 名称重名歧义 → `customer_id` 置空 + 记入未决清单（**只报告不猜测**）。打印三级命中数（助记码桥/名称回退/置空）。
  - `order_line`：`product_id` **过 XD 取商品id**（用户选定）——用本单 `downstream_order_no`(=XD.单据) + 本行 `商品条码` 查 XD 行级索引 `{(单据,条形码):商品id}`；条码为空则查 `{(单据,商品名称):商品id}`；命中后 `product_id = product[商品id]`（商品id=商品唯一序号=platform_product_no）。**回退链**：① 该 SXD 无下游 XD / XD 查无此行 → `SXD.商品条码 = product.barcode(小单位条码)` 直连（已核验 898/899=99.9%）；② 仍不中（赠品/无条码无名称）→ product_id NULL + 记未匹配清单（**只报告不猜测**）。打印三级命中数（XD商品id/条码回退/置空）。`order_qty ← 订单数量（大）`（不同 SXD 文件若列名为"实际数量"等，靠 map 统一到订货数量）；文本 "1箱" 用 `to_num`。`base_qty`：SXD 无基本单位数量列 → `order_qty × 每箱换算`(product.box_conversion) 计算（仅当 order_unit=箱/大单位），匹配不到商品则留空。`pre_discount_amount ← 优惠前金额`；`discount_amount = 优惠前金额 − 实际金额`（舟谱无独立优惠列）；`unit_price ← 实际单价`；`return_qty ← NULL`（答案 C）。
- **fulfillment（XD 履约层）**：对每个 `downstream_order_no` 命中 XD 桥的 order_header，插一行 fulfillment：`order_id ← 该 SXD header`；`order_status ← XD.订单状态`；`completed_at ← XD.签收时间`（空则取出库时间）；`return_qty ← XD.退货结算数量`（原样落地，非冲回核算；**满赠 XD 无此列 → 满赠单 return_qty 留空**）；`t2_release_candidate ← 0`（核算轮再算）。`fulfillment.order_id` 唯一 → 一 SXD 至多一行（XD 已按单据聚合）。无 XD 的 SXD → 不建 fulfillment，计数报告。
- **RAW 血缘**：新建 `raw_import_batch`(`batch_code='ZHOUPU-YIBAI-MASTER-ORDER-XD-20260923'`, `source_platform='舟谱'`, `dealer_name='羿柏'`, `operator='小凡'`)；每个加载文件一行 `raw_file`（`module`=客户/商品/订单/订单履约, `file_signature='OOXML'`, `read_method='readers.read_table(header_row=4)'`, `header_row=4`, `data_rows`=实际行数）。共 12 行。
- 末尾打印验证查询。

## 验证（端到端，只读 SQL）

1. **readers 修复**：单独读销售明细成功（不加载，仅证明修复）；兴路强任一文件无回归。
2. **DDL 加列**：`PRAGMA table_info(order_header)` 含 `downstream_order_no`；兴路强既有 order_header 行该列全 NULL。
3. **STANDARD 非空**：`SELECT COUNT(*) FROM std_field_mapping WHERE platform='舟谱'` > 0；抽查 片区→客户区域、支付时间→支付方式、客户助记码、单据→XD单号。
4. **隔离性（关键）**：加载前后，兴路强 dealer_platform 的 customer/product/order_header/order_line/fulfillment 计数**逐一不变**。
5. **主数据**：羿柏 customer/product 计数以实际为准；`platform_customer_no`(=名称|助记码)/`platform_product_no`(=商品唯一序号) 全非空且唯一；抽查 3 条客户组合键格式正确。
6. **SXD 订单**：order_header 数 = 8 文件 distinct SXD号（去重后）；`PRAGMA foreign_key_check` 无输出；抽查 `SXD260827000153` 的 header + lines + 优惠前/实际金额对得上源文件；`downstream_order_no` 在有 XD 的单上非空。
7. **SXD→XD 过桥命中率**：统计 order_header 中 `downstream_order_no` 命中 XD 桥的比例；打印未命中（无 XD）的单数。
8. **客户匹配三级命中**：打印 经助记码桥命中 / 名称回退命中 / customer_id 置空 的订单数；置空清单交人工。
8b. **商品匹配过桥命中（用户选定路线）**：打印 order_line 中 经 XD 商品id 命中 / 条码回退命中 / product_id 置空 的行数；置空清单（赠品/无条码无名称）交人工。抽查 1 个过桥命中的订单行，确认 `product_id` 指向的 product 的 `商品唯一序号` = 该行 XD.商品id。
9. **订单状态取 XD（用户指示·关键）**：打印 order_header.order_status 的来源分布——经 XD 命中 / 回退 SXD（应 ≈580）；抽查那 136 个 SXD"已完成"但 XD"待签收/待出库"的单，确认 order_header.order_status 落的是 **XD 值**（待签收/待出库），不是 SXD 的"已完成"。
9b. **fulfillment**：行数 = 有 XD 匹配的 SXD 数（≈3,474）；`order_status` 分布与 XD 源一致；满赠单 `return_qty` 为空（满赠 XD 无该列）；`PRAGMA foreign_key_check` 无输出。
10. **血缘**：`raw_import_batch` 1 行 + `raw_file` 12 行（2 主数据 + 8 SXD + 2 XD），`header_row` 均 = 4。
11. **未映射列报告**：dry-run 输出的"文件有但 std_field_mapping 无"的列清单应为空（补齐后）。
12. **冲突检测**：打印 羿柏内客户重名数、同单同商品多行数（`UNIQUE(order_id,product_id)` 冲突风险）、XD 同单据状态不一致数，供人工判断。

## 本轮明确不做（范围边界）

**本轮交付物** = 舟谱羿柏的 **客户主数据 + 商品主数据 + SXD 订单(表头+行) + XD 履约(fulfillment) + RAW 血缘**，落进共库 CORE 表；并把 skill 映射(+XD 补映射)灌进 `std_field_mapping`（首次填 STANDARD 层）。以下 **明确不做**：

> ⚠️ **09-24 更新（范围已扩张·轮次 B）**：下表中标 ✅ 的三项（返券核算、满赠核算、任何舟谱 RESULT 层行）**已在轮次 B 做完并落库**；其余各项仍不做。逐行状态见下表"09-24"列。

| 不做项 | 为什么本轮不做 | 影响 | 09-24 状态 |
|---|---|---|---|
| 返券(288 返 15)核算 | 需 coupon_ledger + 逐单归因；活动明细无领券时间/触发订单号，无法逐单比对 | 不产出舟谱返券 RESULT；返券台账下一轮 | ✅ **已做**（轮次 B）：只算使用侧、双单号券不猜测 → 45 单×15=**675 元**，另 3 张双单号券 45 元保守不计、记台账 |
| 满赠(送抱枕)核算 | 需应赠/实赠 + 赠品成本；存在未赠/异常/孤儿赠品单等开放问题 | 不产出舟谱满赠 RESULT | ✅ **已做**（轮次 B）：合格 **142** / 应赠 **135** / 一致 **99** / 差异 **43** / 实赠抱枕 **100**；数量口径、不走 TPM |
| 销售明细加载 | 属"销售明细"模块（非订单/履约），文件最大；本轮范围是订单两层 | CORE 无舟谱销售明细；readers 已修好，下一轮可直接读 | ⬜ 仍不做 |
| 活动明细(优惠券数据) | 属活动执行模块，本轮不核算 | 无舟谱活动执行行 | ✅ **已用于返券台账**（轮次 B）：读 `活动明细`(header_row=3) 建 `coupon_ledger`（102 券/48 已用） |
| 退货冲回核算 | 用户答案 C：舟谱暂不算退货冲回 | `order_line.return_qty` 留空；`fulfillment.return_qty` 仅原样落 XD 数据，不做冲回逻辑 | ⬜ 仍不做 |
| cross_mapping / 太古侧映射 | 需太古 SKU/售点对照，本轮无输入 | `swire_product_code`/`swire_outlet_no` 留空 | ⬜ 仍不做 |
| 任何舟谱 RESULT 层行 | RESULT 依赖上面的核算 | result_* 表本轮无舟谱数据 | ✅ **已做**（轮次 B）：返券+满赠 RESULT 落库，`calc_batch`→**11**，release 候选 **179** |
| 兴路强任何改动 | 共库追加，按 dealer_platform_id 隔离 | 兴路强数据逐行不变（验证 #4 保证） | ⬜ 不变（兴路强 8 表 Δ=**0**，两轮均验证通过） |

## 风险与本轮处置

每条标注 **触发场景 / 检测方式 / 本轮处置**：

1. **SXD 无对应 XD → 客户助记码桥断裂**
   - 触发：全量 70/6,169 个 SXD 无下游 XD；试点窗口内若有这类单，拿不到助记码。
   - 检测：验证 #7 过桥命中率 + 未命中单数。
   - 处置：回退按客户名称匹配（名称唯一才连）；仍歧义则 `customer_id` 置空 + 记未决清单，不猜测。

2. **XD 文件未覆盖某些 SXD 窗口 → 桥索引缺单（已核验 576 单）**
   - 触发：满减 XD 覆盖 0826-0908、满赠 XD 覆盖 0819-0826；**已核验 576 个 SXD 的下游 XD 不在这两个文件内**（另 4 单无下游编号），桥查不到。
   - 检测：`downstream_order_no` 非空但 XD 桥无此单据的单数（验证 #7/#9）。
   - 处置：该单不建 fulfillment；客户走名称回退；商品走条码回退；**order_status 回退用 SXD 状态**；全部计数报告，不阻断。

3. **XD 同单据多行状态不一致**
   - 触发：XD 行级（一单多商品），同 `单据` 的订单状态/签收时间理论上应一致，但源数据可能不齐。
   - 检测：`GROUP BY 单据 HAVING COUNT(DISTINCT 订单状态)>1`（验证 #12）。
   - 处置：取首条并记录不一致单据数，交人工。

4. **客户重名导致名称回退错配**
   - 触发：助记码桥命中时无歧义；仅当回退到名称匹配且羿柏内存在同名客户时才可能错配。
   - 检测：`GROUP BY customer_name HAVING COUNT(*)>1`。
   - 处置：重名歧义单 `customer_id` 置空 + 未决清单（不猜测），打印数量。

5. **商品过 XD 取商品id，桥断 / 赠品项落空（用户选定路线）**
   - 触发：用户选定 `order_line.product_id` 经 XD.商品id 过桥（SXD 无"商品id"列）。桥会在三种情况断裂：① 该 SXD 无下游 XD（70/6,169 全量无 XD，试点窗口内可能也有）；② XD 桥索引查无对应行（XD 文件未覆盖该窗口，见风险 2）；③ 赠品行既无条码又无名称可匹配 XD 行。
   - 检测：验证 #8b 打印的三级命中数（XD 商品id / 条码回退 / product_id 置空）。
   - 处置：① 回退 `SXD.商品条码 = product.barcode(小单位条码)` 直连（已核验 898/899=99.9%）；② 仍不中 → product_id NULL（schema 支持；SQLite `UNIQUE(order_id,NULL)` 不冲突），打印未匹配清单，不阻断（**只报告不猜测**）。

6. **条码在主数据内重复 → 回连歧义**
   - 触发：两个不同商品(不同商品唯一序号)共用同一条码。
   - 检测：`SELECT barcode,COUNT(*) FROM product WHERE dealer_platform_id=羿柏 GROUP BY barcode HAVING COUNT(*)>1`。
   - 处置：打印重复条码清单；歧义取首条并记录，交人工。

7. **base_qty 靠换算推导，可能缺失**
   - 触发：SXD 无"基本单位数量"列，需 `order_qty × 每箱换算`；product_id 未匹配(风险 5)或换算解析失败则为空。
   - 检测：统计 `base_qty IS NULL` 的订单行数。
   - 处置：能算则算，算不出留空并计数，不臆造换算。

8. **同单同商品多行触发 UNIQUE 冲突**
   - 触发：`order_line` 有 `UNIQUE(order_id, product_id)`；同一订单同一商品拆多行(不同批次/价格)会冲突。
   - 检测：加载前扫描 (order_no, product) 重复对（验证 #12）。
   - 处置：默认合并数量/金额为一行；单价不同不宜合并则保留首行并记录，加载前先打印冲突数。

9. **满赠订单窗口重叠 → 订单重复**
   - 触发：满赠 0819-0821 与 0821-0823 窗口重叠，同一 order_no 可能出现两次。
   - 检测：`INSERT OR IGNORE` 的忽略计数。
   - 处置：按 `UNIQUE(dealer_platform_id, order_no)` 去重(首入为准)，打印重复数。
   - ✅ **09-24 已消解（轮次 A）**：源文件已把 `0821-0823` 换成 `0822-0823`，三窗口连续无重叠 → 源侧重复不再存在。`INSERT OR IGNORE` 去重保留作兜底（防跨文件同 order_no）。核算数字未变。

10. **run.json 映射基于 phase-2，缺 XD 列 / phase-3 列名有出入**
    - 触发：seed 用的 skill 映射来自 phase-2；XD 列大概率没映射，phase-3 SXD 列名/后缀(如"（大）")也可能不同。
    - 检测：步骤 1 dry-run 的"未映射列报告"(验证 #11)，对每个文件逐一打印。
    - 处置：手工补 XD 映射 + SXD 别名，直到未映射列为空(或仅剩确认无需入库的列)。

11. **满减/满赠同类文件列结构确实不同（已核验）**
    - 触发：**已字节级核验**——满赠 XD 83 列 vs 满减 XD 63 列，"订单状态"满赠在第 58 列、满减在第 46 列；**满赠 XD 无"退货结算数量"列**；SXD 数量列满减叫"订单数量（大）"、满赠叫"实际数量"，单位列满减"单位名称（大）"、满赠"单位名称"。
    - 检测：加载器**一律按列名定位（禁止固定列序）** + 每文件打印表头 + 未映射报告兜底（验证 #11）。
    - 处置：std_field_mapping 补两套别名（订单数量（大）/实际数量→订货数量；单位名称（大）/单位名称→订货单位）；满赠 fulfillment.return_qty 留空；不假设两类文件结构相同。

12. **"支付时间"列语义陷阱**
    - 触发：SXD"支付时间"列实际存"货到付款"(支付方式)，不是时间。
    - 检测：抽查该列取值分布。
    - 处置：按 RAW_TO_STANDARD 映射到 `pay_method`，不写入任何时间字段。

13. **组合键分隔符是假设**
    - 触发：`platform_customer_no = 客户名称 + "|" + 助记码` 的分隔符 `|` 由我设定，用户未明确指定。
    - 处置：已在 Context 显式标注；如需其他分隔符/顺序，批准时告知即可调整。

14. **DDL 加列与既有库的 schema 一致性**
    - 触发：库已有兴路强数据，不能重建；若只 ALTER 活库不改 DDL 文件，未来重建会丢列。
    - 检测：`PRAGMA table_info(order_header)`(验证 #2) + DDL 文件 diff。
    - 处置：DDL 文件与活库 ALTER 同步改；ALTER 用 `PRAGMA table_info` 守卫，幂等可重跑；兴路强既有行得 NULL（语义正确）。

15. **order_status 取 XD 后的回退语义（用户指示）**
    - 触发：用户指示 `order_header.order_status` 取 XD 权威状态；但已核验 580 单无 XD 命中，而 `order_status` 是 NOT NULL，不能留空。
    - 检测：验证 #9 的来源分布（XD 命中 vs 回退 SXD ≈580）。
    - 处置：无 XD 命中 → 回退填 SXD 订单状态（已下发/未下发/已完成），计数报告；不臆造、不留空。

16. **XD-only 单与被引用 XD 可能重复计费（09-24 轮次 B 新增·开放项）**
    - 触发：轮次 B 新增 XD-only 路径后，"被某 SXD 下游订单编号引用的 XD" 与 "无 SXD 指向、独立建单的 XD" 理论上是两批；但 XD 侧"综合订单号"（本可回指 SXD）列**全空**，两批只能在**单号层面**判定不相交，无法从数据本身证明它们不是同一笔业务的不同视图 → 存在**重复计费**风险。
    - 检测：XD-only 单数（本轮 +2644）与被引用 XD 单号集合做交集（应为空）；`order_source='XD履约(无SXD)'` 计数。
    - 处置：本轮按用户指示"XD 即权威履约"落地为 `order_source='XD履约(无SXD)'` 并计数，**不臆造 XD↔SXD 关联**；来源口径**待舟谱（林楷森/江总）确认**后再决定是否调整或去重。