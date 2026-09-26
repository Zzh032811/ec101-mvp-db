# EC101 本地真实数据 API

这是一个只读本地 API，直接查询仓库内的 `mvp/ec101_mvp.db`。它不修改数据库，也不提供核算重跑、审批或结算写入。

## 环境要求

- Python 3.9+（macOS、Windows 均可）
- 不需要安装第三方 Python 包

## 启动

在仓库根目录执行：

```bash
python3 api/server.py
```

Windows PowerShell：

```powershell
py api/server.py
```

也可以从 `api/` 目录启动，程序会按脚本位置自动找到数据库：

```bash
cd api
python3 server.py
```

默认监听 `http://127.0.0.1:8787`。可用 `--port` 或 `--db` 覆盖端口和数据库路径。

## 检查服务

```text
GET /health
GET /api/business-data/orders?dealer=兴路强&limit=20
GET /api/business-data/orders/1
```

支持的业务对象：`orders`、`order-lines`、`activities`、`activity-details`、`customers`、`products`、`fulfillments`、`order-activities`。

列表接口支持 `q`、`dealer`、`platform`、`limit`、`offset`；`limit` 最大为 100，`offset` 最大为 10000。

## 启动前端联调

另开一个终端：

```bash
cd ec101-fee-platform-v1
NEXT_PUBLIC_EC101_API_URL=http://127.0.0.1:8787 npm run dev
```

Windows PowerShell：

```powershell
cd ec101-fee-platform-v1
$env:NEXT_PUBLIC_EC101_API_URL = "http://127.0.0.1:8787"
npm run dev
```

前端 API 地址通过 `NEXT_PUBLIC_EC101_API_URL` 设置；未设置时默认使用 `http://127.0.0.1:8787`。

## 后续线上化

前端接口契约保持不变，只替换 API 服务端的数据库连接和部署地址。生产阶段再将 SQLite 迁移到统一 MySQL/PostgreSQL，并增加认证、权限和审计。
