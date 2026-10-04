# 优惠券 CORE 模型实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将两类优惠券配置和已验证的 `test1` 台账事实纳入 EC101 既有 CORE 活动模型。

**Architecture:** SQLite DDL 作为权威结构定义；独立迁移模块在事务内重建受旧唯一约束限制的 `activity`，新增券规则结构，再幂等地加载两条快马/兴路强券活动。导入脚本继续负责券台账事实，并仅对具有明确导入键证据的 `test1` 券回填活动关联。

**Tech Stack:** Python 3、stdlib `sqlite3` / `unittest`、SQLite、现有 `readers.py`、SVG 生成脚本。

**Spec:** `docs/superpowers/specs/2026-10-04-coupon-core-model-design.md`

## Global Constraints

- 保留既有活动、规则、范围和券台账；不建立第二套活动模型。
- 旧活动的 `activity_import_key` 必须保持 `NULL`，活动名称可以重复，非空导入键全局唯一。
- 历史券仅在有充分证据时回填；本次只允许回填券号 `202609091700313431` 到 `KM-COUPON-AUTO-001`。
- 金额门槛与立减金额只保存于 `activity_rule`。
- 新源文件使用 `test1优惠券` 名称，并忽略 `.~` Office 临时文件。
- 不修改订单、费用结算或前端 API 契约；未使用券不得进入 `result_fee`。

## Review Focus

- 旧 `activity` 仍保留的内联名称唯一约束会阻止同名活动，迁移测试必须插入同名活动证明约束已消除。
- `activity_import_key=NULL` 的历史行不应被部分唯一索引视为冲突，迁移测试必须保留两条空键行。
- `test1` 之外的券即使同名或同平台也不能自动关联活动，台账加载测试必须断言其 `activity_id` 为空。
- 迁移失败时不应留下半张重建表或部分导入数据，测试必须验证事务回滚。
- 新增名单包含可精确匹配的客户编号；缺失或无法匹配的名单行必须使导入失败，而不能插入猜测范围。

---

### Task 1: 建立可迁移且可回归的 CORE 结构测试

**Files:**
- Create: `mvp/scripts/test_coupon_core_migration.py`
- Modify: `mvp/ddl/ec101_mvp_sqlite.sql`

**Interfaces:**
- Consumes: `migrate_coupon_core.migrate_schema(connection: sqlite3.Connection) -> None`
- Produces: 可运行的 `unittest` 回归套件，供后续迁移和导入任务使用。

- [ ] **Step 1: 写失败测试，验证活动名可重复且导入键唯一**

```python
def test_migrate_schema_allows_duplicate_activity_names_and_unique_non_null_import_keys(self):
    migrate_schema(self.connection)
    self.insert_activity("同名活动", None)
    self.insert_activity("同名活动", None)
    self.insert_activity("券活动", "KM-COUPON-AUTO-001")
    with self.assertRaises(sqlite3.IntegrityError):
        self.insert_activity("另一名称", "KM-COUPON-AUTO-001")
```

- [ ] **Step 2: 运行测试，确认因缺少迁移模块而失败**

Run: `python3 -m unittest mvp.scripts.test_coupon_core_migration.CouponCoreMigrationTest.test_migrate_schema_allows_duplicate_activity_names_and_unique_non_null_import_keys -v`

Expected: FAIL，提示无法导入 `migrate_coupon_core`。

- [ ] **Step 3: 在 DDL 声明新列与两张券规则表**

在 `activity` 加入可空 `activity_import_key`，去除名称唯一约束；声明两个规则表、`coupon_ledger.activity_id` 和必要索引。用 SQLite `CHECK` 约束限定 `issue_mode`、`validity_mode`，但不把业务状态或中文券类型硬编码为数据库枚举。

- [ ] **Step 4: 运行同一测试，确认仍失败于未实现迁移函数**

Run: `python3 -m unittest mvp.scripts.test_coupon_core_migration.CouponCoreMigrationTest.test_migrate_schema_allows_duplicate_activity_names_and_unique_non_null_import_keys -v`

Expected: FAIL，迁移函数尚不存在。

### Task 2: 实现 SQLite 原子结构迁移

**Files:**
- Create: `mvp/scripts/migrate_coupon_core.py`
- Modify: `mvp/scripts/test_coupon_core_migration.py`

