# 快马 × 兴路强全量快照四层导入实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将快马 × 兴路强的每周全量快照文件包自动导入 RAW、STANDARD 与 CORE，支持安全重跑、完整血缘与跨经销商隔离；本阶段不生成 RESULT。

**Architecture:** 一次上传的一组全量快照文件形成一个技术批次；原文件与逐行数据留在 RAW，字段映射和类型规范落在 STANDARD，CORE 按业务键更新当前最新事实并通过血缘桥表回查来源。活动参与只从平台活动参与明细建立，使用“享受促销政策”文本中 `参与[活动名称]` 的名称精确关联人工批准的活动配置。

**Tech Stack:** Python 3、SQLite、现有 `mvp/scripts/readers.py`、现有字段映射模式、`unittest`、临时 SQLite 测试库。

---

## 1. 已确认的业务边界

### 1.1 输入和批次

- 快马 × 兴路强后续以**每周全量快照**导入：通常覆盖 `2026-01-01` 至该周导出日，而不是按“满减文件”或“满赠文件”分别执行脚本。
- 一次上传/一次自动运行的一组文件是一个技术导入批次；文件可能包括客户、商品、订单、活动参与、优惠券及新增活动截图。
- 批次必须登记数据覆盖起止日期、导入模式 `FULL_SNAPSHOT`、输入文件指纹、状态、操作人和运行报告。
- 同一内容的输入包重跑不得产生重复 RAW、STANDARD 或 CORE 数据。
- 新一周快照建立新批次；旧批次的 RAW 和 STANDARD 永不被覆盖。

### 1.2 CORE 更新口径

- `customer`、`product`、`order_header`、`order_line`、`fulfillment`、`order_activity`、`coupon_ledger` 由 STANDARD 自动装配。
- CORE 是“当前最新事实”视图：新快照中出现的同业务键记录可覆盖旧值。
- 本周快照未出现的旧客户、商品或订单**不得自动删除**；仅记录它在本批次未出现。
- RAW 与 STANDARD 是历史证据；CORE 的覆盖不删除旧源行血缘。
- MVP 阶段，客户/商品/订单关联不完整、字段缺失、活动未匹配等业务质量问题只记录警告，不阻断 CORE。

### 1.3 活动参与和人工配置

- 活动截图与 TPM 不做 OCR 自动猜测；截图/TPM 原件必须归档，并由人工确认后形成结构化配置。
- TPM 在本阶段独立保存，不自动关联活动、预算或费用。
- 平台活动参与明细是活动执行的唯一依据。订单即使从规则上看应满足条件，但活动参与明细没有该订单，系统也不得补建 `order_activity`，只能记录警告。
- 快马“享受促销政策”字段中存在唯一活动名，例如：

  ```text
  参与[可口可乐满减]组合金额满¥300，立减¥15活动，为您节省¥1.24
  ```

  系统只提取方括号内的 `可口可乐满减`，按“经销商 × 平台 × 活动名称”精确匹配人工批准的活动配置；不得以整段政策文本匹配。
- 同一订单、同一活动有多条平台活动明细时，聚合为一条 `order_activity`；活动商品金额和平台优惠金额分别求和，全部原始参与行保留血缘。
- 满减、满赠规则、适用范围、叠加和限购均以人工确认后的截图配置为准。满赠“整个活动每客户一次”不是系统预设，是否限购及限购期间以配置为准。

### 1.4 本阶段不做 RESULT

- 不生成理论权益、一致性、T-2 发放候选、费用结果或结算候选。
- 不做活动资格重算、满减重算、满赠应赠计算或券费用计算。
- 仅为第二阶段保存将来所需的活动配置、活动参与事实、订单事实和完整血缘。
- 后续 RESULT 的订单完成口径已经确认：只认 `订单状态 = 已完成`；部分发货不算完成；T-2 使用下单时间与计算日判断；目前不处理退货、取消和退款回收。但这些规则不在第一阶段执行。

## 2. 目标输入目录与命令

运行时通过环境变量 `EC101_DATA_ROOT` 指向非 Git 归档根目录。示例：

