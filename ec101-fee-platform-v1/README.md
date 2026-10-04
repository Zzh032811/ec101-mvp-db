# EC101 费用运营前端

本前端的“费用与促销 TPM”区域仅调用只读 RESULT API，不在浏览器重算促销门槛、T-2 或结算金额。

```bash
NEXT_PUBLIC_EC101_API_URL=http://127.0.0.1:8787 npm run dev
```

另一个终端启动 API：`python3 api/server.py`。未传 `calc_batch_id` 时 API 会为每个活动选择自己的最新结果；传入时是固定历史批次回放。`tpm: null` 显示为“不走 TPM”，赠品仅按数量展示。

当前未实现异常协同、负责人、P0/P1、支付和 ERP 上账。生产多人使用前必须从本地 SQLite 迁移到受管数据库并增加权限与审计。