**Interfaces:**
- Consumes: 旧版或新版 EC101 SQLite `sqlite3.Connection`。
- Produces: `migrate_schema(connection: sqlite3.Connection) -> None`，可安全重复执行；`run(db_path: str, source_dir: str) -> dict[str, int]` 留给 Task 3 填充活动导入。

- [ ] **Step 1: 写失败测试，保留旧 `activity_id`、子表引用和历史空导入键**

```python
def test_migrate_schema_rebuilds_legacy_activity_without_losing_children(self):
    legacy_id = self.insert_legacy_activity("旧活动")
    self.insert_legacy_rule(legacy_id)
    migrate_schema(self.connection)
    self.assertEqual(self.query_activity(legacy_id)["activity_import_key"], None)
    self.assertEqual(self.rule_activity_ids(), [legacy_id])
```

- [ ] **Step 2: 运行测试，确认旧活动表仍无法重建**

Run: `python3 -m unittest mvp.scripts.test_coupon_core_migration.CouponCoreMigrationTest.test_migrate_schema_rebuilds_legacy_activity_without_losing_children -v`

Expected: FAIL，`migrate_schema` 尚未保留旧数据。

- [ ] **Step 3: 实现 `migrate_schema`**

在同一事务内关闭外键检查，创建 `activity__new`（不含名称唯一约束）、按列复制原 `activity_id` 和所有业务字段、替换原表、重建索引和新增规则表/台账列；成功后恢复 `PRAGMA foreign_keys=ON` 并执行 `PRAGMA foreign_key_check`。对已经迁移的数据库检测列/表后直接返回，保持幂等。

- [ ] **Step 4: 运行结构测试并新增回滚测试**

Run: `python3 -m unittest mvp.scripts.test_coupon_core_migration -v`

Expected: PASS；测试覆盖重复迁移、外键完整性及异常时不提交部分变更。

### Task 3: 幂等导入券活动、规则、范围与确定性台账关联

**Files:**
- Modify: `mvp/scripts/migrate_coupon_core.py`
- Modify: `mvp/scripts/ingest_coupon.py`
- Modify: `mvp/scripts/test_coupon_core_migration.py`

**Interfaces:**
- Consumes: `run(db_path, source_dir)`、两张方案图、两份指定客户列表和 `customer` / `coupon_ledger` 已有事实。
- Produces: 两条以导入键定位的券活动、各一条发放规则和使用规则、明确范围行，以及 `test1` 券的单一活动关联。

- [ ] **Step 1: 写失败测试，验证两条规则、客户范围和 `test1` 回填**

```python
def test_load_coupon_activities_creates_rules_scopes_and_only_verified_ledger_link(self):
    summary = load_coupon_activities(self.connection, self.source_dir)
    self.assertEqual(summary["activities"], 2)
    self.assertEqual(self.count("coupon_issue_rule"), 2)
    self.assertEqual(self.count("coupon_use_rule"), 2)
    self.assertEqual(self.ledger_activity("202609091700313431"), self.activity_id("KM-COUPON-AUTO-001"))
    self.assertIsNone(self.ledger_activity("UNVERIFIED-001"))
```

- [ ] **Step 2: 运行测试，确认导入函数尚不存在或未创建正确数据**

Run: `python3 -m unittest mvp.scripts.test_coupon_core_migration.CouponCoreMigrationTest.test_load_coupon_activities_creates_rules_scopes_and_only_verified_ledger_link -v`

Expected: FAIL，未实现 `load_coupon_activities`。

- [ ] **Step 3: 实现 `load_coupon_activities(connection, source_dir) -> dict[str, int]`**

解析指定客户列表并按 `platform_customer_no` 验证客户存在后，以 `activity_import_key` 插入或更新 `KM-COUPON-MANUAL-001` 和 `KM-COUPON-AUTO-001`。写入规格确定的金额规则、规则状态、发放/使用规则、范围行；重跑时先替换这两张活动自己的规则和范围，绝不影响其他活动。只以券号、目标客户、券名、领取时间和使用期的组合证据回填 `test1` 台账；不满足组合条件的券保留空关联。

- [ ] **Step 4: 更新 `ingest_coupon.py` 的源文件与关联逻辑**

把三份源明细改为 `快马-兴路强-优惠券-test1优惠券-*` 文件名，增加忽略 `.~` 文件的源校验；在台账重载后调用 `load_coupon_activities` 的确定性回填逻辑。保留既有 RAW 血缘登记和订单号精度验证。