```text
EC101_DATA_ROOT/
  incoming/
    kuaima-xingluqiang/
      2026-10-04/
        客户主数据.xlsx
        商品主数据.xlsx
        订单明细.xlsx
        活动参与明细.xlsx
        优惠券明细.xlsx
  raw-archive/
    kuaima-xingluqiang/
      KM-XLQ-SNAPSHOT-20261004-001/
```

输入文件角色由 manifest 声明，不通过“满减”“满赠”等文件名推断：

| file_role | 业务含义 |
|---|---|
| `customer_snapshot` | 客户主数据全量快照 |
| `product_snapshot` | 商品主数据全量快照 |
| `order_snapshot` | 订单及订单行全量快照 |
| `activity_execution_snapshot` | 平台活动参与全量快照 |
| `coupon_snapshot` | 优惠券台账全量快照 |
| `activity_config_evidence` | 活动截图证据 |
| `tpm_evidence` | TPM 原件证据 |

目标命令：

```bash
python -m mvp.pipeline.cli validate \
  --platform 快马 \
  --dealer 深圳市兴路强商贸有限公司 \
  --input-dir "$EC101_DATA_ROOT/incoming/kuaima-xingluqiang/2026-10-04"
```

```bash
python -m mvp.pipeline.cli run \
  --platform 快马 \
  --dealer 深圳市兴路强商贸有限公司 \
  --input-dir "$EC101_DATA_ROOT/incoming/kuaima-xingluqiang/2026-10-04" \
  --operator "<操作人>"
```

`validate` 只做文件识别、RAW 预览、STANDARD 预览和质量报告，不写 CORE。`run` 执行完整的 RAW → STANDARD → CORE。后续可增加 `rerun --batch-code`，但重跑必须复用同一个批次，不新建重复数据。

## 3. 数据模型调整

### 3.1 RAW

扩充 `raw_import_batch`：

```text
ingest_mode             TEXT NOT NULL       -- FULL_SNAPSHOT
coverage_start_date     TEXT
coverage_end_date       TEXT
input_fingerprint       TEXT NOT NULL       -- 排序后的文件 hash 组合
run_status              TEXT NOT NULL       -- VALIDATING/RUNNING/SUCCEEDED/FAILED
started_at              TEXT
finished_at             TEXT
failure_reason          TEXT
```

新增 `ingest_run`，分离“这组输入文件”与“执行尝试”：

```text
run_id, batch_id, run_type, status, operator,
started_at, finished_at, report_path, error_message
```

扩充 `raw_file`：

```text
file_role, sha256, file_size_bytes, archived_path,
source_coverage_start, source_coverage_end
```

新增 `raw_record`：

```text
raw_record_id, file_id, source_row_no, source_business_key, payload_json
```

规则：一个源数据行对应一条 `raw_record`；`payload_json` 保留读取后的原字段和值，不改名、不清洗、不聚合。原 Excel 文件复制到 `raw-archive`，并以 SHA-256 检验版本；不将 Excel 二进制写入 SQLite。

### 3.2 STANDARD

保留 `std_field_mapping`，为快马补齐映射并作为字段映射真源。新增：

```text
std_customer
std_product
std_order
std_order_line
std_activity_detail
std_coupon
```

每张标准化表必须包含：

```text
std_id, batch_id, file_id, source_row_no, raw_record_id,
dealer_platform_id, 标准业务字段
```

扩充 `std_quality_check`：

```text
file_id, source_row_no, check_code, check_item,
result, level, impact, evidence_ref
```

标准化强制规则：编号/单号/券号为文本；日期为 `YYYY-MM-DD HH:MM:SS`；金额保留两位小数；数量和单位分列保留。

### 3.3 CORE 和血缘

保留既有 CORE 实体表，新增 `core_lineage_link`：

```text
lineage_id, target_type, target_id, std_table_name,
std_id, raw_record_id, batch_id, link_role
```

`link_role` 至少包括 `source`、`aggregation_member`、`matched_evidence`。它必须支持多条 `std_order_line` 聚合为一条 `order_line`，也必须支持多条 `std_activity_detail` 聚合为一条 `order_activity`。

为 `customer`、`product`、`order_header` 增加：

