# EC101 数据底座与费用运营平台

## Purpose

将经销商平台导出的订单、活动、客户、商品和履约事实沉淀到 EC101 SQLite MVP，并通过费用运营平台查询和核验促销费用。

## Current capabilities

- `mvp/ec101_mvp.db` 已包含快马×兴路强、舟谱×羿柏的真实导入数据和核算结果。
- `api/server.py` 提供跨平台只读 HTTP API，直接查询 SQLite。
- `ec101-fee-platform-v1` 的“业务数据”工作区通过 API 查询、筛选、查看详情和导出 CSV。

## How to run

```bash
python3 api/server.py
cd ec101-fee-platform-v1
NEXT_PUBLIC_EC101_API_URL=http://127.0.0.1:8787 npm run dev
```

Windows 使用 `py api/server.py` 和 PowerShell 环境变量写法，详见 `api/README.md`。

## Main flow

平台文件 → RAW/标准化脚本 → `mvp/ec101_mvp.db` → 只读 API → 费用运营平台业务数据工作区。

## Important files

- `mvp/ec101_mvp.db`：本地真实数据源；不要由前端直接读取。
- `api/server.py`：只读查询服务；后续线上化主要替换数据库连接和部署配置。
- `ec101-fee-platform-v1/app/page.tsx`：费用运营台界面和 API 联调逻辑。

## Current limits and next step

当前 API 仍为本地 SQLite，未配置认证、权限和线上统一数据库。下一步是选定 MySQL/PostgreSQL 或 D1，迁移表结构和数据，再将相同 API 契约部署到线上。