- [ ] **Step 5: 运行完整迁移/导入回归测试**

Run: `python3 -m unittest mvp.scripts.test_coupon_core_migration -v`

Expected: PASS；重跑结果中活动、规则、范围行不重复且只关联一张已验证券。

### Task 4: 对真实 MVP 数据库执行迁移并验证业务不变量

**Files:**
- Modify: `mvp/ec101_mvp.db`
- Create: `mvp/scripts/verify_coupon_core.py`
- Modify: `mvp/scripts/verify_coupon.py`

**Interfaces:**
- Consumes: 已实现的 `run(db_path, source_dir)` 与真实 `mvp/ec101_mvp.db`。
- Produces: 迁移后的数据库与可重复执行的文本验证结果。

- [ ] **Step 1: 写失败验证，定义真实库的预期结果**

```python
assert scalar("SELECT COUNT(*) FROM coupon_issue_rule") == 2
assert scalar("SELECT COUNT(*) FROM coupon_use_rule") == 2
assert scalar("SELECT activity_id IS NOT NULL FROM coupon_ledger WHERE coupon_no=?", ("202609091700313431",)) == 1
assert scalar("SELECT COUNT(*) FROM pragma_foreign_key_check") == 0
```

- [ ] **Step 2: 迁移前运行验证，确认当前库缺少新表而失败**

Run: `python3 mvp/scripts/verify_coupon_core.py`

Expected: FAIL，报告缺少 `coupon_issue_rule` / `coupon_use_rule`。

- [ ] **Step 3: 执行一次真实库迁移与券活动导入**

Run: `python3 mvp/scripts/migrate_coupon_core.py --db mvp/ec101_mvp.db --source-dir 快马-兴路强-试点/优惠券`

迁移命令只修改本地 MVP SQLite；在开始前复制数据库到同目录、带时间戳的 `.bak` 文件，并在提交后打印活动、规则、范围和回填券数。

- [ ] **Step 4: 运行验证并确认重复执行幂等**

Run: `python3 mvp/scripts/verify_coupon_core.py && python3 mvp/scripts/migrate_coupon_core.py --db mvp/ec101_mvp.db --source-dir 快马-兴路强-试点/优惠券 && python3 mvp/scripts/verify_coupon_core.py`

Expected: PASS；无外键违规、两条规则各两行、仅 `test1` 的已验证台账关联到活动，第二次执行不增加记录。

### Task 5: 同步 CORE 模型文档与 ER 图

**Files:**
- Modify: `EC101逻辑数据模型设计说明V1.md`
- Modify: `mvp/EC101_MVP数据库使用说明V1.md`
- Modify: `scripts/build_core_er_svg.py`
- Modify: `docs/diagrams/ec101-mvp-core-er.svg`
- Modify: `PROJECT.md`

**Interfaces:**
- Consumes: 最终 DDL 与 `verify_coupon_core.py` 的验证结果。
- Produces: 与实际 CORE schema 一致的说明和 ER 图。

- [ ] **Step 1: 写失败文档一致性检查**

在 `verify_coupon_core.py` 中断言 DDL、ER 图生成源和逻辑模型说明均含 `coupon_issue_rule`、`coupon_use_rule`、`activity_import_key`、`coupon_ledger.activity_id`。

- [ ] **Step 2: 运行检查，确认当前文档缺少新增实体**

Run: `python3 mvp/scripts/verify_coupon_core.py`

Expected: FAIL，报告缺少新增 CORE 实体说明。

- [ ] **Step 3: 更新逻辑说明、MVP 使用说明、ER 图源和 `PROJECT.md`**

在逻辑模型中记录两个规则表、一对一关系、活动导入键和台账关联的历史回填规则；在使用说明中记录两条券活动、源文件和范围证据。更新 ER 图源的实体、关系、表总数和活动域布局，再运行 `python3 scripts/build_core_er_svg.py` 生成 SVG。更新 `PROJECT.md` 的能力、重要文件和下一步。

- [ ] **Step 4: 运行完整文档与数据库验证**

Run: `python3 mvp/scripts/verify_coupon_core.py && python3 mvp/scripts/verify_coupon.py && git diff --check`

Expected: PASS；数据库、ER 图和说明引用同一套 CORE 模型，且无空白错误。