```text
first_seen_batch_id, last_seen_batch_id
```

现有 `order_header.batch_id` 仅保留兼容旧数据；新链路以 `core_lineage_link` 为追溯真源。

### 3.4 人工活动与 TPM 配置

新增 `raw_config_evidence`：

```text
evidence_id, dealer_platform_id, evidence_type,
archived_file_id, structured_config_json, config_version,
approval_status, confirmed_by, confirmed_at
```

人工批准活动配置必须至少有：

```text
平台、经销商、活动名称、有效期、活动类型、配置版本、状态、截图证据、确认人、确认时间
```

完整配置还应记录：门槛、权益、商品范围、客户范围、叠加、允许用券、限购类型、限购次数和限购期间。配置未批准时，活动参与明细只能进入 STANDARD 并记录警告，不得建立 `order_activity`。

## 4. 快马映射与 CORE 装配

快马字段映射从现有专用脚本迁移到 `std_field_mapping`：

| 原始字段 | EC101 标准字段 | CORE 目标 |
|---|---|---|
| 客户编号 | 客户编号 | `customer.platform_customer_no` |
| 客户名称 | 客户名称 | `customer.customer_name` |
| 商品编号 | 平台商品编号 | `product.platform_product_no` |
| 商品条码 | 商品条码 | 商品匹配兜底 |
| 订单编号 | 订单编号 | `order_header.order_no` |
| 下单时间 | 下单时间 | `order_header.order_time` |
| 订单状态 | 订单状态 | `order_header.order_status`、`fulfillment.order_status` |
| 订货数量 | 订货数量 | `order_line.order_qty` |
| 优惠前金额 | 优惠前金额 | `order_line.pre_discount_amount` |
| 优惠金额 | 总优惠金额 | `order_line.discount_amount` |
| 活动明细.订单号 | 活动订单号 | `order_activity` 关联订单 |
| 活动明细.商品总金额 | 活动商品金额 | `order_activity.activity_product_amount` |
| 活动明细.促销优惠金额 | 平台实际权益 | `order_activity.platform_actual_benefit` |
| 活动明细.享受促销政策 | 活动政策原文 | 活动名称提取与审计证据 |
| 优惠券编号 | 优惠券编号 | `coupon_ledger.coupon_no` |
| 使用订单号 | 使用订单号 | `coupon_ledger.use_order_no` |

CORE 装配顺序：

```text
dealer_platform
  → customer / product
  → order_header / order_line
  → fulfillment
  → 已批准 activity 配置
  → order_activity
  → coupon_ledger
```

订单状态作为履约事实写入 `fulfillment`；本阶段不得以订单状态或下单时间计算 `t2_release_candidate`，也不得将下单时间伪装成履约完成时间。

## 5. 新文件、保留文件与职责

新增：

```text
mvp/migrations/001_snapshot_raw_standard.sql
mvp/migrations/002_core_lineage.sql
mvp/pipeline/__init__.py
mvp/pipeline/cli.py
mvp/pipeline/manifest.py
mvp/pipeline/raw_loader.py
mvp/pipeline/standardizer.py
mvp/pipeline/quality_checks.py
mvp/pipeline/core_loader.py
mvp/pipeline/activity_config_loader.py
mvp/pipeline/lineage.py
mvp/pipeline/reporting.py
mvp/config/kuaima_xingluqiang/field_mapping.json
mvp/config/kuaima_xingluqiang/module_manifest.json
mvp/config/kuaima_xingluqiang/quality_rules.json
mvp/tests/fixtures/kuaima_xingluqiang/
mvp/tests/test_manifest.py
mvp/tests/test_raw_loader.py
mvp/tests/test_standardizer.py
mvp/tests/test_core_loader.py
mvp/tests/test_lineage.py
mvp/tests/test_kuaima_snapshot_e2e.py
```

既有文件：

