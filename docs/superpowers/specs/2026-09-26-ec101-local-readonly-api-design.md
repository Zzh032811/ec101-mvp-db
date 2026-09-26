# EC101 本地真实数据只读 API 设计

## 目标

让 GitHub 项目内的 EC101 SQLite 数据库可以通过跨平台本地 API 被费用运营平台查询，Mac 与 Windows 使用同一套启动方式和接口契约。当前阶段只读，不开放修改、核算重跑或结算写回。

## 范围

- API 直接读取 `mvp/ec101_mvp.db`。
- 提供订单、订单明细、活动、活动明细、客户、商品、履约记录、订单活动关系八类业务对象。
- 支持关键词、经销商、平台、分页和单行详情。
- 前端通过 `NEXT_PUBLIC_EC101_API_URL`（默认 `http://127.0.0.1:8787`）请求 API。
- API 不可用时前端明确提示，不回退到静态业务样例。

## 非目标

- 不在本阶段迁移 MySQL/PostgreSQL。
- 不增加登录、权限、修改、审批、结算和支付回写。
- 不把 SQLite 文件上传到 Site 或暴露下载。

## 运行方式

API 使用 Python 标准库 `http.server` 与 `sqlite3`，不依赖操作系统特定命令或第三方包：

```text
python api/server.py
```

前端本地启动时设置：

```text
EC101_API_URL=http://127.0.0.1:8787 npm run dev
```

Windows 使用同等的 PowerShell 环境变量写法。后续线上化时，只替换 API 的数据库连接和部署地址，前端接口契约保持不变。

## 接口契约

- `GET /health`：返回服务状态、数据库路径和可用对象。
- `GET /api/business-data/{object}`：返回 `{object, columns, rows, total, limit, offset}`。
- 查询参数：`q`、`dealer`、`platform`、`limit`（默认 50，上限 100）、`offset`。
- `GET /api/business-data/{object}/{id}`：返回单行详情；不存在返回 404。
- 所有查询使用参数化 SQL；对象名称只允许白名单映射，禁止拼接任意表名。
- CORS 仅允许本地前端来源，开发时允许 `http://localhost:*` 与 `http://127.0.0.1:*`。

## 数据边界

API 返回的是 SQLite 中已经导入的真实快照，不是前端演示数据。返回结果保留来源批次或计算批次字段，页面显示“本地真实数据库”。
