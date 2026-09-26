# EC101 数据底座

本仓库包含 EC101 促销费用数据底座、MVP SQLite 数据库和费用运营平台。

## 本地真实数据联调

API 与运行说明见 [`api/README.md`](api/README.md)。最小启动流程：

```bash
python3 api/server.py
cd ec101-fee-platform-v1
NEXT_PUBLIC_EC101_API_URL=http://127.0.0.1:8787 npm run dev
```

当前 API 只读查询 `mvp/ec101_mvp.db`，Mac 与 Windows 均可运行；线上统一数据库和线上 API 属于下一阶段。