| 文件 | 后续职责 |
|---|---|
| `mvp/scripts/readers.py` | 保留并复用，按真实文件格式读取 |
| `mvp/scripts/std_mapping.py` | 迁入/复用为通用字段映射工具 |
| `mvp/scripts/seed_std_mapping_zhoupu.py` | 参考其映射入库方式，为快马提供同类初始化 |
| `mvp/scripts/ingest_zhoupu.py` | 参考“配置驱动 + 薄适配”模式，不作为快马入口 |
| `mvp/scripts/ingest_manjian.py` | 历史回归基线；禁止用于新流程，因为它重建整库 |
| `mvp/scripts/ingest_manzeng.py` | 历史规则与控制数基线 |
| `mvp/scripts/ingest_coupon.py` | 快马券字段映射与历史控制数基线 |

## 6. 实施任务

### Task 0：建立历史基线和临时测试库

**Files:**

- Create: `mvp/tests/fixtures/kuaima_xingluqiang/`
- Create: `mvp/tests/baseline_queries.sql`
- Test: `mvp/tests/test_kuaima_snapshot_e2e.py`

- [ ] 从现有 `mvp/ec101_mvp.db` 导出快马和舟谱分经销商控制数、金额和外键检查结果。
- [ ] 将快马历史源文件复制为测试 fixture，不直接让测试读写真实数据库。
- [ ] 编写端到端测试：创建临时 SQLite 数据库，导入 fixture，并断言舟谱测试种子不被改动。
- [ ] 记录当前快马历史回归基线：满减 136 笔、理论/实际优惠各 2,040 元；满赠 98 笔、应赠/实赠各 98；这些仅用于未来第二阶段 RESULT 回归，不在第一阶段重算。

验收：

```sql
PRAGMA foreign_key_check;
```

必须返回 0 行。

### Task 1：以迁移脚本增加 RAW 快照能力

**Files:**

- Create: `mvp/migrations/001_snapshot_raw_standard.sql`
- Test: `mvp/tests/test_raw_loader.py`

- [ ] 在迁移脚本中以非破坏方式扩充 `raw_import_batch` 和 `raw_file`，并创建 `ingest_run`、`raw_record`。
- [ ] 为 `raw_record(file_id, source_row_no)` 创建唯一约束。
- [ ] 为 `raw_file` 建立以 `batch_id + file_role + sha256` 为准的去重约束或等价索引。
- [ ] 在临时库执行迁移两次，确认第二次不报错、不丢现有快马和舟谱数据。

验收：

```sql
SELECT b.batch_code, b.ingest_mode, b.coverage_start_date, b.coverage_end_date,
       f.file_role, f.file_name, f.sha256, f.data_rows
FROM raw_import_batch b
JOIN raw_file f ON f.batch_id = b.batch_id
WHERE b.batch_id = :batch_id;
```

```sql
SELECT f.file_name, COUNT(*) AS raw_rows
FROM raw_file f
LEFT JOIN raw_record r ON r.file_id = f.file_id
WHERE f.batch_id = :batch_id
GROUP BY f.file_id, f.file_name;
```

每个文件的 `raw_rows` 应等于其 `data_rows`。

### Task 2：定义快马 manifest 与字段映射

**Files:**

- Create: `mvp/config/kuaima_xingluqiang/module_manifest.json`
- Create: `mvp/config/kuaima_xingluqiang/field_mapping.json`
- Create: `mvp/pipeline/manifest.py`
- Modify: `mvp/scripts/std_mapping.py`
- Test: `mvp/tests/test_manifest.py`
- Test: `mvp/tests/test_standardizer.py`

- [ ] manifest 定义每个 `file_role` 的允许文件数、表头行、必需原字段、STANDARD 目标表和覆盖日期获取方式。
- [ ] 快马字段映射落入 `std_field_mapping`，使脚本不再直接写死快马表头。
- [ ] 标准化时将编号、单号、券号强制为字符串，日期标准化为 ISO 文本，金额转为两位小数。
- [ ] 遇到未知列、缺失必填列、日期/金额解析失败时写入 `std_quality_check`；除技术不可读外不阻断第一阶段 CORE。

验收：

```sql
SELECT platform, module, raw_field, ec101_field
FROM std_field_mapping
WHERE platform = '快马'
ORDER BY module, raw_field;
```

```sql
SELECT level, result, check_code, COUNT(*) AS issue_count
FROM std_quality_check
WHERE batch_id = :batch_id
GROUP BY level, result, check_code;
```

