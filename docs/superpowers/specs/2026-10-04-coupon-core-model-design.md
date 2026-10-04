# 优惠券 CORE 数据模型设计

## 目标

将优惠券纳入现有活动模型，而非新增第二套促销活动模型。活动规则、活动范围、实际发券和核销事实保持在既有 CORE 层可追溯、可复算的关系中。

## 已确认约束

- 保留 `activity`、`activity_rule`、`activity_rule_benefit`、`activity_scope`、`coupon_ledger`。
- `activity_rule` 仍承载券的金额门槛和立减金额；不得在券规则表重复保存这些值。
- 每张券活动只有一条发放规则和一条使用规则。
- 活动名称可以重复；稳定关联只使用不可重复的 `activity_import_key`。
- 历史 `activity.activity_import_key` 保持 `NULL`，不根据名称、内部 ID 或其他推测值回填。
- 历史 `coupon_ledger.activity_id` 默认保持 `NULL`，只有取得充分、可审计的证据时才可回填；本次 `test1` 是已验证的例外。
- 未使用券只保存可用、已领取或已过期等事实，不计入费用结算。

## 关系模型

```text
activity（券类活动）
  ├─ activity_rule              满额门槛与立减金额
  ├─ activity_scope             对象、商品、支付、物流、场景范围
  ├─ coupon_issue_rule          发放或领取方式
  ├─ coupon_use_rule            有效期、券类型与使用次数
  └─ coupon_ledger              实际领取、发放、使用事实
```

`coupon_issue_rule` 与 `coupon_use_rule` 均通过 `activity_id` 外键引用 `activity`，并以唯一约束保证每个活动至多一条对应规则。`coupon_ledger.activity_id` 为可空外键，允许历史事实尚未归属到活动。

## Schema 变更

### `activity`

增加可空列：

```sql
activity_import_key TEXT
```

对非空值建立唯一索引：

```sql
CREATE UNIQUE INDEX uq_activity_import_key
ON activity(activity_import_key)
WHERE activity_import_key IS NOT NULL;
```

删除旧的 `UNIQUE(dealer_platform_id, activity_name)` 约束。SQLite 不能直接删除内联唯一约束，因此迁移必须重建 `activity` 表，并原样保留已有 `activity_id` 以及所有其他列和值。

### `coupon_issue_rule`

```sql
coupon_issue_rule_id       INTEGER PRIMARY KEY AUTOINCREMENT
activity_id                INTEGER NOT NULL UNIQUE REFERENCES activity(activity_id)
issue_mode                 TEXT NOT NULL
issue_start_at             TEXT NOT NULL
issue_end_at               TEXT
auto_issue_at              TEXT
coupon_qty_per_grant       NUMERIC NOT NULL
max_claim_per_customer     NUMERIC
daily_claim_limit          NUMERIC
rule_status                TEXT NOT NULL
```

`issue_mode` 使用 `auto_grant` 或 `manual_claim`。自动发放必须提供 `auto_issue_at`，且 `issue_start_at` 与其相同；手动领取使用发放起止时间，自动发放的结束时间可为空。

### `coupon_use_rule`

```sql
coupon_use_rule_id         INTEGER PRIMARY KEY AUTOINCREMENT
activity_id                INTEGER NOT NULL UNIQUE REFERENCES activity(activity_id)
coupon_type                TEXT NOT NULL
validity_mode              TEXT NOT NULL
use_start_at               TEXT
use_end_at                 TEXT
valid_days_after_receive   INTEGER
max_use_per_coupon         NUMERIC NOT NULL
rule_status                TEXT NOT NULL
```

`validity_mode` 使用 `fixed_period` 或 `days_after_receive`。固定期间需要起止时间；领取后有效天数需要 `valid_days_after_receive`。`coupon_type` 保存单品优惠或多品组合优惠的业务取值。

### `coupon_ledger`

增加可空列：

```sql
activity_id INTEGER REFERENCES activity(activity_id)
```

增加 `idx_coupon_activity` 索引，便于按券活动查询台账。历史行不回填。

### `activity_scope`

不增加第三张范围表。其 `scope_category` 业务取值扩展为：发放对象、禁用对象、适用商品、禁用商品、必买商品、支付方式、物流方式、使用场景。既有商品、客户、禁用商品、禁用客户行继续兼容保留。

## 初始导入数据

在快马/兴路强平台创建两条券类活动及关联规则；其活动名来自方案截图，不以截图中的临时名称作为关联键。

| 导入键 | 活动名称 | 发放规则 | 使用规则 | 金额规则 |
| --- | --- | --- | --- | --- |
| `KM-COUPON-MANUAL-001` | 新客户投放 | `manual_claim`；2026-08-31 16:10 至 23:59；每次 2 张；每客最多 2 张；`rule_status=已结束` | 多品组合优惠；固定期间 2026-08-31 16:04 至 2026-09-15 23:59；每券 1 次；`rule_status=已结束` | 满 800 立减 10 |
| `KM-COUPON-AUTO-001` | test1 | `auto_grant`；发放起点和自动发放时间均为 2026-09-09 16:55；`rule_status=已结束` | 单品优惠；固定期间 2026-09-09 16:50 至 2026-09-12 16:50；每券 1 次；`rule_status=已结束` | 满 588 立减 200 |

两条活动仅导入有源证据的范围值：

- 新客户投放：发放对象/客户编号/`WX-00000000000007507743`，适用商品/商品范围/全部商品，支付方式/支付方式/在线支付。
- `test1`：发放对象/客户编号/`WX-00000000000007507893`，适用商品/品牌/可口可乐，使用场景/下单场景/客户自下单，以及使用场景/下单场景/代下单。

无勾选的支付、物流、使用场景选项不写限制行；两张截图均未列出必买商品，因此不创建必买商品范围行。

新增的指定客户列表提供了 `test1` 的完整目标客户编号，并与现有台账的客户编号、券名、领取时间和使用期一致。因此，券号 `202609091700313431` 可以回填为 `KM-COUPON-AUTO-001` 对应活动的 `activity_id`。除该券外，其余历史券仍保持为空，直至取得等效的活动配置与指定对象证据。

## 源数据变更

2026-10-04 更新的源目录将原“定向优惠券”三份明细和方案图重命名为 `test1优惠券`；文件哈希与旧文件一致。新增两份指定客户列表：`test1优惠券指定客户列表.xlsx` 与 `新客户投放优惠券指定客户列表.xlsx`。导入脚本必须使用新文件名并忽略同目录的 `.~` Office 临时文件。

## 数据导入与校验

迁移脚本必须在单一 SQLite 事务中完成结构变更、两条活动的幂等导入、对应规则及范围导入，并在提交前执行 `PRAGMA foreign_key_check`。重复执行不会重复创建活动、规则或范围行。

结构与数据验证至少覆盖：

1. 同名活动可在同一平台保存，非空导入键不能重复。
2. 每个券活动恰有一条发放规则和一条使用规则。
3. 自动发券只能关联发放时间之后的台账记录；手动领取必须在领取期间且不超过客户上限。
4. 已使用券的使用时间、金额门槛、商品范围、支付方式、使用期与券规则一致；无法验证的条件记录质量问题，不推测为通过。
5. 未使用券不会进入 `result_fee`。

## 非目标

- 不修改订单、费用结果或前端 API 契约。
- 不对历史活动或历史券做猜测性关联。
- 不新建按客户、商品、支付或物流分别拆分的小范围表。