### Task 3：实现 RAW 与 STANDARD 装载器

**Files:**

- Create: `mvp/pipeline/raw_loader.py`
- Create: `mvp/pipeline/standardizer.py`
- Create: `mvp/pipeline/quality_checks.py`
- Create: `mvp/pipeline/reporting.py`
- Test: `mvp/tests/test_raw_loader.py`
- Test: `mvp/tests/test_standardizer.py`

- [ ] 归档每个原文件，计算 SHA-256，创建或复用批次和文件记录。
- [ ] 读取文件后先写 `raw_record`，再由 RAW 生成对应 STANDARD 表。
- [ ] `std_order_line` 必须保留逐行明细，禁止在 STANDARD 聚合。
- [ ] `std_activity_detail` 必须保存完整 `享受促销政策` 文本和提取出的 `activity_name`。
- [ ] 对 `参与[活动名称]` 使用严格提取；无法提取活动名称时仅记警告。

验收：

```sql
SELECT COUNT(*) AS unmapped_required_fields
FROM std_quality_check
WHERE batch_id = :batch_id
  AND check_code = 'REQUIRED_FIELD_UNMAPPED';
```

应为 0。

### Task 4：建立人工活动证据与配置装载

**Files:**

- Create: `mvp/migrations/002_core_lineage.sql`
- Create: `mvp/pipeline/activity_config_loader.py`
- Create: `mvp/config/kuaima_xingluqiang/activity-config-schema.json`
- Test: `mvp/tests/test_core_loader.py`

- [ ] 创建 `raw_config_evidence` 和活动配置关联字段。
- [ ] 创建人工活动配置校验：活动名称、平台、经销商、有效期、版本、证据、确认人和批准状态为必填。
- [ ] 只将 `APPROVED` 配置写入可匹配的 `activity` 与规则/范围子表。
- [ ] 配置未批准、活动名找不到或同名多版本无法判定当前版本时，活动参与明细只记警告，不写 `order_activity`。

验收：

```sql
SELECT a.activity_name, e.config_version, e.approval_status,
       e.confirmed_by, e.confirmed_at
FROM activity a
JOIN raw_config_evidence e ON e.evidence_id = a.config_evidence_id
WHERE a.dealer_platform_id = :target_dp_id;
```

所有可匹配活动应为 `APPROVED`。

### Task 5：实现 CORE 装配与血缘

**Files:**

- Create: `mvp/pipeline/core_loader.py`
- Create: `mvp/pipeline/lineage.py`
- Test: `mvp/tests/test_core_loader.py`
- Test: `mvp/tests/test_lineage.py`

- [ ] `customer` 与 `product` 按“经销商平台 + 平台编号”更新为最新值，同时更新 `last_seen_batch_id`。
- [ ] `order_header` 按“经销商平台 + 订单号”更新为最新值；订单未出现在新快照时不删除。
- [ ] `order_line` 先按现有业务约束 `(order, product)` 聚合；每个聚合结果建立全部成员的 `aggregation_member` 血缘。
- [ ] `fulfillment` 只写平台订单状态；不计算 T-2，不写伪完成时间。
- [ ] 从 `std_activity_detail` 关联订单和人工批准活动，按 `(order, activity)` 聚合后写 `order_activity`。
- [ ] 从 `std_coupon` 更新 `coupon_ledger`；不得按整个经销商平台删除所有券。
- [ ] 未匹配客户、商品、订单或活动时写质量警告，但不猜测关系。

验收：

```sql
PRAGMA foreign_key_check;
```

必须返回 0 行。

```sql
SELECT dealer_platform_id, order_no, COUNT(*) AS n
FROM order_header
GROUP BY dealer_platform_id, order_no
HAVING COUNT(*) > 1;
```

必须返回 0 行。

```sql
SELECT target_type, COUNT(*) AS missing_source
FROM core_lineage_link l
LEFT JOIN raw_record r ON r.raw_record_id = l.raw_record_id
WHERE r.raw_record_id IS NULL
GROUP BY target_type;
```

必须返回 0 行。

### Task 6：实现 CLI、同批次重跑和跨经销商隔离

**Files:**

- Create: `mvp/pipeline/cli.py`
- Test: `mvp/tests/test_kuaima_snapshot_e2e.py`

- [ ] `validate` 输出文件角色识别、映射覆盖、质量警告和预计写入量，且不写 CORE。
- [ ] `run` 在单个事务边界内执行 RAW → STANDARD → CORE；失败时标记批次失败并报告原因。
- [ ] `rerun` 仅清理该批次的 STANDARD 派生记录，再从已归档 RAW 重建；不得删除其他批次 RAW、舟谱或其他经销商 CORE 数据。
- [ ] 运行报告记录批次、文件、RAW 行数、STANDARD 行数、CORE 新增/更新数、警告数和外键检查结果。

验收：

```sql
SELECT dp.dealer_name, dp.platform_name, COUNT(*) AS order_count
FROM order_header oh
JOIN dealer_platform dp ON dp.dealer_platform_id = oh.dealer_platform_id
GROUP BY dp.dealer_platform_id;
```

在快马运行前后，舟谱的 `order_count` 必须完全一致。

对同一输入连续执行两次后：

```sql
SELECT COUNT(*) AS orders
FROM order_header
WHERE dealer_platform_id = :kuaima_dp_id;
```

以及对应订单行、活动参与和券台账的数量与金额均必须稳定，不得翻倍。

## 7. 验收测试矩阵

| 场景 | 预期 |
|---|---|
| 同一输入文件包连续运行两次 | RAW、STANDARD、CORE 不重复累计 |
| 新周订单快照将订单状态从部分发货更新为已完成 | CORE 显示已完成，旧 RAW/STANDARD 批次仍可查询 |
| 新周快照遗漏历史订单 | CORE 不删除历史订单 |
| 长订单号/券号/使用订单号 | 保持完整文本，不出现科学计数法 |
| `.xls`、`.xlsx`、HTML 伪 Excel | 由 `readers.py` 正确识别并读取 |
| 客户或商品不匹配 | CORE 可入库，产生警告，不猜测匹配 |
| 政策文本可提取且匹配批准活动 | 创建/更新 `order_activity` |
| 政策文本无方括号活动名 | 警告，不创建 `order_activity` |
| 订单规则上可能符合活动但活动参与明细缺失 | 警告，不创建 `order_activity` |
| 活动配置未批准 | 警告，不创建 `order_activity` |
| 快马运行 | 舟谱所有 CORE 行数不变 |
| 任意阶段完成 | `PRAGMA foreign_key_check` 无结果 |

## 8. 迁移与兼容风险

- 禁止使用 `ingest_manjian.py` 作为新入口：它含有删除 `mvp/ec101_mvp.db` 的逻辑，会清除舟谱数据。
- 当前快马历史数据没有逐行 RAW/STANDARD 血缘；应以历史源文件做“回补批次”导入，在临时库对账通过后再切换。
- SQLite 对删除/修改唯一约束支持有限。第一阶段只新增 RAW、STANDARD、血缘能力，避免不必要地重建现有 CORE/RESULT 表。
- `order_header.batch_id` 不能表达多次快照更新的完整来源；新链路必须依赖 `core_lineage_link`。
- 当前 API 测试直接读取真实 `mvp/ec101_mvp.db` 并断言快马订单数量。新增流水线测试必须使用临时数据库和 fixture，避免污染真实库。
- RAW 每周保存全量快照会快速增加存储量；MVP 期间原文件与 RAW 行不清理，后续生产化时另行制定归档期限和冷热存储策略。

## 9. 第二阶段 RESULT 的前置条件（不在本次实施）

在第一阶段稳定后，才执行 RESULT 改造。前置条件：

- 活动截图已人工结构化并批准；
- 标准化订单、活动参与、赠品/券数据可逐行追溯；
- 订单完成口径和 T-2 口径已按本文件记录；
- `result_entitlement` 的唯一约束调整为 `(order_activity_id, calc_batch_id)`，以保留重算历史；
- 活动配置版本可被结果批次引用。

第二阶段再实现满减、满赠、券类、T-2 和费用结果；第一阶段不得提前写入任何 RESULT 派生数据。
